#
# CO2InjectionWell class
#
# Author: Richard Plevin and Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
from ..log import getLogger
from ..process import Process
from ..stream import PHASE_GAS

_logger = getLogger(__name__)


class CO2Membrane(Process):
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()
        self.gas = field.gas
        self.membrane_comp = field.imported_gas_comp["Membrane Separation Gas"]
        self.feed_press_AGR = field.attr("feed_press_AGR")

    def run(self, analysis):
        self.print_running_msg()
        field = self.field

        input = self.find_input_stream("gas for CO2 membrane")

        if input.is_uninitialized():
            return

        gas_to_AGR = self.find_output_stream("gas for AGR")
        AGR_mol_fracs = 1 - self.membrane_comp
        gas_to_AGR.copy_flow_rates_from(input, tp=field.stp)
        gas_to_AGR.multiply_factor_from_series(AGR_mol_fracs, PHASE_GAS)

        gas_to_compressor = self.find_output_stream("gas for CO2 compressor")
        gas_to_compressor.tp.set(T=field.stp.T, P=input.tp.P * 0.33)
        gas_to_compressor.copy_flow_rates_from(input)
        gas_to_compressor.multiply_factor_from_series(self.membrane_comp, PHASE_GAS)
