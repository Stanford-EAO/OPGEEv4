#
# GasDistribution class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
from ..emissions import EM_FUGITIVES
from ..import_export import NATURAL_GAS
from ..log import getLogger
from ..process import Process

_logger = getLogger(__name__)


class GasDistribution(Process):
    """
    Gas distribution calculates emission of gas to distribution

    """
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()
        self.gas = field.gas
        self.frac_loss =\
            self.attr("frac_loss_distribution") + self.attr("frac_loss_meter") + self.attr("frac_loss_enduse")

    def run(self, analysis):
        self.print_running_msg()
        field = self.field

        input = self.find_input_streams("gas for distribution", combine=True)

        if input.is_uninitialized():
            return

        gas_fugitives = self.set_gas_fugitives(input, self.frac_loss.m)

        gas_to_customer = self.find_output_stream("gas")
        gas_to_customer.copy_flow_rates_from(input)
        gas_to_customer.subtract_rates_from(gas_fugitives)

        gas_mass_rate = gas_to_customer.total_gas_rate()
        gas_mass_energy_density = self.gas.mass_energy_density(gas_to_customer)
        gas_LHV_rate = gas_mass_rate * gas_mass_energy_density
        import_product = field.import_export
        import_product.set_export(self.name, NATURAL_GAS, gas_LHV_rate)

        # emissions
        emissions = self.emissions
        emissions.set_from_stream(EM_FUGITIVES, gas_fugitives)





