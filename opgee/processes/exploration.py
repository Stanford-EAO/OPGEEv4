#
# Exploration class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
from opgee import ureg
from .transport_energy import TransportEnergy
from ..constants import year_to_day
from ..emissions import EM_COMBUSTION
from ..energy import EN_DIESEL
from ..log import getLogger
from ..process import Process

_logger = getLogger(__name__)


class Exploration(Process):
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()
        self.vertical_drill_df = field.vertical_drill_df
        self.horizontal_drill_df = field.horizontal_drill_df

        self.well_size = field.attr("well_size")
        self.well_complexity = field.attr("well_complexity")
        self.eta_rig = field.attr("eta_rig")
        self.vertical_drill_energy_intensity = \
            (self.vertical_drill_df.loc[self.eta_rig]).loc[self.well_size][self.well_complexity]
        self.horizontal_drill_energy_intensity = \
            (self.horizontal_drill_df.loc[self.eta_rig]).loc[self.well_size][self.well_complexity]

        self.oil_sands_mine = field.attr("oil_sands_mine")
        self.offshore = field.attr("offshore")
        self.weight_land_survey = field.attr("weight_land_survey")
        self.weight_ocean_survey = field.attr("weight_ocean_survey")
        self.distance_survey = field.attr("distance_survey")
        self.number_wells_dry = field.attr("number_wells_dry")
        self.number_wells_exploratory = field.attr("number_wells_exploratory")
        self.num_wells = field.attr("num_prod_wells") + field.attr("num_water_inj_wells")
        self.depth = field.attr("depth")
        self.frac_wells_horizontal = field.attr("fraction_wells_horizontal")
        self.length_lateral = field.attr("length_lateral")
        self.number_wells_dry = field.attr("number_wells_dry")
        self.number_wells_exploratory = field.attr("number_wells_exploratory")
        self.field_production_lifetime = field.attr("field_production_lifetime")

        self.drill_fuel_consumption = \
            (self.vertical_drill_energy_intensity * (1 - self.frac_wells_horizontal) * self.depth +
             self.horizontal_drill_energy_intensity * self.frac_wells_horizontal * self.length_lateral) * self.num_wells
        self.drill_energy_consumption = field.model.const("diesel-LHV") * self.drill_fuel_consumption

        self.transport_share_fuel = field.transport_share_fuel.loc["Crude"]
        self.transport_parameter = field.transport_parameter[["Crude", "Units"]]
        self.frac_transport_mode = field.attrs_with_prefix("frac_transport_").rename("Fraction")
        self.transport_dist = field.attrs_with_prefix("transport_dist_").rename("Distance")
        self.transport_by_mode = self.frac_transport_mode.to_frame().join(self.transport_dist)

    def run(self, analysis):
        self.print_running_msg()

        field = self.field

        oil_mass_energy_density = field.oil.mass_energy_density()
        if self.field.get_process_data("crude_LHV") is None:
            self.field.save_process_data(crude_LHV=oil_mass_energy_density)
        _ = TransportEnergy.get_transport_energy_dict(field,
                                                      self.transport_parameter,
                                                      self.transport_share_fuel,
                                                      self.transport_by_mode,
                                                      ureg.Quantity(1.0, "btu/day"),
                                                      "Crude")
        ocean_tank_energy_intensity = field.get_process_data("ocean_tanker_dest_energy_intensity")
        truck_energy_intensity = field.get_process_data("energy_intensity_truck")

        export_LHV = field.get_process_data("exported_prod_LHV")
        cumulative_export_LHV = export_LHV * year_to_day * self.field_production_lifetime
        survey_vehicle_energy_consumption = \
            truck_energy_intensity * self.weight_land_survey * self.distance_survey if not self.offshore else \
                ocean_tank_energy_intensity * self.weight_ocean_survey * self.distance_survey
        drill_consumption_per_well = self.drill_energy_consumption / self.num_wells \
            if self.oil_sands_mine == "None" else ureg.Quantity(0.0, "mmbtu")
        drill_energy_consumption = drill_consumption_per_well * (self.number_wells_dry + self.number_wells_exploratory)
        frac_energy_consumption = (survey_vehicle_energy_consumption + drill_energy_consumption) / cumulative_export_LHV
        diesel_consumption = frac_energy_consumption * export_LHV

        field.save_process_data(cumulative_export_LHV=cumulative_export_LHV)
        field.save_process_data(drill_energy_consumption=drill_energy_consumption)
        field.save_process_data(num_wells=self.num_wells)

        # energy-use
        energy_use = self.energy
        energy_use.set_rate(EN_DIESEL, diesel_consumption)

        emissions = self.emissions
        energy_for_combustion = energy_use.data.drop("Electricity")
        combustion_emission = (energy_for_combustion * self.process_EF).sum()
        emissions.set_rate(EM_COMBUSTION, "CO2", combustion_emission)
