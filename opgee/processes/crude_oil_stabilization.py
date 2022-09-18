#
# CrudeOilStabilization class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
from .compressor import Compressor
from .shared import get_energy_carrier
from .. import ureg
from ..core import TemperaturePressure
from ..emissions import EM_COMBUSTION, EM_FUGITIVES
from ..log import getLogger
from ..process import Process
from ..stream import Stream, PHASE_LIQUID, PHASE_GAS

_logger = getLogger(__name__)


class CrudeOilStabilization(Process):
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()
        self.stab_tp = TemperaturePressure(self.attr("stabilizer_column_temp"), self.attr("stabilizer_column_press"))
        self.mol_per_scf = field.model.const("mol-per-scf")
        self.stab_gas_press = field.attr("gas_pressure_after_boosting")
        self.eps_stab = self.attr("eps_stab")
        self.eta_gas = self.attr("eta_gas")
        self.eta_electricity = self.attr("eta_electricity")
        self.prime_mover_type = self.attr("prime_mover_type")
        self.eta_compressor = self.attr("eta_compressor")
        self.oil_sands_mine = field.attr("oil_sands_mine")
        if self.oil_sands_mine != "None":
            self.set_enabled(False)
            return

    def run(self, analysis):
        self.print_running_msg()
        field = self.field



        # mass rate
        input = self.find_input_stream("oil for stabilization")

        if input.is_uninitialized():
            return

        input_T, input_P = input.tp.get()

        average_temp = (self.stab_tp.T.m + input_T.m) / 2
        average_temp = ureg.Quantity(average_temp, "degF")

        oil = self.field.oil
        oil_specific_heat = oil.specific_heat(oil.API, average_temp)
        stream = Stream("out_stream", self.stab_tp)
        solution_GOR_inlet = oil.solution_gas_oil_ratio(input,
                                                        oil.oil_specific_gravity,
                                                        oil.gas_specific_gravity,
                                                        oil.gas_oil_ratio)
        solution_GOR_outlet = oil.solution_gas_oil_ratio(stream,
                                                         oil.oil_specific_gravity,
                                                         oil.gas_specific_gravity,
                                                         oil.gas_oil_ratio)
        oil_mass_rate = input.flow_rate("oil", PHASE_LIQUID)
        oil_density = oil.density(input,
                                  oil.oil_specific_gravity,
                                  oil.gas_specific_gravity,
                                  oil.gas_oil_ratio)
        gas_removed_by_stabilizer = oil_mass_rate * (solution_GOR_inlet - solution_GOR_outlet) / oil_density
        gas_removed_molar_rate = gas_removed_by_stabilizer * self.mol_per_scf * oil.gas_comp  # Pandas Series
        gas_removed_mass_rate = oil.component_MW[gas_removed_molar_rate.index] * gas_removed_molar_rate

        output_stab_gas = self.find_output_stream("gas for gas gathering")
        output_stab_gas.set_tp(self.stab_tp)
        output_stab_gas.set_rates_from_series(gas_removed_mass_rate, PHASE_GAS)

        loss_rate = self.venting_fugitive_rate()
        gas_fugitives = self.set_gas_fugitives(input, loss_rate)

        output = self.find_output_stream("oil for storage")
        oil_for_storage = oil_mass_rate - output_stab_gas.total_gas_rate() - gas_fugitives.total_gas_rate()
        output.set_liquid_flow_rate("oil", oil_for_storage, tp=self.stab_tp)

        self.set_iteration_value(output_stab_gas.total_flow_rate() + output.total_flow_rate())

        # energy use
        heat_duty = oil_mass_rate * oil_specific_heat * (self.stab_tp.T - input_T) * (1 + self.eps_stab)
        energy_use = self.energy

        energy_carrier = get_energy_carrier(self.prime_mover_type)
        energy_consumption = heat_duty / self.eta_gas if self.prime_mover_type == "NG_engine" else heat_duty / self.eta_electricity

        # boosting compressor for stabilizer
        overall_compression_ratio = self.stab_gas_press / input.tp.P
        compressor_energy, _, _ = Compressor.get_compressor_energy_consumption(field,
                                                                               self.prime_mover_type,
                                                                               self.eta_compressor,
                                                                               overall_compression_ratio,
                                                                               output_stab_gas,
                                                                               inlet_tp=input.tp)

        energy_consumption += compressor_energy
        energy_use.set_rate(energy_carrier, energy_consumption.to("mmBtu/day"))

        # import/export
        self.set_import_from_energy(energy_use)

        # emission rate
        emissions = self.emissions
        energy_for_combustion = energy_use.data.drop("Electricity")
        combustion_emission = (energy_for_combustion * self.process_EF).sum()
        emissions.set_rate(EM_COMBUSTION, "CO2", combustion_emission)

        emissions.set_from_stream(EM_FUGITIVES, gas_fugitives)

        self.field.save_process_data(oil_stab_solution_GOR_outlet=solution_GOR_outlet)
