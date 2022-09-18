#
# StorageSeparator class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
from ..core import TemperaturePressure
from ..log import getLogger
from ..process import Process
from ..stream import Stream

_logger = getLogger(__name__)


class StorageSeparator(Process):
    """
    Storage well calculate fugitive emission from storage wells.
    """
    def _after_init(self):
        super()._after_init()

        self.water_production_frac = self.attr("water_production_frac")
        self.outlet_tp = TemperaturePressure(self.attr("outlet_temp"), self.attr("outlet_press"))

    def run(self, analysis):
        self.print_running_msg()

        input = self.find_input_stream("gas for separator")

        if input.is_uninitialized():
            return

        # produced water stream
        prod_water = Stream("produced water stream", self.outlet_tp)
        prod_water.set_liquid_flow_rate("H2O", (input.total_gas_rate() * self.water_production_frac).m)

        gas_to_compressor = self.find_output_stream("gas for storage")
        gas_to_compressor.copy_gas_rates_from(input, tp=self.outlet_tp)

        #TODO: Future versions of OPGEE may treat this process in more detail.




