from .. import ureg
from opgee.processes.compressor import Compressor
from ..emissions import EM_COMBUSTION, EM_FUGITIVES
from ..log import getLogger
from ..process import Process
from .shared import get_energy_carrier
from opgee.error import OpgeeException
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
        self.eta_compressor = field.attr("eta_compressor")
        self.flood_gas_type = field.attr("flood_gas_type")
        self.N2_flooding_temp = self.attr("N2_flooding_temp")
        self.N2_flooding_press = self.attr("N2_flooding_press")
        self.C1_flooding_temp = self.attr("C1_flooding_temp")
        self.C1_flooding_press = self.attr("C1_flooding_press")
        self.GFIR = field.attr("GFIR")
        self.offset_gas_comp = self.attrs_with_prefix("offset_gas_comp_")
        self.oil_prod = field.attr("oil_prod")
        self.gas_flooding_vol_rate = self.oil_prod * self.GFIR
        self.frac_CO2_breakthrough = field.attr("frac_CO2_breakthrough")

    def run(self, analysis):
        self.print_running_msg()
        field = self.field

        input = self.find_input_stream("gas for gas reinjection compressor")

        if input.is_uninitialized() and not self.gas_flooding:
            return

        input_gas_vol_rate =\
            ureg.Quantity(0, "mmscf/day")\
                if input.is_uninitialized()\
                else input.total_gas_rate() / field.gas.density(input)

        imported_gas = self.find_output_stream("imported gas")
        if self.gas_flooding:
            known_types = ["N2", "NG"]
            if self.flood_gas_type not in known_types:
                raise OpgeeException(f"{self.flood_gas_type} is not in the known gas type: {known_types}")
            else:
                if self.flood_gas_type == "N2":
                    N2_mass_rate = self.gas_flooding_vol_rate * field.gas.component_gas_rho_STP["N2"]
                    imported_gas.set_gas_flow_rate("N2", N2_mass_rate)
                    imported_gas.set_temperature_and_pressure(temp=self.N2_flooding_temp, press=self.N2_flooding_press)
                elif self.flood_gas_type == "NG":
                    adjust_flow_vol_rate = \
                        self.gas_flooding_vol_rate \
                            if self.gas_flooding_vol_rate.m <= input_gas_vol_rate.m \
                            else self.gas_flooding_vol_rate - input_gas_vol_rate
                    offset_mass_frac = field.gas.component_mass_fractions(self.offset_gas_comp)
                    offset_density = field.gas.component_gas_rho_STP[self.offset_gas_comp.index]
                    imported_gas.set_rates_from_series(adjust_flow_vol_rate * offset_mass_frac * offset_density,
                                                       phase=PHASE_GAS)
                    imported_gas.set_temperature_and_pressure(temp=self.C1_flooding_temp, press=self.C1_flooding_press)

        loss_rate = self.venting_fugitive_rate()
        gas_fugitives_temp = self.set_gas_fugitives(input, loss_rate)
        gas_fugitives = self.find_output_stream("gas fugitives")
        gas_fugitives.copy_flow_rates_from(gas_fugitives_temp, temp=field.std_temp, press=field.std_press)

        discharge_press = self.res_press + ureg.Quantity(500, "psi")
        overall_compression_ratio = discharge_press / input.pressure
        energy_consumption, output_temp, output_press = \
            Compressor.get_compressor_energy_consumption(
                self.field,
                self.prime_mover_type,
                self.eta_compressor,
                overall_compression_ratio,
                input)

        gas_to_well = self.find_output_stream("gas for gas reinjection well")
        gas_to_well.copy_flow_rates_from(input)
        gas_to_well.subtract_gas_rates_from(gas_fugitives)

        incoming_gas_consumed = energy_consumption / self.gas.energy_flow_rate(input)
        gas_to_well.multiply_flow_rates(1 - incoming_gas_consumed.m)

        # energy-use
        energy_use = self.energy
        energy_carrier = get_energy_carrier(self.prime_mover_type)
        energy_use.set_rate(energy_carrier, energy_consumption)

        # emissions
        emissions = self.emissions
        energy_for_combustion = energy_use.data.drop("Electricity")
        combustion_emission = (energy_for_combustion * self.process_EF).sum()
        emissions.set_rate(EM_COMBUSTION, "CO2", combustion_emission.to("tonne/day"))

        emissions.set_from_stream(EM_FUGITIVES, gas_fugitives)
