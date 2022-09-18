#
# GasReinjectionCompressor class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
from .compressor import Compressor
from .shared import get_energy_carrier
from .. import ureg
from ..core import TemperaturePressure
from ..emissions import EM_COMBUSTION, EM_FUGITIVES
from ..error import OpgeeException
from ..import_export import NATURAL_GAS
from ..log import getLogger
from ..process import Process
from ..stream import PHASE_GAS, Stream

_logger = getLogger(__name__)


class GasReinjectionCompressor(Process):
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()
        self.gas = field.gas
        self.res_press = field.attr("res_press")
        self.gas_flooding = field.attr("gas_flooding")
        self.prime_mover_type = self.attr("prime_mover_type")
        self.eta_compressor = self.attr("eta_compressor")
        self.flood_gas_type = field.attr("flood_gas_type")
        self.N2_flooding_tp = TemperaturePressure(self.attr("N2_flooding_temp"),
                                                  self.attr("N2_flooding_press"))
        self.C1_flooding_tp = TemperaturePressure(self.attr("C1_flooding_temp"),
                                                  self.attr("C1_flooding_press"))
        self.CO2_flooding_tp = TemperaturePressure(self.attr("CO2_flooding_temp"),
                                                  self.attr("CO2_flooding_press"))

        self.GFIR = field.attr("GFIR")
        self.offset_gas_comp = field.imported_gas_comp["Gas Flooding"]
        self.oil_prod = field.attr("oil_prod")
        self.gas_flooding_vol_rate = self.oil_prod * self.GFIR

    def run(self, analysis):
        self.print_running_msg()
        field = self.field

        input = self.find_input_stream("gas for gas reinjection compressor")

        if input.is_uninitialized() or not self.gas_flooding:
            return

        input_gas_vol_rate = \
            ureg.Quantity(0., "mmscf/day") \
                if input.is_uninitialized() \
                else input.total_gas_rate() / field.gas.density(input)

        imported_gas = Stream("imported_gas", tp=input.tp)
        if self.gas_flooding:
            known_types = ["N2", "NG", "CO2"]
            if self.flood_gas_type not in known_types:
                raise OpgeeException(f"{self.flood_gas_type} is not in the known gas type: {known_types}")
            else:
                if self.flood_gas_type == "N2":
                    N2_mass_rate = self.gas_flooding_vol_rate * field.gas.component_gas_rho_STP["N2"]
                    imported_gas.set_gas_flow_rate("N2", N2_mass_rate)
                    imported_gas.set_tp(self.N2_flooding_tp)
                elif self.flood_gas_type == "NG":
                    adjust_flow_vol_rate = self.gas_flooding_vol_rate \
                            if self.gas_flooding_vol_rate.m <= input_gas_vol_rate.m \
                            else self.gas_flooding_vol_rate - input_gas_vol_rate
                    offset_mass_frac = field.gas.component_mass_fractions(self.offset_gas_comp)
                    offset_density = field.gas.component_gas_rho_STP[self.offset_gas_comp.index]
                    imported_gas.set_rates_from_series(adjust_flow_vol_rate * offset_mass_frac * offset_density,
                                                       phase=PHASE_GAS)
                    imported_gas.set_tp(self.C1_flooding_tp)

                    # Calculate import NG energy content
                    gas_mass_rate = imported_gas.total_gas_rate()
                    gas_mass_energy_density = self.gas.mass_energy_density(imported_gas)
                    gas_LHV_rate = gas_mass_rate * gas_mass_energy_density
                    import_product = field.import_export
                    import_product.set_import(self.name, NATURAL_GAS, gas_LHV_rate)
                else:
                    CO2_mass_rate = self.gas_flooding_vol_rate * field.gas.component_gas_rho_STP["CO2"]
                    imported_gas.set_gas_flow_rate("CO2", CO2_mass_rate)
                    imported_gas.set_tp(self.N2_flooding_tp)


        loss_rate = self.venting_fugitive_rate()
        gas_fugitives = self.set_gas_fugitives(input, loss_rate)

        total_rate_for_compression = Stream("imported_gas", tp=input.tp)
        total_rate_for_compression.add_flow_rates_from(input)
        total_rate_for_compression.add_flow_rates_from(imported_gas)

        discharge_press = self.res_press + ureg.Quantity(500., "psi")
        overall_compression_ratio = discharge_press / input.tp.P
        energy_consumption, output_temp, output_press = \
            Compressor.get_compressor_energy_consumption(
                self.field,
                self.prime_mover_type,
                self.eta_compressor,
                overall_compression_ratio,
                total_rate_for_compression)

        gas_to_well = self.find_output_stream("gas for gas reinjection well")
        gas_to_well.copy_flow_rates_from(input)
        gas_to_well.subtract_rates_from(gas_fugitives)

        self.set_iteration_value(gas_to_well.total_flow_rate())

        # energy-use
        energy_use = self.energy
        energy_carrier = get_energy_carrier(self.prime_mover_type)
        energy_use.set_rate(energy_carrier, energy_consumption)

        # import/export
        self.set_import_from_energy(energy_use)

        # emissions
        emissions = self.emissions
        energy_for_combustion = energy_use.data.drop("Electricity")
        combustion_emission = (energy_for_combustion * self.process_EF).sum()
        emissions.set_rate(EM_COMBUSTION, "CO2", combustion_emission)

        emissions.set_from_stream(EM_FUGITIVES, gas_fugitives)
