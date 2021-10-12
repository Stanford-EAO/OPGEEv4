from ..log import getLogger
from ..process import Process
from ..stream import PHASE_LIQUID, PHASE_GAS
from opgee import ureg
from ..energy import Energy, EN_NATURAL_GAS, EN_ELECTRICITY, EN_DIESEL
from ..emissions import Emissions, EM_COMBUSTION, EM_LAND_USE, EM_VENTING, EM_FLARING, EM_FUGITIVES

_logger = getLogger(__name__)


class RyanHolmes(Process):
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()
        self.gas = field.gas
        self.RH_process_tbl = field.model.ryan_holmes_process_tbl
        self.std_temp = field.model.const("std-temperature")
        self.std_press = field.model.const("std-pressure")
        self.diesel_LHV = field.model.const("diesel-LHV")
        self.mol_to_scf = field.model.const("mol-per-scf")
        self.daily_use_engine = self.attr("daily_use_engine")


    def run(self, analysis):
        self.print_running_msg()

        # mass rate
        input = self.find_input_stream("gas for Ryan Holmes")

        loss_rate = self.venting_fugitive_rate()
        gas_fugitives_temp = self.set_gas_fugitives(input, loss_rate)
        gas_fugitives = self.find_output_stream("gas fugitives")
        gas_fugitives.copy_flow_rates_from(gas_fugitives_temp)
        gas_fugitives.set_temperature_and_pressure(self.std_temp, self.std_press)

        gas_to_partition = self.find_output_stream("gas for gas partition")
        gas_to_partition.copy_flow_rates_from(input)
        gas_to_partition.subtract_gas_rates_from(gas_fugitives)
        gas_to_partition.multiply_factor_from_series(self.RH_process_tbl.loc[:, "Light HC"], PHASE_GAS)
        gas_to_partition.set_temperature_and_pressure(input.temperature, input.pressure)

        gas_to_NGL = self.find_output_stream("gas for NGL")
        gas_to_NGL.copy_flow_rates_from(input)
        gas_to_NGL.subtract_gas_rates_from(gas_fugitives)
        gas_to_NGL.multiply_factor_from_series(self.RH_process_tbl.loc[:, "Heavy HC"], PHASE_GAS)
        gas_to_NGL.set_temperature_and_pressure(input.temperature, input.pressure)

        gas_to_CO2_reinjection = self.find_output_stream("gas for CO2 compressor")
        gas_to_CO2_reinjection.copy_flow_rates_from(input)
        gas_to_CO2_reinjection.subtract_gas_rates_from(gas_fugitives)
        gas_to_CO2_reinjection.multiply_factor_from_series(self.RH_process_tbl.loc[:, "CO2-rich"], PHASE_GAS)
        gas_to_CO2_reinjection.set_temperature_and_pressure(input.temperature, input.pressure)

        # Ryan-Holmes Process
        volume_flow_rate_STP = self.gas.tot_volume_flow_rate_STP(input)
        feed_stream_rate = ureg.Quantity(45, "mmscf/day")
        turbine_consume_rate = ureg.Quantity(25800, "scf/hr")
        tot_turbine_consumption_rate = volume_flow_rate_STP / feed_stream_rate * turbine_consume_rate
        turbine_energy_consumption = self.gas.component_HHV_molar["C1"] * self.mol_to_scf * tot_turbine_consumption_rate

        compressor_consume_rate = ureg.Quantity(110519, "scf/hr")
        tot_compressor_consumption_rate = volume_flow_rate_STP / feed_stream_rate * compressor_consume_rate
        compressor_energy_consumption = self.gas.component_HHV_molar["C1"] * self.mol_to_scf * tot_compressor_consumption_rate

        hotoil_heater_consume_rate = ureg.Quantity(14589, "scf/hr")
        tot_heater_consumption_rate = volume_flow_rate_STP / feed_stream_rate * hotoil_heater_consume_rate
        heater_energy_consumption = self.gas.component_HHV_molar["C1"] * self.mol_to_scf * tot_heater_consumption_rate

        diesel_consume_rate = ureg.Quantity(57, "gal/day")
        tot_diesel_consumption_rate = volume_flow_rate_STP / feed_stream_rate * diesel_consume_rate * self.daily_use_engine
        diesel_energy_consumption = self.diesel_LHV * tot_diesel_consumption_rate

        # energy-use
        energy_use = self.energy
        energy_use.set_rate(EN_NATURAL_GAS, turbine_energy_consumption + compressor_energy_consumption + heater_energy_consumption)
        energy_use.set_rate(EN_DIESEL, diesel_energy_consumption)

        # emissions
        emissions = self.emissions
        energy_for_combustion = energy_use.data.drop("Electricity")
        combustion_emission = (energy_for_combustion * self.process_EF).sum()
        emissions.add_rate(EM_COMBUSTION, "CO2", combustion_emission)

        emissions.add_from_stream(EM_FUGITIVES, gas_fugitives)



