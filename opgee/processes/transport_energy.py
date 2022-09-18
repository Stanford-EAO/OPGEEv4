#
# TransportEnergy class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
import pandas as pd

from opgee import ureg
from opgee.core import OpgeeObject
from opgee.error import OpgeeException
from ..energy import EN_DIESEL


class TransportEnergy(OpgeeObject):
    def __init__(self, field):
        self.field = field

    # TODO: if you need to call other methods of the class, then don't make it a @staticmethod
    #       Then you can just call self.get_water_transport_energy_consumption() rather than using the
    #       classname. Embedding the class name prevents the class from being subclassed, since the
    #       subclass will still refer to the hardcoded classname rather than the new subclass.

    @staticmethod
    def get_transport_energy_dict(field,
                                  parameter_table,
                                  transport_share_fuel,
                                  transport_by_mode,
                                  LHV_rate,
                                  prod_type):
        known_types = ["diluent", "lng", "crude", "petrocoke"]
        prod_type = prod_type.lower()
        if prod_type not in known_types:
            raise OpgeeException(f"{prod_type} is not in the known product type: {known_types}")

        parameter_dict = TransportEnergy.get_parameter_dict(parameter_table)

        # TODO: is it necessary to say "ocean_tanker" rather than just "tanker"? Longer names
        #       that don't add clarity are worse than clear, shorter names.
        ocean_tanker_load_factor_dest = parameter_dict["load_factor_to_dest_tanker"]
        barge_load_factor_dest = parameter_dict["load_factor_to_dest_barge"]
        ocean_tanker_load_factor_origin = parameter_dict["load_factor_to_orig_tanker"]
        barge_load_factor_origin = parameter_dict["load_factor_to_orig_barge"]
        barge_capacity = parameter_dict["capacity_barge"]
        ocean_tanker_speed = parameter_dict["speed_tanker"]
        ocean_tanker_size = parameter_dict["ocean_tanker_size"]
        barge_speed = parameter_dict["speed_barge"]
        energy_intensity_pipeline_turbine = parameter_dict["energy_intensity_pipeline_turbine"]
        energy_intensity_pipeline_engine_current = parameter_dict["energy_intensity_pipeline_engine_current"]
        frac_power_pipeline_turbine = parameter_dict["frac_power_pipeline_turbine"]
        frac_power_pipeline_engine_current = parameter_dict["frac_power_pipeline_engine_current"]
        energy_intensity_pipeline_engine_future = parameter_dict["energy_intensity_pipeline_engine_future"]
        frac_power_pipeline_engine_future = parameter_dict["frac_power_pipeline_engine_future"]
        energy_intensity_rail_transport = parameter_dict["energy_intensity_rail_to_dest"]
        energy_intensity_truck = ureg.Quantity(969.0, "btu/(tonne*mile)")
        feed_loss = parameter_dict["feed_loss"]
        fraction_transport = transport_by_mode["Fraction"]
        transport_distance = transport_by_mode["Distance"]
        residual_oil_LHV = field.model.const("residual-oil-LHV")
        residual_oil_density = field.model.const("residual-oil-density")

        # TODO: Avoid redundant code by distilling out the commonality and calling a local function, e.g.,
        def transp_energy(load_factor, mode):
            # TODO: try to find shorter meaningful names, like TransportEnergy.maritime_energy_use()
            #       Long names are tedious to read and force strange formatting of the code, which is also harder to read.
            return TransportEnergy.get_water_transport_energy_consumption(
                residual_oil_LHV,
                residual_oil_density,
                load_factor, mode)

        # TODO: then you can do this. Use same approach below for transport_energy_density()
        # ocean_tanker_dest_energy_consumption = transp_energy(ocean_tanker_load_factor_dest, "tanker")

        ocean_tanker_dest_energy_consumption = \
            TransportEnergy.get_water_transport_energy_consumption(
                residual_oil_LHV,
                residual_oil_density,
                ocean_tanker_load_factor_dest,
                "tanker")
        ocean_tanker_orig_energy_consumption = \
            TransportEnergy.get_water_transport_energy_consumption(
                residual_oil_LHV,
                residual_oil_density,
                ocean_tanker_load_factor_origin,
                "tanker")
        barge_dest_energy_consumption = \
            TransportEnergy.get_water_transport_energy_consumption(
                residual_oil_LHV,
                residual_oil_density,
                barge_load_factor_dest,
                "barge")
        barge_orig_energy_consumption = \
            TransportEnergy.get_water_transport_energy_consumption(
                residual_oil_LHV,
                residual_oil_density,
                barge_load_factor_origin,
                "barge")

        ocean_tanker_hp = ureg.Quantity(9070 + 0.101 * ocean_tanker_size.m, "hp")
        barge_hp = ureg.Quantity(5600 / 22500 * barge_capacity.m, "hp")

        ocean_tanker_dest_energy_intensity = \
            TransportEnergy.transport_energy_intensity(
                ocean_tanker_speed,
                ocean_tanker_size,
                barge_capacity,
                barge_speed,
                ocean_tanker_dest_energy_consumption,
                ocean_tanker_load_factor_dest,
                ocean_tanker_hp,
                "tanker")
        barge_dest_energy_intensity = \
            TransportEnergy.transport_energy_intensity(
                ocean_tanker_speed,
                ocean_tanker_size,
                barge_capacity,
                barge_speed,
                barge_dest_energy_consumption,
                barge_load_factor_dest,
                barge_hp,
                "barge")
        pipeline_dest_energy_intensity = (energy_intensity_pipeline_turbine *
                                          frac_power_pipeline_turbine +
                                          energy_intensity_pipeline_engine_current *
                                          frac_power_pipeline_engine_current +
                                          energy_intensity_pipeline_engine_future *
                                          frac_power_pipeline_engine_future)
        ocean_tanker_origin_energy_intensity = \
            TransportEnergy.transport_energy_intensity(
                ocean_tanker_speed,
                ocean_tanker_size,
                barge_capacity,
                barge_speed,
                ocean_tanker_orig_energy_consumption,
                ocean_tanker_load_factor_origin,
                ocean_tanker_hp,
                "tanker")
        barge_origin_energy_intensity = \
            TransportEnergy.transport_energy_intensity(
                ocean_tanker_speed,
                ocean_tanker_size,
                barge_capacity,
                barge_speed,
                barge_orig_energy_consumption,
                barge_load_factor_origin,
                barge_hp,
                "barge")

        pipeline_origin_energy_intensity = ureg.Quantity(0.0, "btu/tonne/mile")
        rail_origin_energy_intensity = ureg.Quantity(200.0, "btu/tonne/mile")
        truck_origin_energy_intensity = energy_intensity_truck

        transport_dest_energy_consumption = pd.Series([ocean_tanker_dest_energy_intensity, barge_dest_energy_intensity,
                                                       pipeline_dest_energy_intensity, energy_intensity_rail_transport,
                                                       energy_intensity_truck], dtype="pint[btu/tonne/mile]")

        # save to the field and retrieve them from exploration
        if prod_type == "crude":
            field.save_process_data(ocean_tanker_dest_energy_intensity=ocean_tanker_dest_energy_intensity)
            field.save_process_data(energy_intensity_truck=energy_intensity_truck)

        transport_origin_energy_consumption = pd.Series(
            [ocean_tanker_origin_energy_intensity, barge_origin_energy_intensity,
             pipeline_origin_energy_intensity, rail_origin_energy_intensity,
             truck_origin_energy_intensity], dtype="pint[btu/tonne/mile]")

        if prod_type == "diluent":
            denominator = field.get_process_data("final_diluent_LHV_mass")
        elif prod_type == "lng":
            denominator = field.gas.component_LHV_mass["C1"]
        elif prod_type == "crude":
            denominator = field.get_process_data("crude_LHV")
        else:
            denominator = field.model.const("petrocoke-heating-value") / 1.10231

        transport_energy_consumption =\
            (transport_dest_energy_consumption + transport_origin_energy_consumption) / denominator

        fuel_consumption = \
            TransportEnergy.fuel_consumption(
                fraction_transport,
                transport_distance,
                transport_share_fuel,
                transport_energy_consumption,
                feed_loss,
                LHV_rate)

        return fuel_consumption

    @staticmethod
    def get_parameter_dict(parameter_table):
        """
        Given Dataframe with name, value and unit. Return parameter dictionary where key is
        the name and value is the ureg.Quantity with unit specified.

        :return:
        """
        parameter_value = parameter_table.iloc[:, 0]
        parameter_unit = parameter_table["Units"]
        parameter_dict = {}
        for name, value in parameter_value.iteritems():
            parameter_dict[name] = ureg.Quantity(float(value), parameter_unit[name])

        return parameter_dict

    @staticmethod
    def get_water_transport_energy_consumption(residual_oil_LHV, residual_oil_density, load_factor, type):
        """
        calculate the water transport energy consumption

        :param residual_oil_density:
        :param residual_oil_LHV:
        :param type: (str) "tanker" or "barge"
        :param load_factor:
        :return: (float) energy consumption (unit = btu/hp/hr)
        """
        known_types = ["tanker", "barge"]
        if type not in known_types:
            raise OpgeeException(f"{type} is not in the known transport type: {known_types}")

        const = 150 if type == "tanker" else 350
        result = (14.42 / load_factor.m + const) * 0.735 * residual_oil_LHV.m / residual_oil_density.m
        return ureg.Quantity(result, "btu/hp/hr")

    @staticmethod
    def transport_energy_intensity(ocean_tanker_speed,
                                   ocean_tanker_size,
                                   barge_capacity,
                                   barge_speed,
                                   energy_consumption,
                                   load_factor,
                                   hp,
                                   type):
        """
        Calculate tanker energy intensity using load factor

        :param barge_speed:
        :param barge_capacity:
        :param ocean_tanker_size:
        :param ocean_tanker_speed:
        :param type: (str) "tanker" or "barge"
        :param hp:
        :param energy_consumption:
        :param load_factor:
        :return: (float) tanker energy intensity
        """

        known_types = ["tanker", "barge"]
        if type not in known_types:
            raise OpgeeException(f"{type} is not in the known transport type: {known_types}")

        common = energy_consumption * load_factor * hp
        if type == "tanker":
            result = common / ocean_tanker_speed / ocean_tanker_size
        else: # must be "barge" since we checked.
            result = common / barge_capacity / barge_speed
        return result

    @staticmethod
    def fuel_consumption(fraction_transport,
                         transport_distance,
                         transport_share_fuel,
                         transport_energy_consumption,
                         feed_loss,
                         LHV):
        """
        Calculate different type of fuel consumption.

        :param feed_loss:
        :param transport_share_fuel:
        :param transport_distance:
        :param fraction_transport:
        :param transport_energy_consumption:
        :param LHV:
        :return: (float) calculate fuel consumption
        """
        transport_energy_consumption.index = transport_distance.index

        result = {}
        for type, frac in transport_share_fuel.iteritems():
            temp = (transport_energy_consumption * transport_distance * fraction_transport * frac).sum() * LHV
            result[type] = temp if type != EN_DIESEL else temp + LHV * feed_loss
        return result
