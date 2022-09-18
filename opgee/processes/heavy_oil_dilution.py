#
# HeavyOilDilution class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
from opgee.processes.transport_energy import TransportEnergy
from .shared import get_energy_carrier
from .. import ureg
from ..core import TemperaturePressure
from ..emissions import EM_COMBUSTION
from ..import_export import DILUENT
from ..process import Process
from ..stream import Stream


class HeavyOilDilution(Process):
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()
        self.oil = self.field.oil
        self.oil_SG = self.oil.oil_specific_gravity
        self.oil_prod_rate = field.attr("oil_prod")

        self.water = self.field.water
        self.water_density = self.water.density()

        self.frac_diluent = self.attr("fraction_diluent")
        self.downhole_pump = field.attr("downhole_pump")
        self.oil_sand_mine = field.attr("oil_sands_mine")

        self.bitumen_API = field.attr("API_bitumen")
        self.bitumen_SG = self.oil.specific_gravity(self.bitumen_API)
        self.bitumen_tp = TemperaturePressure(field.attr("temperature_mined_bitumen"),
                                              field.attr("pressure_mined_bitumen"))

        self.diluent_API = self.attr("diluent_API")
        self.dilution_SG = self.oil.specific_gravity(self.diluent_API)

        self.dilution_type = self.attr("dilution_type")
        self.diluent_tp = TemperaturePressure(self.attr("diluent_temp"),
                                              self.attr("diluent_temp"))
        self.before_diluent_tp = TemperaturePressure(self.attr("before_diluent_temp"),
                                                     self.attr("before_diluent_press"))
        self.final_mix_tp = TemperaturePressure(self.attr("final_mix_temp"),
                                                self.attr("final_mix_press"))

        self.transport_share_fuel = field.transport_share_fuel.loc["Diluent"]
        self.transport_parameter = field.transport_parameter[["Diluent", "Units"]]
        self.transport_by_mode = field.transport_by_mode.loc["Diluent"]

    def run(self, analysis):
        self.print_running_msg()
        field =self.field

        # mass rate
        input_oil = self.find_input_stream("oil for dilution", raiseError=False)
        input_bitumen = self.find_input_stream("bitumen for dilution", raiseError=False)

        if self.frac_diluent.m == 0.0:
            return

        if input_oil is None and input_bitumen is None:
            return

        if (input_oil is not None and input_oil.is_uninitialized()) and \
                (input_bitumen is not None and input_bitumen.is_uninitialized()):
            return

        output = self.find_output_stream("oil for storage")
        oil_mass_rate = input_oil.liquid_flow_rate("oil") if input_oil is not None else ureg.Quantity(0.0, "tonne/day")
        bitumen_mass_rate =\
            input_bitumen.liquid_flow_rate("oil") if input_bitumen is not None else ureg.Quantity(0.0, "tonne/day")
        total_mass_rate = oil_mass_rate + bitumen_mass_rate
        output.set_liquid_flow_rate("oil", total_mass_rate, tp=self.final_mix_tp)

        frac_diluent = self.frac_diluent

        total_mass_oil_bitumen_before_dilution = total_mass_rate
        final_SG = self.oil_SG if self.oil_sand_mine is None else self.bitumen_SG
        total_volume_oil_bitumen_before_dilution = 0 if frac_diluent == 1 else \
            total_mass_oil_bitumen_before_dilution / final_SG / self.water_density
        expected_volume_oil_bitumen = self.oil_prod_rate if frac_diluent == 1 else \
            self.oil_prod_rate / (1 - frac_diluent)
        required_volume_diluent = expected_volume_oil_bitumen if frac_diluent == 1 else \
            expected_volume_oil_bitumen * frac_diluent

        if self.dilution_type == "Diluent":
            required_mass_dilution = required_volume_diluent * self.dilution_SG * self.water_density
            total_mass_diluted_oil = required_mass_dilution + total_mass_oil_bitumen_before_dilution
        else:
            total_mass_diluted_oil = expected_volume_oil_bitumen * self.dilution_SG
            required_mass_dilution = total_mass_diluted_oil if frac_diluent == 1 else \
                total_mass_diluted_oil - total_mass_oil_bitumen_before_dilution

        # TODO: unused variable
        # diluted_oil_bitumen_SG = self.oil_SG if expected_volume_oil_bitumen <= 0 else \
        #     total_mass_diluted_oil / expected_volume_oil_bitumen / self.water_density

        stream = Stream("diluent", self.before_diluent_tp)
        diluent_density = self.oil.density(stream, self.dilution_SG, self.oil.gas_specific_gravity,
                                           self.oil.gas_oil_ratio)
        heavy_oil_density = self.oil.density(stream, self.oil_SG, self.oil.gas_specific_gravity, self.oil.gas_oil_ratio)
        diluent_energy_density_mass = self.oil.mass_energy_density(API=self.diluent_API)
        heavy_oil_energy_density_mass = self.oil.mass_energy_density(API=self.oil.API)
        diluent_energy_density_vol = diluent_energy_density_mass * diluent_density
        heavy_oil_energy_density_vol = heavy_oil_energy_density_mass * heavy_oil_density

        final_diluent_LHV_mass = \
            diluent_energy_density_mass if frac_diluent == 1.0 or self.dilution_type == "Diluent" \
                else (
                             diluent_energy_density_vol *
                             total_mass_diluted_oil -
                             total_mass_oil_bitumen_before_dilution *
                             heavy_oil_energy_density_vol) / required_mass_dilution

        self.field.save_process_data(final_diluent_LHV_mass=final_diluent_LHV_mass)

        oil_mass_energy_density = self.oil.mass_energy_density(self.diluent_API)
        oil_LHV_rate = required_mass_dilution * oil_mass_energy_density

        fuel_consumption = TransportEnergy.get_transport_energy_dict(self.field,
                                                                     self.transport_parameter,
                                                                     self.transport_share_fuel,
                                                                     self.transport_by_mode,
                                                                     oil_LHV_rate,
                                                                     "Diluent")

        energy_use = self.energy
        for name, value in fuel_consumption.items():
            energy_use.set_rate(get_energy_carrier(name), value.to("mmBtu/day"))

        # import/export
        import_product = field.import_export
        self.set_import_from_energy(energy_use)
        import_product.set_export(self.name, DILUENT, oil_LHV_rate)

        # emission
        emissions = self.emissions
        energy_for_combustion = energy_use.data.drop("Electricity")
        combustion_emission = (energy_for_combustion * self.process_EF).sum()
        emissions.set_rate(EM_COMBUSTION, "CO2", combustion_emission)
