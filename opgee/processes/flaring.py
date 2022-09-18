#
# Flaring class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
from .. import ureg
from ..emissions import EM_FLARING
from ..log import getLogger
from ..process import Process
from ..stream import Stream

_logger = getLogger(__name__)


# TODO: Ask Zhang for the flaring model.

class Flaring(Process):
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()
        self.FOR = field.attr("FOR")
        if self.FOR.m == 0:
            self.set_enabled(False)
            return

        self.gas = field.gas
        self.mol_per_scf = field.model.const("mol-per-scf")
        self.oil_volume_rate = field.attr("oil_prod")
        self.combusted_gas_frac = field.attr("combusted_gas_frac")

    def run(self, analysis):
        self.print_running_msg()
        field = self.field

        if not self.all_streams_ready("gas for flaring"):
            return

        # mass rate
        input = self.find_input_streams("gas for flaring", combine=True)  # type: Stream

        gas_mol_fraction = self.gas.total_molar_flow_rate(input)
        gas_volume_rate = gas_mol_fraction / self.mol_per_scf
        SCO_bitumen_ratio = field.get_process_data("SCO_bitumen_ratio")
        if SCO_bitumen_ratio:
            volume_of_gas_flared = self.oil_volume_rate * self.FOR / SCO_bitumen_ratio
        else:
            volume_of_gas_flared = self.oil_volume_rate * self.FOR
        frac_gas_flared = min(ureg.Quantity(1, "frac"), volume_of_gas_flared / gas_volume_rate)

        methane_slip = Stream("methane_slip", tp=input.tp)
        methane_slip.copy_flow_rates_from(input)
        multiplier = (frac_gas_flared * (1 - self.combusted_gas_frac)).m
        methane_slip.multiply_flow_rates(multiplier)

        gas_to_flare = Stream("gas_to_flare", tp=input.tp)
        gas_to_flare.copy_flow_rates_from(input)
        gas_to_flare.multiply_flow_rates(frac_gas_flared.m)
        gas_to_flare.subtract_rates_from(methane_slip)

        output_gas = self.find_output_stream("gas for venting", raiseError=False)
        if output_gas is None:
            output_gas = self.find_output_stream("gas for gas gathering")
        output_gas.copy_flow_rates_from(input)
        output_gas.subtract_rates_from(gas_to_flare)
        output_gas.subtract_rates_from(methane_slip)

        self.set_iteration_value(output_gas.total_flow_rate())

        # emissions
        emissions = self.emissions
        sum_streams = Stream("combusted_stream", tp=gas_to_flare.tp)
        sum_streams.add_combustion_CO2_from(gas_to_flare)
        sum_streams.add_flow_rates_from(methane_slip)
        emissions.set_from_stream(EM_FLARING, sum_streams)
