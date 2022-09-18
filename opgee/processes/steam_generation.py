#
# SteamGeneration class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
from .shared import get_energy_consumption
from ..core import TemperaturePressure
from ..emissions import EM_COMBUSTION
from ..energy import EN_NATURAL_GAS, EN_ELECTRICITY
from ..error import BalanceError
from ..error import OpgeeException
from ..log import getLogger
from ..process import Process

_logger = getLogger(__name__)

# the tolerance is used for checking mass and energy balance
# (input - output) / input < tolerance
tolerance = 0.01


class SteamGeneration(Process):
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()
        self.steam_flooding_check = field.attr("steam_flooding")

        if self.steam_flooding_check != 1:
            self.set_enabled(False)
            return

        self.SOR = field.attr("SOR")
        self.oil_volume_rate = field.attr("oil_prod")
        self.steam_quality_outlet = self.attr("steam_quality_outlet")
        self.steam_quality_after_blowdown = self.attr("steam_quality_after_blowdown")
        self.fraction_blowdown_recycled = self.attr("fraction_blowdown_recycled")

        self.waste_water_reinjection_tp = TemperaturePressure(self.attr("waste_water_reinjection_temp"),
                                                              self.attr("waste_water_reinjection_press"))

        self.friction_loss_stream_distr = self.attr("friction_loss_stream_distr")
        self.pressure_loss_choke_wellhead = self.attr("pressure_loss_choke_wellhead")
        self.water = field.water
        self.water_density = self.water.density()
        self.res_press = field.attr("res_press")
        self.steam_press_upper = field.model.const("steam-press-upper-limit")
        self.steam_injection_delta_press = self.attr("steam_injection_delta_press")
        self.steam_generator_press_outlet = min((self.res_press + self.steam_injection_delta_press) *
                                                self.friction_loss_stream_distr *
                                                self.pressure_loss_choke_wellhead, self.steam_press_upper)
        self.steam_generator_temp_outlet = self.water.saturated_temperature(self.steam_generator_press_outlet)
        self.prod_water_inlet_press = self.attr("prod_water_inlet_press")
        self.makeup_water_inlet_press = self.attr("makeup_water_inlet_press")
        self.eta_displacementpump_steamgen = self.attr("eta_displacementpump_steamgen")
        self.eta_air_blower_OTSG = self.attr("eta_air_blower_OTSG")
        self.eta_air_blower_HRSG = self.attr("eta_air_blower_HRSG")
        self.eta_air_blower_solar = self.attr("eta_air_blower_solar")

        # TODO: the SteamGenerator is instantiated only here, in Field, yet it is used only
        #       in the SteamGeneration process. Is the SteamGenerator intended to be used by
        #       other processes? If not, this, why not move its methods into SteamGeneration?
        #       The only methods SteamGenerator called in SteamGeneration are called once each,
        #       in run().
        self.steam_generator = field.steam_generator

    def run(self, analysis):
        self.print_running_msg()
        self.set_iteration_value(0)
        field = self.field

        if self.SOR.m == 0:
            raise OpgeeException(f"Steam-oil-ratio is zero in the {self.name} process")

        # mass rate
        steam_injection_volume_rate = self.SOR * self.oil_volume_rate
        water_mass_rate_for_injection = steam_injection_volume_rate * self.water_density
        blowdown_water_mass_rate = water_mass_rate_for_injection * (
                self.steam_quality_after_blowdown - self.steam_quality_outlet) / self.steam_quality_outlet
        waste_water_from_blowdown = blowdown_water_mass_rate * (1 - self.fraction_blowdown_recycled)
        recycled_blowdown_water = blowdown_water_mass_rate * self.fraction_blowdown_recycled

        output_waste_water = self.find_output_stream("waste water")
        output_waste_water.set_liquid_flow_rate("H2O",
                                                waste_water_from_blowdown.to("tonne/day"),
                                                tp=self.waste_water_reinjection_tp)
        #TODO: output it to the production boundary
        # if recycled_blowdown_water.m != 0:
        #     output_recycled_blowdown_water = self.find_output_stream("blowdown water")
        #     output_recycled_blowdown_water.set_liquid_flow_rate("H2O", recycled_blowdown_water.to("tonne/day"),
        #                                                         tp=self.waste_water_reinjection_tp)

        input_prod_water = self.find_input_stream("produced water for steam generation")
        if input_prod_water.is_uninitialized():
            return
        prod_water_mass_rate = input_prod_water.liquid_flow_rate("H2O")

        input_makeup_water = self.find_input_stream("makeup water for steam generation")
        makeup_water_mass_rate = input_makeup_water.liquid_flow_rate("H2O")

        makeup_water_to_prod_water_frac = makeup_water_mass_rate / prod_water_mass_rate

        fuel_consumption_OTSG, mass_in_OTSG, mass_out_OTSG, energy_in_OTSG, energy_out_OTSG = \
            self.steam_generator.once_through_SG(prod_water_mass_rate,
                                                 makeup_water_mass_rate,
                                                 water_mass_rate_for_injection,
                                                 blowdown_water_mass_rate)
        fuel_consumption_HRSG, electricity_HRSG, mass_in_HRSG, mass_out_HRSG, energy_in_HRSG, energy_out_HRSG = \
            self.steam_generator.heat_recovery_SG(prod_water_mass_rate,
                                                  makeup_water_mass_rate,
                                                  water_mass_rate_for_injection,
                                                  blowdown_water_mass_rate)

        fuel_consumption_solar = self.steam_generator.solar_SG(prod_water_mass_rate, makeup_water_mass_rate)

        self.check_balance(mass_in_OTSG, mass_out_OTSG, "OTSG_mass")
        self.check_balance(mass_in_HRSG, mass_out_HRSG, "HRSG_mass")
        self.check_balance(energy_in_OTSG, energy_out_OTSG, "OTSG_energy")
        self.check_balance(energy_in_HRSG, energy_out_HRSG, "HRSG_energy")

        # energy use
        energy_use = self.energy
        NG_consumption = fuel_consumption_OTSG + fuel_consumption_HRSG + fuel_consumption_solar
        energy_use.set_rate(EN_NATURAL_GAS, NG_consumption.to("mmBtu/day"))

        water_pump_hp = self.get_feedwater_horsepower(steam_injection_volume_rate, makeup_water_to_prod_water_frac)
        water_pump_power = get_energy_consumption("Electric_motor", water_pump_hp)
        OTSG_air_blower = get_energy_consumption("Electric_motor",
                                                 fuel_consumption_OTSG * self.eta_air_blower_OTSG)
        HRSG_air_blower = get_energy_consumption("Electric_motor",
                                                 fuel_consumption_HRSG * self.eta_air_blower_HRSG)
        solar_thermal_pumping = get_energy_consumption("Electric_motor",
                                                       fuel_consumption_solar * self.eta_air_blower_solar)
        total_power_required = water_pump_power + OTSG_air_blower + HRSG_air_blower + solar_thermal_pumping
        energy_use.set_rate(EN_ELECTRICITY, total_power_required - electricity_HRSG.to("mmBtu/day"))

        # import/export
        # import_product = field.import_export
        self.set_import_from_energy(energy_use)

        emissions = self.emissions
        energy_for_combustion = energy_use.data.drop("Electricity")
        combustion_emission = (energy_for_combustion * self.process_EF).sum()
        emissions.set_rate(EM_COMBUSTION, "CO2", combustion_emission)

    def get_feedwater_horsepower(self, steam_injection_volume_rate, makeup_water_to_prod_water_frac):
        result = steam_injection_volume_rate * makeup_water_to_prod_water_frac * (
                self.steam_generator_press_outlet - self.makeup_water_inlet_press) + \
                 steam_injection_volume_rate * (1 - makeup_water_to_prod_water_frac) * (
                         self.steam_generator_press_outlet - self.prod_water_inlet_press)
        result /= self.eta_displacementpump_steamgen

        return result

    def check_balance(self, input, output, label):
        """

        :param input:
        :param output:
        :param label:
        :return:
        """

        unit = input.units
        if abs(input.m - output.to(unit).m) > tolerance * input.m:
            raise BalanceError(self.name, label)
