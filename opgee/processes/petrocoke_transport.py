#
# PetrocokeTransport class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
from opgee.processes.transport_energy import TransportEnergy
from .shared import get_energy_carrier
from ..emissions import EM_COMBUSTION
from ..import_export import NGL_LPG
from ..log import getLogger
from ..process import Process

_logger = getLogger(__name__)


class PetrocokeTransport(Process):
    """
    Petrocoke transport calculate emissions from petrocoke to the market

    """

    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()
        self.oil = field.oil
        self.transport_share_fuel = field.transport_share_fuel.loc["Petrocoke"]
        self.transport_parameter = field.transport_parameter[["Petrocoke", "Units"]]
        self.transport_by_mode = field.transport_by_mode.loc["Petrocoke"]
        self.petro_coke_heating_value = self.model.const("petrocoke-heating-value")

    def run(self, analysis):
        self.print_running_msg()
        field = self.field

        input_coke = self.find_input_stream("petrocoke")

        if input_coke.is_uninitialized():
            return

        petrocoke_mass_rate = input_coke.solid_flow_rate("PC")
        petrocoke_LHV_rate = petrocoke_mass_rate * self.petro_coke_heating_value

        self.frac_coke_exported = field.get_process_data("frac_coke_exported").m

        petrocoke_to_market = self.find_output_stream("petrocoke for market")
        petrocoke_to_market.copy_flow_rates_from(input_coke)
        petrocoke_to_market.multiply_flow_rates(self.frac_coke_exported)

        petrocoke_to_export = self.find_output_stream("exported petrocoke")
        petrocoke_to_export.copy_flow_rates_from(input_coke)
        petrocoke_to_export.multiply_flow_rates(1-self.frac_coke_exported)

        # energy use
        energy_use = self.energy
        fuel_consumption = TransportEnergy.get_transport_energy_dict(self.field,
                                                                     self.transport_parameter,
                                                                     self.transport_share_fuel,
                                                                     self.transport_by_mode,
                                                                     petrocoke_LHV_rate,
                                                                     "Petrocoke")

        for name, value in fuel_consumption.items():
            energy_use.set_rate(get_energy_carrier(name), value.to("mmBtu/day"))

        # import/export
        import_product = field.import_export
        self.set_import_from_energy(energy_use)
        import_product.set_export(self.name, NGL_LPG, petrocoke_LHV_rate)


        # emission
        emissions = self.emissions
        energy_for_combustion = energy_use.data.drop("Electricity")
        combustion_emission = (energy_for_combustion * self.process_EF).sum()
        emissions.set_rate(EM_COMBUSTION, "CO2", combustion_emission)