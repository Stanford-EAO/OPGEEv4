#
# Venting class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
from opgee.processes.compressor import Compressor
from .shared import get_gas_lifting_init_stream
from .. import ureg
from ..emissions import EM_VENTING, EM_FUGITIVES
from ..log import getLogger
from ..process import Process
from ..stream import Stream

_logger = getLogger(__name__)


class Venting(Process):
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()
        self.VOR = field.attr("VOR")
        if self.VOR.m == 0:
            self.set_enabled(False)
            return

        self.gas = field.gas
        self.pipe_leakage = field.attr("surface_piping_leakage")
        self.gas_lifting = field.attr("gas_lifting")
        self.GOR = field.attr("GOR")
        self.FOR = field.attr("FOR")
        self.WOR = field.attr("WOR")
        self.GLIR = field.attr("GLIR")
        self.oil_prod = field.attr("oil_prod")
        self.res_press = field.attr("res_press")
        self.water_prod = self.oil_prod * self.WOR
        self.VOR_over_GOR = self.VOR / (self.GOR - self.FOR) if (self.GOR.m - self.FOR.m) > 0 else ureg.Quantity(0, "frac")
        self.imported_fuel_gas_comp = field.imported_gas_comp["Imported Fuel"]
        self.imported_fuel_gas_mass_fracs = field.gas.component_mass_fractions(self.imported_fuel_gas_comp)

    def run(self, analysis):
        self.print_running_msg()
        field = self.field
        # mass rate

        input = self.find_input_stream("gas for venting", raiseError=False)
        if input is None or input.is_uninitialized():
            return

        input_tp = input.tp

        methane_lifting = self.field.get_process_data(
            "methane_from_gas_lifting") if self.gas_lifting else None
        gas_lifting_fugitive_loss_rate = self.field.get_process_data("gas_lifting_compressor_loss_rate")
        gas_stream = get_gas_lifting_init_stream(field.gas, self.imported_fuel_gas_comp,
                                                 self.imported_fuel_gas_mass_fracs,
                                                 self.GLIR, self.oil_prod,
                                                 self.water_prod, input_tp)

        if methane_lifting is None and len(gas_stream.gas_flow_rates()) > 0:
            input_press = input_tp.P
            discharge_press = (self.res_press + input_press) / 2 + ureg.Quantity(100.0, "psia")
            overall_compression_ratio = discharge_press / input_press

            energy_consumption, _, _ = Compressor.get_compressor_energy_consumption(field,
                                                                                    field.prime_mover_type_lifting,
                                                                                    field.eta_compressor_lifting,
                                                                                    overall_compression_ratio,
                                                                                    gas_stream,
                                                                                    inlet_tp=input_tp)

            energy_content_imported_gas = self.gas.mass_energy_density(gas_stream) * gas_stream.total_gas_rate()
            frac_imported_gas_consumed = energy_consumption / energy_content_imported_gas
            loss_rate = (ureg.Quantity(0.0, "frac")
                         if gas_lifting_fugitive_loss_rate is None else gas_lifting_fugitive_loss_rate)
            factor = 1 - loss_rate - frac_imported_gas_consumed
            gas_stream.multiply_flow_rates(factor.m)
            methane_lifting = gas_stream.gas_flow_rate("C1")
        else:
            methane_lifting = ureg.Quantity(0, "tonne/day")

        methane_to_venting = (input.gas_flow_rate("C1") - methane_lifting) * self.VOR_over_GOR
        venting_frac = \
            methane_to_venting / input.gas_flow_rate("C1") \
                if input.gas_flow_rate("C1").m != 0 else ureg.Quantity(0, "frac")
        fugitive_frac = \
            self.pipe_leakage / input.gas_flow_rate("C1") \
                if input.gas_flow_rate("C1").m != 0 else ureg.Quantity(0, "frac")

        if self.field.get_process_data("gas_lifting_stream") is None:
            self.field.save_process_data(gas_lifting_stream=gas_stream)

        gas_to_vent = Stream("venting_gas", tp=field.stp)
        gas_to_vent.copy_flow_rates_from(input, tp=field.stp)
        gas_to_vent.multiply_flow_rates(venting_frac.to("frac").m)

        gas_fugitives = self.set_gas_fugitives(input, fugitive_frac.to("frac").m)

        gas_to_gathering = self.find_output_stream("gas for gas gathering")
        gas_to_gathering.copy_flow_rates_from(input, tp=input.tp)
        gas_to_gathering.multiply_flow_rates(1 - venting_frac.m - fugitive_frac.m)

        self.set_iteration_value(gas_to_gathering.total_flow_rate())

        # emissions
        emissions = self.emissions
        emissions.set_from_stream(EM_FUGITIVES, gas_fugitives)
        emissions.set_from_stream(EM_VENTING, gas_to_vent)
