#
# PreMembraneChiller class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
from .. import ureg
from ..emissions import EM_FUGITIVES
from ..energy import EN_ELECTRICITY
from ..log import getLogger
from ..process import Process

_logger = getLogger(__name__)


class PreMembraneChiller(Process):
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()
        self.outlet_temp = field.attr("chiller_outlet_temp")
        self.fug_emissions_chiller = field.attr("fug_emissions_chiller")
        self.pressure_drop = ureg.Quantity(56.0, "delta_degC")
        self.feed_stream_mass_rate = ureg.Quantity(6.111072, "tonne/day")
        self.compressor_load = ureg.Quantity(3.44, "MW")

    def run(self, analysis):
        self.print_running_msg()
        field = self.field

        # mass rate
        input = self.find_input_stream("gas for chiller")

        if input.is_uninitialized():
            return

        gas_fugitives = self.set_gas_fugitives(input, self.fug_emissions_chiller.to("frac"))

        gas_to_compressor = self.find_output_stream("gas for compressor")
        gas_to_compressor.copy_flow_rates_from(input)
        gas_to_compressor.subtract_rates_from(gas_fugitives)
        gas_to_compressor.tp.set(T=self.outlet_temp, P=input.tp.P)

        delta_temp = input.tp.T - self.outlet_temp
        energy_consumption = (self.compressor_load * input.total_gas_rate() /
                              self.feed_stream_mass_rate * delta_temp / self.pressure_drop)

        # energy-use
        energy_use = self.energy
        energy_use.set_rate(EN_ELECTRICITY, energy_consumption)

        # import/export
        # import_product = field.import_export
        self.set_import_from_energy(energy_use)

        # emissions
        emissions = self.emissions
        emissions.set_from_stream(EM_FUGITIVES, gas_fugitives)
