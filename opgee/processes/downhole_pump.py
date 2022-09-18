#
# DownholePump class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
import numpy as np

from .shared import get_energy_carrier, get_energy_consumption_stages
from .. import ureg
from ..core import TemperaturePressure
from ..emissions import EM_COMBUSTION, EM_FUGITIVES
from ..log import getLogger
from ..process import Process
from ..stream import Stream

_logger = getLogger(__name__)


class DownholePump(Process):
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()
        self.downhole_pump = field.attr("downhole_pump")
        self.gas_lifting = field.attr("gas_lifting")
        self.res_temp = field.attr("res_temp")
        self.oil_volume_rate = field.attr("oil_prod")
        self.eta_pump_well = self.attr("eta_pump_well")
        self.prod_tubing_diam = diameter = field.attr("well_diam")
        self.prod_tubing_xsection_area = np.pi * (diameter / 2) ** 2
        self.depth = field.attr("depth")
        self.friction_factor = field.attr("friction_factor")
        self.num_prod_wells = field.attr("num_prod_wells")
        self.gravitational_acceleration = field.model.const("gravitational-acceleration")
        self.prime_mover_type = self.attr("prime_mover_type")

        self.oil_sand_mine = field.attr("oil_sands_mine")
        if self.oil_sand_mine != "None":
            self.set_enabled(False)
            return

    def run(self, analysis):
        self.print_running_msg()
        field = self.field

        # mass rate
        input = self.find_input_stream("crude oil")

        if input.is_uninitialized():
            return

        lift_gas = self.find_input_stream('lifting gas', raiseError=None)
        field.save_process_data(dp_input_before=input)

        loss_rate = self.venting_fugitive_rate()
        gas_fugitives = self.set_gas_fugitives(input, loss_rate)

        output = self.find_output_stream("crude oil")

        # Check
        output.copy_flow_rates_from(input, tp=field.wellhead_tp)
        if lift_gas is not None and lift_gas.is_initialized():
            output.add_flow_rates_from(lift_gas)
        output.subtract_rates_from(gas_fugitives)
        self.set_iteration_value(output.total_flow_rate())

        # energy use
        oil = field.oil
        water = field.water
        gas = field.gas
        solution_gas_oil_ratio_input = oil.solution_gas_oil_ratio(input,
                                                                  oil.oil_specific_gravity,
                                                                  oil.gas_specific_gravity,
                                                                  oil.gas_oil_ratio)
        solution_gas_oil_ratio_output = oil.solution_gas_oil_ratio(output,
                                                                   oil.oil_specific_gravity,
                                                                   oil.gas_specific_gravity,
                                                                   oil.gas_oil_ratio)
        oil_density_input = oil.density(input,
                                        oil.oil_specific_gravity,
                                        oil.gas_specific_gravity,
                                        oil.gas_oil_ratio)
        oil_density_output = oil.density(output,
                                         oil.oil_specific_gravity,
                                         oil.gas_specific_gravity,
                                         oil.gas_oil_ratio)
        volume_oil_lifted_input = oil.volume_flow_rate(input,
                                                       oil.oil_specific_gravity,
                                                       oil.gas_specific_gravity,
                                                       oil.gas_oil_ratio)
        volume_oil_lifted_output = oil.volume_flow_rate(output,
                                                        oil.oil_specific_gravity,
                                                        oil.gas_specific_gravity,
                                                        oil.gas_oil_ratio)

        # properties of crude oil (all at average conditions along wellbore, in production tubing)
        average_SOR = (solution_gas_oil_ratio_input + solution_gas_oil_ratio_output) / 2
        average_oil_density = (oil_density_input + oil_density_output) / 2
        average_volume_oil_lifted = (volume_oil_lifted_input + volume_oil_lifted_output).to("ft**3/day") / 2

        # properties of water (all at average conditions along wellbore, in production tubing)
        water_density = water.density()
        volume_water_lifted = water.volume_flow_rate(output)

        wellhead_T, wellhead_P = field.wellhead_tp.get()

        # properties of free gas (all at average conditions along wellbore, in production tubing)
        free_gas = solution_gas_oil_ratio_input - average_SOR
        wellbore_average_press = (wellhead_P + input.tp.P) / 2
        wellbore_average_temp = ureg.Quantity((wellhead_T.m + self.res_temp.m) / 2, "degF")
        stream = Stream("average", TemperaturePressure(wellbore_average_temp, wellbore_average_press))
        stream.copy_flow_rates_from(input)
        gas_FVF = gas.volume_factor(stream)
        gas_density = gas.density(stream)
        volume_free_gas = free_gas * gas_FVF
        volume_free_gas_lifted = (volume_free_gas * self.oil_volume_rate)

        total_volume_fluid_lifted = (average_volume_oil_lifted +
                                     volume_water_lifted +
                                     volume_free_gas_lifted)
        fluid_velocity = (total_volume_fluid_lifted / (self.prod_tubing_xsection_area * self.num_prod_wells))

        total_mass_fluid_lifted = (average_oil_density * average_volume_oil_lifted +
                                   water_density * volume_water_lifted +
                                   gas_density * volume_free_gas_lifted)
        fluid_lifted_density = (total_mass_fluid_lifted / total_volume_fluid_lifted)

        # downhole pump
        pressure_drop_elev = fluid_lifted_density * self.gravitational_acceleration * self.depth
        pressure_drop_fric = (fluid_lifted_density * self.friction_factor * self.depth * fluid_velocity ** 2 /
                              (2 * self.prod_tubing_diam))
        pressure_drop_total = pressure_drop_fric + pressure_drop_elev
        pressure_for_lifting = max(ureg.Quantity(0.0, "psia"), wellhead_P + pressure_drop_total - input.tp.P)
        liquid_flow_rate_per_well = (average_volume_oil_lifted + volume_water_lifted) / self.num_prod_wells
        brake_horse_power = 1.05 * (liquid_flow_rate_per_well * pressure_for_lifting) / self.eta_pump_well
        energy_consumption_of_stages = get_energy_consumption_stages(self.prime_mover_type, [brake_horse_power])
        energy_consumption_sum = sum(energy_consumption_of_stages) * self.num_prod_wells

        energy_use = self.energy
        energy_carrier = get_energy_carrier(self.prime_mover_type)
        energy_use.set_rate(energy_carrier, energy_consumption_sum)

        # import/export
        # import_product = field.import_export
        self.set_import_from_energy(energy_use)

        # emission
        emissions = self.emissions
        energy_for_combustion = energy_use.data.drop("Electricity")
        combustion_emission = (energy_for_combustion * self.process_EF).sum()
        emissions.set_rate(EM_COMBUSTION, "CO2", combustion_emission)

        emissions.set_from_stream(EM_FUGITIVES, gas_fugitives)

        field.save_process_data(dp_input_after=input)

    def impute(self):
        output = self.find_output_stream("crude oil")

        loss_rate = self.venting_fugitive_rate()
        loss_rate = (1 / (1 - loss_rate)).to("frac")

        input = self.find_input_stream("crude oil")
        output.multiply_flow_rates(loss_rate)
        input.copy_flow_rates_from(output)
