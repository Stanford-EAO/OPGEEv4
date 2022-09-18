#
# GasPartition class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
from .shared import get_gas_lifting_init_stream
from .. import ureg
from ..core import STP
from ..log import getLogger
from ..process import Process
from ..stream import PHASE_GAS, Stream

_logger = getLogger(__name__)


class GasPartition(Process):
    """
    Gas partition is to check the reasonable amount of gas goes to gas lifting and gas reinjection
    """
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()
        self.gas = field.gas
        self.gas_lifting_option = field.attr("gas_lifting")
        self.imported_fuel_gas_comp = field.imported_gas_comp["Imported Fuel"]
        self.imported_fuel_gas_mass_fracs = field.gas.component_mass_fractions(self.imported_fuel_gas_comp)
        self.imported_gas_stream = Stream("imported_gas", STP)
        self.imported_gas_stream.set_rates_from_series(
            self.imported_fuel_gas_mass_fracs * ureg.Quantity(1., "tonne/day"),
            phase=PHASE_GAS)
        self.fraction_remaining_gas_inj = field.attr("fraction_remaining_gas_inj")
        self.natural_gas_reinjection = field.attr("natural_gas_reinjection")
        self.gas_flooding = field.attr("gas_flooding")
        self.flood_gas_type = field.attr("flood_gas_type")
        self.GLIR = field.attr("GLIR")
        self.oil_prod = field.attr("oil_prod")
        self.WOR = field.attr("WOR")
        self.water_prod = self.oil_prod * self.WOR
        self.iteration_tolerance = field.model.attr("iteration_tolerance")
        self.is_first_loop = True

    def run(self, analysis):
        self.print_running_msg()

        if not self.all_streams_ready("gas for gas partition"):
            return

        input = self.find_input_streams("gas for gas partition", combine=True)
        if input.is_uninitialized():
            return

        input_tp = input.tp

        gas_lifting = self.find_output_stream("lifting gas", raiseError=False)
        if self.gas_lifting_option and gas_lifting:
            if self.is_first_loop:
                init_stream = get_gas_lifting_init_stream(self.field.gas,
                                                          self.imported_fuel_gas_comp,
                                                          self.imported_fuel_gas_mass_fracs,
                                                          self.GLIR, self.oil_prod,
                                                          self.water_prod, input_tp)
                gas_lifting.copy_flow_rates_from(init_stream)
                self.is_first_loop = False

            # Check
            iteration_series = (gas_lifting.components.gas - input.components.gas).astype(float)
            iteration_series[iteration_series < 0] = 0
            self.set_iteration_value(iteration_series)

            if sum(iteration_series) >= self.iteration_tolerance:
                gas_lifting.copy_flow_rates_from(input)
                self.field.save_process_data(methane_from_gas_lifting=gas_lifting.gas_flow_rate("C1"))
                return

        exported_gas = self.find_output_stream("gas")
        exported_gas.copy_flow_rates_from(input, tp=input_tp)
        if gas_lifting:
            exported_gas.subtract_rates_from(gas_lifting)

        gas_to_reinjection = self.find_output_stream("gas for gas reinjection compressor", raiseError=False)
        if gas_to_reinjection:
            if self.natural_gas_reinjection or (self.gas_flooding and self.flood_gas_type == "NG"):
                gas_to_reinjection.copy_flow_rates_from(exported_gas)
                gas_to_reinjection.multiply_flow_rates(self.fraction_remaining_gas_inj)

        # gas_mass_rate = exported_gas.total_gas_rate()
        # gas_mass_energy_density = self.gas.mass_energy_density(exported_gas)
        # gas_LHV_rate = gas_mass_rate * gas_mass_energy_density
        # import_product = field.import_export
        # import_product.set_export(self.name, NATURAL_GAS, gas_LHV_rate)

        # excluded = [s.strip() for s in getParam("OPGEE.ExcludeFromReinjectionEnergySummary").split(",")]
        # energy_sum = self.field.sum_process_energy(processes_to_exclude=excluded)
        # NG_energy_sum = energy_sum.get_rate(EN_NATURAL_GAS)
        #
        # NG_LHV = self.gas.mass_energy_density(gas_to_reinjection)
        # is_gas_to_reinjection_empty = False
        # if NG_LHV.m == 0:
        #     is_gas_to_reinjection_empty = True
        #     NG_LHV = self.gas.mass_energy_density(self.imported_gas_stream)
        #
        # NG_mass = NG_energy_sum / NG_LHV
        # NG_consumption_stream = Stream("NG_consump_stream", gas_to_reinjection.tp)
        #
        # if is_gas_to_reinjection_empty:
        #     NG_consumption_series = self.imported_fuel_gas_mass_fracs * NG_mass
        # else:
        #     NG_consumption_series = self.gas.component_mass_fractions(
        #         self.gas.component_molar_fractions(gas_to_reinjection)) * NG_mass
        #
        # NG_consumption_stream.set_rates_from_series(NG_consumption_series, PHASE_GAS)
        #
        # tot_exported_mass = gas_to_reinjection.total_flow_rate() - NG_consumption_stream.total_flow_rate()
        # if tot_exported_mass.m >= 0:
        #     exported_gas.copy_flow_rates_from(gas_to_reinjection)
        #     exported_gas.subtract_gas_rates_from(NG_consumption_stream)
        #     exported_gas.set_tp(input_tp)
        #
        # if is_gas_to_reinjection_empty is False and tot_exported_mass.m >= 0:
        #     gas_to_reinjection.subtract_gas_rates_from(exported_gas)

