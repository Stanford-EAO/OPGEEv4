#
# VRUCompressor class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
from opgee.processes.compressor import Compressor
from .shared import get_energy_carrier
from ..emissions import EM_COMBUSTION, EM_FUGITIVES
from ..log import getLogger
from ..process import Process

_logger = getLogger(__name__)


class VRUCompressor(Process):
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()
        self.gas = field.gas
        self.discharge_press = self.attr("discharge_press")
        self.prime_mover_type = self.attr("prime_mover_type")
        self.eta_compressor = self.attr("eta_compressor")

    def run(self, analysis):
        self.print_running_msg()
        field = self.field

        if not self.all_streams_ready("gas for VRU"):
            return

        # mass rate
        input = self.find_input_streams("gas for VRU",combine=True)

        if input.is_uninitialized():
            return

        loss_rate = self.venting_fugitive_rate()
        gas_fugitives = self.set_gas_fugitives(input, loss_rate)

        gas_to_gathering = self.find_output_stream("gas for gas gathering")

        overall_compression_ratio = self.discharge_press / input.tp.P
        energy_consumption, output_temp, output_press = \
            Compressor.get_compressor_energy_consumption(
                self.field,
                self.prime_mover_type,
                self.eta_compressor,
                overall_compression_ratio,
                input)

        gas_to_gathering.copy_flow_rates_from(input)
        gas_to_gathering.subtract_rates_from(gas_fugitives)
        gas_to_gathering.tp.set(T=output_temp, P=self.discharge_press)

        self.set_iteration_value(gas_to_gathering.total_flow_rate())

        # energy-use
        energy_use = self.energy
        energy_carrier = get_energy_carrier(self.prime_mover_type)
        energy_use.set_rate(energy_carrier, energy_consumption)

        # import/export
        # import_product = field.import_export
        self.set_import_from_energy(energy_use)

        # emissions
        emissions = self.emissions
        energy_for_combustion = energy_use.data.drop("Electricity")
        combustion_emission = (energy_for_combustion * self.process_EF).sum()
        emissions.set_rate(EM_COMBUSTION, "CO2", combustion_emission)

        emissions.set_from_stream(EM_FUGITIVES, gas_fugitives)
