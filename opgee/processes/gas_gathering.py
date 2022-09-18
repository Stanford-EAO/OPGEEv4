#
# GasGathering class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
from ..emissions import EM_FUGITIVES
from ..log import getLogger
from ..process import Process

_logger = getLogger(__name__)


class GasGathering(Process):
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()

    def run(self, analysis):
        self.print_running_msg()
        field = self.field

        if not self.all_streams_ready("gas for gas gathering"):
            return

        # mass_rate
        input = self.find_input_streams("gas for gas gathering", combine=True)

        loss_rate = self.venting_fugitive_rate()
        gas_fugitives = self.set_gas_fugitives(input, loss_rate)

        output_gas = self.find_output_stream("gas for gas dehydration", raiseError=False)
        if output_gas is None:
            output_gas = self.find_output_stream("gas for gas partition")
        output_gas.copy_flow_rates_from(input)
        output_gas.subtract_rates_from(gas_fugitives)

        self.set_iteration_value(output_gas.total_flow_rate())

        # emissions
        emissions = self.emissions
        emissions.set_from_stream(EM_FUGITIVES, gas_fugitives)

