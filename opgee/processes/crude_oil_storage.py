#
# CrudeOilStorage class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
from .. import ureg
from ..emissions import EM_FUGITIVES
from ..log import getLogger
from ..process import Process
from ..stream import PHASE_GAS
from ..stream import Stream

_logger = getLogger(__name__)


class CrudeOilStorage(Process):
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()

        self.oil = field.oil
        self.oil_sands_mine = field.attr("oil_sands_mine")
        model = field.model
        self.tonne_to_bbl = model.const("tonne-to-bbl")

        self.storage_gas_comp = field.imported_gas_comp["Storage Gas"]
        self.CH4_comp = self.storage_gas_comp["C1"]
        self.f_FG_CS_VRU = self.attr("f_FG_CS_VRU")
        self.f_FG_CS_FL = self.attr("f_FG_CS_FL")

    def run(self, analysis):
        self.print_running_msg()
        field = self.field

        # TODO: LPG to blend with crude oil need to be implement after gas branch
        # mass rate
        input = self.find_input_streams("oil for storage", combine=True)

        if input.is_uninitialized():
            return

        oil_mass_rate = input.liquid_flow_rate("oil")
        # TODO: loss rate need to be replaced by VF-component
        loss_rate = self.venting_fugitive_rate()
        loss_rate = ureg.Quantity(0.47, "kg/bbl_oil")
        gas_exsolved_upon_flashing = oil_mass_rate * loss_rate * self.tonne_to_bbl / \
                                     self.CH4_comp if self.oil_sands_mine == "None" else ureg.Quantity(0, "tonne/day")

        vapor_to_flare = self.f_FG_CS_FL * gas_exsolved_upon_flashing * self.storage_gas_comp
        vapor_to_VRU = self.f_FG_CS_VRU * gas_exsolved_upon_flashing * self.storage_gas_comp
        gas_fugitives = (1 - self.f_FG_CS_VRU - self.f_FG_CS_FL) * gas_exsolved_upon_flashing * self.storage_gas_comp

        stp = field.stp

        output_flare = self.find_output_stream("gas for flaring", raiseError=False)
        if output_flare:
            output_flare.set_rates_from_series(vapor_to_flare, PHASE_GAS)
            output_flare.set_tp(stp)
        else:
            output_flare = Stream("empty_stream", tp=stp)

        output_VRU = self.find_output_stream("gas for VRU")
        output_VRU.set_rates_from_series(vapor_to_VRU, PHASE_GAS)
        output_VRU.set_tp(stp)

        gas_fugitive_stream = Stream("gas_fugitives", tp=self.field.stp)
        gas_fugitive_stream.set_rates_from_series(gas_fugitives, PHASE_GAS)
        gas_fugitive_stream.set_tp(stp)

        output_transport = self.find_output_stream("oil")
        oil_to_transport_mass_rate = (oil_mass_rate -
                                      output_VRU.total_gas_rate() -
                                      output_flare.total_gas_rate() -
                                      gas_fugitive_stream.total_gas_rate())
        output_transport.set_liquid_flow_rate("oil", oil_to_transport_mass_rate)
        output_transport.set_tp(stp)

        self.set_iteration_value(
            output_flare.total_flow_rate() + output_VRU.total_flow_rate()
            + gas_fugitive_stream.total_flow_rate() + output_transport.total_flow_rate())

        # No energy-use for storage

        # emissions
        emissions = self.emissions
        emissions.set_from_stream(EM_FUGITIVES, gas_fugitive_stream)
