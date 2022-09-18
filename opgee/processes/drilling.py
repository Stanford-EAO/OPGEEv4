#
# Drilling class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
import numpy as np

from opgee import ureg
from ..emissions import EM_COMBUSTION, EM_LAND_USE
from ..energy import EN_DIESEL
from ..log import getLogger
from ..process import Process

_logger = getLogger(__name__)


class Drilling(Process):
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()

        self.fraction_wells_fractured = field.attr("fraction_wells_fractured")
        self.fracture_consumption_tbl = field.model.fracture_energy
        self.pressure_gradient_fracturing = field.attr("pressure_gradient_fracturing")
        self.volume_per_well_fractured = field.attr("volume_per_well_fractured")
        self.oil_sand_mine = field.attr("oil_sands_mine")
        if self.oil_sand_mine != "None":
            self.set_enabled(False)
            return
        self.land_use_EF = field.model.land_use_EF
        self.ecosystem_richness = field.attr("ecosystem_richness")
        self.field_development_intensity = field.attr("field_development_intensity")

    def run(self, analysis):
        self.print_running_msg()

        field = self.field
        fracture_energy_constant = self.get_fracture_constant()
        fracture_diesel_use = self.get_fracture_diesel(fracture_energy_constant)
        fracture_fuel_consumption = self.fraction_wells_fractured * field.get_process_data("num_wells") * fracture_diesel_use
        fracture_energy_consumption = fracture_fuel_consumption * field.model.const("diesel-LHV")
        tot_energy_consumption = fracture_energy_consumption + field.get_process_data("drill_energy_consumption")
        wellhead_LHV_rate = field.get_process_data("wellhead_LHV_rate")
        cumulative_export_LHV = field.get_process_data("cumulative_export_LHV")
        diesel_consumption = wellhead_LHV_rate / cumulative_export_LHV * tot_energy_consumption

        # calculate land use emissions
        land_use_intensity_df = self.land_use_EF.loc["Oil sands mining"]
        land_use_intensity = land_use_intensity_df.loc[self.field_development_intensity]
        land_use_emission = land_use_intensity.sum() * field.get_process_data("exported_oil_LHV")

        # energy-use
        energy_use = self.energy
        energy_use.set_rate(EN_DIESEL, diesel_consumption)

        emissions = self.emissions
        energy_for_combustion = energy_use.data.drop("Electricity")
        combustion_emission = (energy_for_combustion * self.process_EF).sum()
        emissions.set_rate(EM_COMBUSTION, "CO2", combustion_emission)
        emissions.set_rate(EM_LAND_USE, "CO2", land_use_emission)

    def get_fracture_constant(self):
        """
        Calculate fracturing rig energy consumption constant a, b, c

        :return:Array list of const [a, b, c]
        """

        result = []
        value = self.pressure_gradient_fracturing
        tbl = self.fracture_consumption_tbl
        result.append(np.interp(value.m, tbl["a"].index, tbl["a"].values))
        result.append(np.interp(value.m, tbl["b"].index, tbl["b"].values))
        result.append(np.interp(value.m, tbl["c"].index, tbl["c"].values))

        return result

    def get_fracture_diesel(self, constants):
        """
        Calculate diesel use per well for fracturing

        :return: diesel use (unit=gallon)
        """
        variables = []
        volume = self.volume_per_well_fractured.m
        variables.append(volume * volume)
        variables.append(volume)
        variables.append(1)

        result = np.dot(variables, constants)
        result = ureg.Quantity(result, "gallon")
        return result
