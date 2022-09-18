#
# CO2ReinjectionCompressor class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
from opgee.processes.compressor import Compressor
from .shared import get_energy_carrier
from .. import ureg
from ..emissions import EM_COMBUSTION, EM_FUGITIVES
from ..log import getLogger
from ..process import Process

_logger = getLogger(__name__)


class CO2ReinjectionCompressor(Process):
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()
        self.gas = field.gas
        # TODO: remove field.xx to field.py and change the reference
        self.res_press = field.attr("res_press")
        self.eta_compressor = self.attr("eta_compressor")
        self.prime_mover_type = self.attr("prime_mover_type")
        self.gas_flooding = field.attr("gas_flooding")
        self.flood_gas_type = field.attr("flood_gas_type")
        self.GFIR = field.attr("GFIR")
        self.oil_prod = field.attr("oil_prod")
        self.gas_flooding_vol_rate = self.oil_prod * self.GFIR

    def run(self, analysis):
        self.print_running_msg()
        field = self.field

        if not self.all_streams_ready("gas for CO2 compressor"):
            return

        # mass rate
        input = self.find_input_streams("gas for CO2 compressor", combine=True)
        if input.is_uninitialized():
            return

        loss_rate = self.venting_fugitive_rate()
        gas_fugitives = self.set_gas_fugitives(input, loss_rate)

        gas_to_well = self.find_output_stream("gas for CO2 injection well")
        gas_to_well.copy_flow_rates_from(input)
        gas_to_well.subtract_rates_from(gas_fugitives)

        total_CO2_mass_rate = input.gas_flow_rate("CO2")
        if self.gas_flooding and self.flood_gas_type == "CO2":
            CO2_mass_rate = self.gas_flooding_vol_rate * field.gas.component_gas_rho_STP["CO2"]
            imported_CO2_mass_rate = CO2_mass_rate - gas_to_well.gas_flow_rate("CO2")
            total_CO2_mass_rate += imported_CO2_mass_rate
        input.set_gas_flow_rate("CO2", total_CO2_mass_rate)

        discharge_press = self.res_press + ureg.Quantity(500.0, "psia")
        overall_compression_ratio = discharge_press / input.tp.P
        energy_consumption, temp, _ = Compressor.get_compressor_energy_consumption(self.field,
                                                                                   self.prime_mover_type,
                                                                                   self.eta_compressor,
                                                                                   overall_compression_ratio,
                                                                                   input)

        # gas_to_well.set_temperature_and_pressure(temp, input.pressure)
        gas_to_well.tp.set(T=temp, P=input.tp.P)

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
