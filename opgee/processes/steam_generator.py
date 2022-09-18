#
# SteamGenerator class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
import pandas as pd

from opgee import ureg
from opgee.core import OpgeeObject


class SteamGenerator(OpgeeObject):
    def __init__(self, field):
        self.field = field
        model = field.model

        self.frac_steam_cogen = field.attr("fraction_steam_cogen")
        self.frac_steam_solar = field.attr("fraction_steam_solar")
        self.SOR = field.attr("SOR")
        self.oil_volume_rate = field.attr("oil_prod")
        self.steam_quality_outlet = field.attr("steam_quality_outlet")
        self.steam_quality_after_blowdown = field.attr("steam_quality_after_blowdown")
        self.fraction_blowdown_recycled = field.attr("fraction_blowdown_recycled")
        self.waste_water_reinjection_temp = field.attr("waste_water_reinjection_temp")
        self.waste_water_reinjection_press = field.attr("waste_water_reinjection_press")
        self.friction_loss_stream_distr = field.attr("friction_loss_stream_distr")
        self.pressure_loss_choke_wellhead = field.attr("pressure_loss_choke_wellhead")
        self.API = field.attr("API")

        self.res_press = field.attr("res_press")
        self.steam_injection_delta_press = field.attr("steam_injection_delta_press")

        # fraction are constrained in attributes.xml to be in range [0, 1]
        self.fraction_steam_cogen = field.attr("fraction_steam_cogen")
        self.fraction_steam_solar = field.attr("fraction_steam_solar")
        self.fraction_OTSG = 1 - self.fraction_steam_cogen - self.fraction_steam_solar

        self.prod_water_inlet_temp = field.attr("prod_water_inlet_temp")
        self.prod_water_inlet_press = field.attr("prod_water_inlet_press")
        self.makeup_water_inlet_temp = field.attr("makeup_water_inlet_temp")
        self.makeup_water_inlet_press = field.attr("makeup_water_inlet_press")
        self.temperature_inlet_air_OTSG = field.attr("temperature_inlet_air_OTSG")
        self.OTSG_exhaust_temp_outlet_before_economizer = field.attr(
            "OTSG_exhaust_temp_outlet_before_economizer")
        self.OTSG_exhaust_temp_series = field.attrs_with_prefix("OTSG_exhaust_temp_")
        self.HRSG_exhaust_temp_series = field.attrs_with_prefix("HRSG_exhaust_temp_")

        self.imported_fuel_gas_comp = field.imported_gas_comp["Imported Fuel"]
        self.processed_prod_gas_comp = field.imported_gas_comp["Processed Produced Gas"]
        self.inlet_air_comp = field.imported_gas_comp["Air"]

        self.OTSG_frac_import_gas = field.attr("OTSG_frac_import_gas")
        self.OTSG_frac_prod_gas = field.attr("OTSG_frac_prod_gas")
        self.HRSG_frac_import_gas = field.attr("HRSG_frac_import_gas")
        self.HRSG_frac_prod_gas = field.attr("HRSG_frac_prod_gas")
        self.O2_excess_OTSG = field.attr("O2_excess_OTSG")
        self.OTSG_fuel_type = field.attr("fuel_input_type_OTSG")
        self.loss_shell_OTSG = field.attr("loss_shell_OTSG")
        self.loss_shell_HRSG = field.attr("loss_shell_HRSG")
        self.loss_gaseous_OTSG = field.attr("loss_gaseous_OTSG")
        self.loss_liquid_OTSG = field.attr("loss_liquid_OTSG")

        self.blowdown_heat_recovery = field.attr("blowdown_heat_recovery")
        self.eta_blowdown_heat_rec_OTSG = field.attr("eta_blowdown_heat_rec_OTSG")
        self.eta_blowdown_heat_rec_HRSG = field.attr("eta_blowdown_heat_rec_HRSG")

        self.economizer_OTSG = field.attr("economizer_OTSG")
        self.preheater_OTSG = field.attr("preheater_OTSG")
        self.economizer_HRSG = field.attr("economizer_HRSG")
        self.preheater_HRSG = field.attr("preheater_HRSG")

        self.eta_economizer_heat_rec_OTSG = field.attr("eta_economizer_heat_rec_OTSG")
        self.eta_preheater_heat_rec_OTSG = field.attr("eta_preheater_heat_rec_OTSG")

        self.eta_economizer_heat_rec_HRSG = field.attr("eta_economizer_heat_rec_HRSG")
        self.eta_preheater_heat_rec_HRSG = field.attr("eta_preheater_heat_rec_HRSG")

        self.gas_turbine_type = field.attr("gas_turbine_type")
        self.duct_firing = field.attr("duct_firing")

        self.water = field.water
        self.oil = field.oil
        self.gas = field.gas

        self.prod_combustion_coeff = model.prod_combustion_coeff
        self.reaction_combustion_coeff = model.reaction_combustion_coeff
        self.gas_turbine_tlb = model.gas_turbine_tbl
        self.liquid_fuel_comp = self.oil.liquid_fuel_composition(self.API)
        self.steam_press_upper = model.const("steam-press-upper-limit")

        self.steam_generator_press_outlet = min((self.res_press + self.steam_injection_delta_press) *
                                                self.friction_loss_stream_distr *
                                                self.pressure_loss_choke_wellhead, self.steam_press_upper)

        self.steam_generator_temp_outlet = self.water.saturated_temperature(self.steam_generator_press_outlet)
        self.O2_excess_HRSG = self.gas_turbine_tlb["Turbine excess air"][self.gas_turbine_type]

        self.prod_gas_reactants_comp = self.get_combustion_comp(self.reaction_combustion_coeff,
                                                                self.processed_prod_gas_comp)

        self.prod_gas_products_comp = self.get_combustion_comp(self.prod_combustion_coeff, self.processed_prod_gas_comp)

        self.import_gas_reactants_comp = self.get_combustion_comp(self.reaction_combustion_coeff,
                                                                  self.imported_fuel_gas_comp)

        self.import_gas_products_comp = self.get_combustion_comp(self.prod_combustion_coeff,
                                                                 self.imported_fuel_gas_comp)

    def once_through_SG(self,
                        prod_water_mass_rate,
                        makeup_water_mass_rate,
                        water_mass_rate_for_injection,
                        blowdown_water_mass_rate):

        prod_water_enthalpy_rate = self.water.enthalpy_PT(self.prod_water_inlet_press,
                                                          self.prod_water_inlet_temp,
                                                          prod_water_mass_rate * self.fraction_OTSG)
        makeup_water_enthalpy_rate = self.water.enthalpy_PT(self.makeup_water_inlet_press,
                                                            self.makeup_water_inlet_temp,
                                                            makeup_water_mass_rate * self.fraction_OTSG)
        desired_steam_mass_rate = water_mass_rate_for_injection * self.fraction_OTSG
        desired_steam_enthalpy_rate = self.water.steam_enthalpy(self.steam_generator_press_outlet,
                                                                self.steam_quality_outlet,
                                                                desired_steam_mass_rate)
        blowdown_mass_rate = blowdown_water_mass_rate * self.fraction_OTSG
        blowdown_before_heat_recovery_enthalpy_rate = self.water.enthalpy_PT(self.steam_generator_press_outlet,
                                                                             self.steam_generator_temp_outlet,
                                                                             blowdown_mass_rate)
        blowdown_after_heat_recovery_enthalpy_rate = self.water.enthalpy_PT(self.waste_water_reinjection_press,
                                                                            self.waste_water_reinjection_temp,
                                                                            blowdown_mass_rate)
        recoverable_enthalpy_blowdown_water = self.eta_blowdown_heat_rec_OTSG * \
                                              (blowdown_before_heat_recovery_enthalpy_rate -
                                               blowdown_after_heat_recovery_enthalpy_rate) \
            if self.blowdown_heat_recovery else ureg.Quantity(0.0, "MJ/day")
        steam_out_enthalpy_rate = desired_steam_enthalpy_rate + blowdown_before_heat_recovery_enthalpy_rate
        # OTSG combustion
        gas_combusted = (self.imported_fuel_gas_comp * self.OTSG_frac_import_gas +
                         self.processed_prod_gas_comp * self.OTSG_frac_prod_gas)
        gas_MW_combust = self.gas.molar_weight_from_molar_fracs(gas_combusted)
        gas_LHV = self.gas.mass_energy_density_from_molar_fracs(gas_combusted)

        air_requirement_fuel, air_requirement_MW, air_requirement_LHV_fuel, air_requirement_LHV_stream = \
            self.get_air_requirement(gas_MW_combust, "OTSG")
        exhaust_consump, exhaust_consump_sum, exhaust_consump_MW = self.get_exhaust_parameters(
            air_requirement_fuel, "OTSG")

        LHV_fuel, LHV_stream = self.get_LHV_fuel_and_stream_series(exhaust_consump,
                                                                   self.OTSG_exhaust_temp_series,
                                                                   gas_MW_combust,
                                                                   exhaust_consump_sum,
                                                                   exhaust_consump_MW)
        exhaust_consump = exhaust_consump.drop(labels=["C1"])
        input_enthalpy_per_unit_fuel = (
                gas_LHV + air_requirement_LHV_fuel - LHV_fuel["outlet_before_economizer"])
        shell_loss_per_unit_fuel = self.loss_shell_OTSG * gas_LHV if self.OTSG_fuel_type == "Gas" else self.loss_shell_OTSG * self.oil.mass_energy_density()
        other_loss_per_unit_fuel = self.loss_gaseous_OTSG / gas_MW_combust if self.OTSG_fuel_type == "Gas" else self.loss_liquid_OTSG
        available_enthalpy = max(input_enthalpy_per_unit_fuel -
                                 shell_loss_per_unit_fuel -
                                 other_loss_per_unit_fuel, 0)

        # TODO: Wennan, lots of redundancy here you can extract to a common factor
        # calculate recoverable heat
        delta_H = steam_out_enthalpy_rate - prod_water_enthalpy_rate - makeup_water_enthalpy_rate - recoverable_enthalpy_blowdown_water
        constant_before_economizer = exhaust_consump_sum * exhaust_consump_MW / \
                                     gas_MW_combust * LHV_stream["outlet_before_economizer"] / available_enthalpy
        constant_before_preheater = exhaust_consump_sum * exhaust_consump_MW / \
                                    gas_MW_combust * LHV_stream["outlet_before_preheater"] / available_enthalpy
        constant_outlet = exhaust_consump_sum * exhaust_consump_MW / gas_MW_combust * LHV_stream[
            "outlet"] / available_enthalpy

        eta_eco = self.eta_economizer_heat_rec_OTSG
        eta_heater = self.eta_preheater_heat_rec_OTSG

        # TODO: Write a local function and call it twice since the form of these expression is the same.
        #       def xxx(value): return value / (1 + value). Not sure what a good name would be.
        d_eco = eta_eco * (constant_before_economizer - constant_before_preheater) / \
                (1 + eta_eco * (constant_before_economizer - constant_before_preheater))
        d_heater = eta_heater * (constant_outlet - constant_before_preheater) / \
                   (1 + eta_heater * (constant_outlet - constant_before_preheater))

        # TODO: as above
        recoverable_heat_before_economizer = ureg.Quantity(0.0, "MJ/day") if not self.economizer_OTSG else \
            (d_eco - d_eco * d_heater) * delta_H / (1 - d_eco * d_heater)
        recoverable_heat_before_preheater = ureg.Quantity(0.0, "MJ/day") if not self.economizer_OTSG else \
            (d_heater - d_eco * d_heater) * delta_H / (1 - d_eco * d_heater)

        fuel_demand_for_steam_enthalpy_change = delta_H - recoverable_heat_before_economizer - recoverable_heat_before_preheater
        fuel_consumption_for_steam_generation_mass = fuel_demand_for_steam_enthalpy_change / available_enthalpy
        fuel_LHV = gas_LHV if self.OTSG_fuel_type == "Gas" else self.oil.mass_energy_density(API=self.oil.API,
                                                                                             with_unit=True)
        fuel_consumption_for_steam_generation_energy = fuel_consumption_for_steam_generation_mass * fuel_LHV

        # mass and energy balance
        air_in_mass_rate = air_requirement_fuel.sum() * self.gas.molar_weight_from_molar_fracs(
            self.inlet_air_comp) * fuel_consumption_for_steam_generation_mass
        air_in_mass_rate = air_in_mass_rate / gas_MW_combust if self.OTSG_fuel_type == "Gas" else air_in_mass_rate

        outlet_exhaust_mass = exhaust_consump_sum * exhaust_consump_MW * fuel_consumption_for_steam_generation_mass
        outlet_exhaust_mass = outlet_exhaust_mass / gas_MW_combust if self.OTSG_fuel_type == "Gas" else outlet_exhaust_mass

        temp = delta_H - recoverable_heat_before_economizer - recoverable_heat_before_preheater
        H_eco = constant_before_economizer * temp
        H_heater = constant_before_preheater * temp
        H_outlet = constant_outlet * temp

        mass_in = fuel_consumption_for_steam_generation_mass + air_in_mass_rate + \
                  prod_water_mass_rate + makeup_water_mass_rate
        mass_out = prod_water_mass_rate + makeup_water_mass_rate + outlet_exhaust_mass

        energy_in = fuel_consumption_for_steam_generation_mass * gas_LHV + \
                    air_in_mass_rate * air_requirement_LHV_stream + \
                    prod_water_enthalpy_rate + makeup_water_enthalpy_rate
        energy_out = outlet_exhaust_mass * LHV_stream["outlet"] + \
                     (H_heater - H_outlet - recoverable_heat_before_preheater) + \
                     (H_eco - H_heater - recoverable_heat_before_economizer) + \
                     fuel_consumption_for_steam_generation_mass * other_loss_per_unit_fuel + \
                     fuel_consumption_for_steam_generation_mass * shell_loss_per_unit_fuel + desired_steam_enthalpy_rate + \
                     (blowdown_before_heat_recovery_enthalpy_rate - recoverable_enthalpy_blowdown_water)

        return fuel_consumption_for_steam_generation_energy, mass_in, mass_out, energy_in, energy_out

    def heat_recovery_SG(self,
                         prod_water_mass_rate,
                         makeup_water_mass_rate,
                         water_mass_rate_for_injection,
                         blowdown_water_mass_rate):

        # TODO: Wennan, I'm think we need a 'ThermoState' object to hold temperature and pressure. (Not sure that's
        #       the best name though.) It would simplify the many function calls that pass the two together.
        prod_water_enthalpy_rate = self.water.enthalpy_PT(self.prod_water_inlet_press,
                                                          self.prod_water_inlet_temp,
                                                          prod_water_mass_rate * self.fraction_steam_cogen)
        makeup_water_enthalpy_rate = self.water.enthalpy_PT(self.makeup_water_inlet_press,
                                                            self.makeup_water_inlet_temp,
                                                            makeup_water_mass_rate * self.fraction_steam_cogen)
        desired_steam_mass_rate = water_mass_rate_for_injection * self.fraction_steam_cogen
        desired_steam_enthalpy_rate = self.water.steam_enthalpy(self.steam_generator_press_outlet,
                                                                self.steam_quality_outlet,
                                                                desired_steam_mass_rate)
        blowdown_mass_rate = blowdown_water_mass_rate * self.fraction_steam_cogen
        blowdown_before_heat_recovery_enthalpy_rate = self.water.enthalpy_PT(self.steam_generator_press_outlet,
                                                                             self.steam_generator_temp_outlet,
                                                                             blowdown_mass_rate)
        blowdown_after_heat_recovery_enthalpy_rate = self.water.enthalpy_PT(self.waste_water_reinjection_press,
                                                                            self.waste_water_reinjection_temp,
                                                                            blowdown_mass_rate)
        recoverable_enthalpy_blowdown_water = self.eta_blowdown_heat_rec_HRSG * \
                                              (blowdown_before_heat_recovery_enthalpy_rate -
                                               blowdown_after_heat_recovery_enthalpy_rate) \
            if self.blowdown_heat_recovery else ureg.Quantity(0.0, "MJ/day")

        steam_out_enthalpy_rate = desired_steam_enthalpy_rate + blowdown_before_heat_recovery_enthalpy_rate

        # GT + HRSG combustion
        gas_combusted = (self.imported_fuel_gas_comp * self.HRSG_frac_import_gas +
                         self.processed_prod_gas_comp * self.HRSG_frac_prod_gas)
        gas_MW_combust = self.gas.molar_weight_from_molar_fracs(gas_combusted)
        gas_LHV = self.gas.mass_energy_density_from_molar_fracs(gas_combusted)

        air_requirement_fuel, air_requirement_MW, air_requirement_LHV_fuel, air_requirement_LHV_stream = \
            self.get_air_requirement(gas_MW_combust, "HRSG")
        exhaust_consump, exhaust_consump_sum, exhaust_consump_MW = self.get_exhaust_parameters(
            air_requirement_fuel, "HRSG")

        temp = exhaust_consump * \
               self.gas.combustion_enthalpy(exhaust_consump,
                                            self.gas_turbine_tlb["Turbine exhaust temp."][self.gas_turbine_type])
        exhaust_consump_LHV_fuel = temp.sum() / gas_MW_combust
        exhaust_consump_LHV_stream = temp.sum() / exhaust_consump_MW / exhaust_consump_sum
        exhaust_consump = exhaust_consump.drop(labels=["C1"])

        inlet_temp = ureg.Quantity(1300.0, "degF") if self.duct_firing else \
            self.gas_turbine_tlb["Turbine exhaust temp."][self.gas_turbine_type]

        if self.duct_firing:
            inlet, inlet_sum, inlet_MW, inlet_LHV_fuel, inlet_LHV_stream, duct_additional_fuel = \
                self.get_HRSG_inlet_combustion(inlet_temp, gas_MW_combust, gas_LHV, exhaust_consump,
                                               exhaust_consump_LHV_fuel)
        else:
            inlet, inlet_sum, inlet_MW, inlet_LHV_fuel, inlet_LHV_stream, duct_additional_fuel = \
                exhaust_consump, exhaust_consump_sum, exhaust_consump_MW, exhaust_consump_LHV_fuel, \
                exhaust_consump_LHV_stream, ureg.Quantity(0.0, "frac")

        LHV_fuel, LHV_stream = self.get_LHV_fuel_and_stream_series(inlet,
                                                                   self.HRSG_exhaust_temp_series,
                                                                   gas_MW_combust,
                                                                   inlet_sum,
                                                                   inlet_MW)

        # recoverable heat in economizer
        delta_H = steam_out_enthalpy_rate - prod_water_enthalpy_rate - makeup_water_enthalpy_rate - \
                  recoverable_enthalpy_blowdown_water
        eta_eco = self.eta_economizer_heat_rec_HRSG
        eta_heater = self.eta_preheater_heat_rec_HRSG
        frac_loss = self.loss_shell_HRSG * (inlet_LHV_stream - LHV_stream["outlet_before_economizer"]) / \
                    inlet_LHV_stream
        frac_exhaust = LHV_stream["outlet_before_economizer"] / inlet_LHV_stream
        frac_steam = 1 - frac_loss - frac_exhaust
        const_eco = LHV_stream["outlet_before_economizer"] / inlet_LHV_stream / frac_steam
        const_heater = LHV_stream["outlet_before_preheater"] / inlet_LHV_stream / frac_steam
        denominator = 1 - eta_eco * const_heater + eta_eco * const_eco
        H_eco = const_eco * delta_H / denominator
        H_heater = const_heater * delta_H / denominator
        recoverable_heat_before_economizer = ((H_eco - H_heater) * eta_eco if
                                              self.economizer_HRSG else ureg.Quantity(0.0, "MJ/day"))
        H_fuel_inlet_HRSG = (delta_H - recoverable_heat_before_economizer) / frac_steam
        mass_fuel_inlet_HRSG = H_fuel_inlet_HRSG / inlet_LHV_stream
        recoverable_heat_before_preheater = (mass_fuel_inlet_HRSG *
                                            (LHV_stream["outlet"] -
                                             LHV_stream["outlet_before_preheater"]) *
                                            eta_heater if self.preheater_HRSG else ureg.Quantity(0.0, "MJ/day"))

        GT_frac_electricity = self.gas_turbine_tlb["Turbine efficiency"][self.gas_turbine_type]
        GT_frac_loss = self.gas_turbine_tlb["Turbine loss"][self.gas_turbine_type]
        GT_frac_thermal = 1 - GT_frac_loss - GT_frac_electricity
        H_exhaust_GT = H_fuel_inlet_HRSG / (GT_frac_thermal + duct_additional_fuel) * GT_frac_thermal
        mass_exhaust_GT = H_exhaust_GT / exhaust_consump_LHV_stream
        H_electricty_GT = H_exhaust_GT / GT_frac_thermal * GT_frac_electricity
        H_loss_GT = H_exhaust_GT / GT_frac_thermal * GT_frac_loss

        H_fuel_inlet_GT = H_loss_GT + H_electricty_GT + H_exhaust_GT - recoverable_heat_before_preheater
        mass_fuel_inlet_GT = H_fuel_inlet_GT / gas_LHV
        H_duct_firing = H_fuel_inlet_HRSG - H_exhaust_GT
        total_fuel_comsumption = H_fuel_inlet_GT + H_duct_firing

        # balance check
        mass_air_GT = mass_exhaust_GT - mass_fuel_inlet_GT
        H_air_GT = mass_air_GT * air_requirement_LHV_stream
        mass_in = mass_air_GT + mass_fuel_inlet_GT + mass_fuel_inlet_HRSG + prod_water_mass_rate + makeup_water_mass_rate
        mass_out = mass_exhaust_GT + mass_fuel_inlet_HRSG + prod_water_mass_rate + makeup_water_mass_rate
        energy_in = H_air_GT + H_fuel_inlet_GT + recoverable_heat_before_preheater + \
                    prod_water_enthalpy_rate + makeup_water_enthalpy_rate + H_fuel_inlet_HRSG
        energy_out = H_electricty_GT + H_exhaust_GT + H_loss_GT + H_eco - recoverable_heat_before_economizer + \
                     H_fuel_inlet_HRSG * frac_loss + desired_steam_enthalpy_rate + \
                     blowdown_before_heat_recovery_enthalpy_rate - recoverable_enthalpy_blowdown_water

        return total_fuel_comsumption, H_electricty_GT, mass_in, mass_out, energy_in, energy_out

    def solar_SG(self,
                 prod_water_mass_rate,
                 makeup_water_mass_rate):

        prod_water_enthalpy_rate = self.water.enthalpy_PT(self.prod_water_inlet_press,
                                                          self.prod_water_inlet_temp,
                                                          prod_water_mass_rate * self.frac_steam_solar)
        makeup_water_enthalpy_rate = self.water.enthalpy_PT(self.makeup_water_inlet_press,
                                                            self.makeup_water_inlet_temp,
                                                            makeup_water_mass_rate * self.frac_steam_solar)
        desired_steam_mass_rate = (prod_water_mass_rate + makeup_water_mass_rate) * self.frac_steam_solar
        desired_steam_enthalpy_rate = self.water.steam_enthalpy(self.steam_generator_press_outlet,
                                                                self.steam_quality_outlet,
                                                                desired_steam_mass_rate)
        H_solar_inlet = desired_steam_enthalpy_rate - prod_water_enthalpy_rate - makeup_water_enthalpy_rate
        return H_solar_inlet

    @staticmethod
    def get_combustion_comp(coeff_table, gas_comp):
        """
        calculate reaction gas comp using combustion table and gas comp

        :param coeff_table:
        :param gas_comp:
        :return: (float) Pandas Series, reaction gas comp
        """
        table = coeff_table.loc[gas_comp.index, :]
        table = table.transpose()
        result = table.dot(gas_comp)

        return result

    def get_LHV_fuel_and_stream_series(self, comp_series, temp_series, fuel_MW, comp_series_sum, comp_series_MW):
        """
        calculate exhaust LHV fuel and stream using exhaust composition, temperature series and fuel mol_weight

        :param comp_series_MW:
        :param comp_series_sum:
        :param fuel_MW:
        :param comp_series:
        :param temp_series:
        :return: (float) LHV fuel series and LHV stream series
        """

        LHV_fuel = pd.Series(dtype="pint[joule/gram]")
        LHV_stream = pd.Series(dtype="pint[joule/gram]")

        for name in temp_series.index:
            temp = (comp_series * self.gas.combustion_enthalpy(comp_series, temp_series[name])).sum()
            LHV_fuel[name] = temp / fuel_MW
            LHV_stream[name] = temp / comp_series_sum / comp_series_MW

        return LHV_fuel, LHV_stream

    def get_air_requirement(self, gas_MW_combust, SG_type):
        """
        Get inlet air requirements such as inlet air composition, air LHV (fuel) and air LHV(stream)

        :param gas_MW_combust:
        :param SG_type:
        :return: (float, Pandas.Series) air_requirement_fuel; (float) air_requirement_LHV_fuel (unit = MJ/kg)
        """

        if SG_type == "OTSG":
            if self.OTSG_fuel_type == "Gas":
                air_requirement_fuel = (self.OTSG_frac_import_gas * self.import_gas_reactants_comp
                                        + self.OTSG_frac_prod_gas * self.prod_gas_reactants_comp) * self.O2_excess_OTSG
            else:
                air_requirement_fuel = (self.liquid_fuel_comp["C"] + 0.25 * self.liquid_fuel_comp["H"] +
                                        self.liquid_fuel_comp["S"]) * self.O2_excess_OTSG / self.inlet_air_comp[
                                           "O2"] * self.inlet_air_comp
        else:
            air_requirement_fuel = (self.HRSG_frac_import_gas * self.import_gas_reactants_comp
                                    + self.HRSG_frac_prod_gas * self.prod_gas_reactants_comp) * self.O2_excess_HRSG

        air_requirement_fuel_sum = ureg.Quantity(air_requirement_fuel.sum(), "percent")
        air_requirement_fuel["C1"] = 100
        air_requirement_fuel = pd.Series(air_requirement_fuel, dtype="pint[percent]")
        air_requirement_MW = self.gas.molar_weight_from_molar_fracs(
            air_requirement_fuel.drop(labels=["C1"])) / air_requirement_fuel.drop(labels=["C1"]).sum()
        temp = air_requirement_fuel * self.gas.combustion_enthalpy(air_requirement_fuel,
                                                                   self.temperature_inlet_air_OTSG)
        air_requirement_LHV_fuel = temp.sum() / gas_MW_combust
        air_requirement_LHV_stream = temp.sum() / air_requirement_MW / air_requirement_fuel_sum
        air_requirement_fuel = air_requirement_fuel.drop(labels=["C1"])

        return air_requirement_fuel, air_requirement_MW, air_requirement_LHV_fuel, air_requirement_LHV_stream

    def get_exhaust_parameters(self, air_requirement_fuel, SG_type):

        if SG_type == "OTSG":
            if self.OTSG_fuel_type == "Gas":
                exhaust_consump = (self.OTSG_frac_import_gas * self.import_gas_products_comp +
                                   self.OTSG_frac_prod_gas * self.prod_gas_products_comp) + (
                                          self.O2_excess_OTSG - 1) / self.O2_excess_OTSG * air_requirement_fuel
            else:
                exhaust_consump = air_requirement_fuel + 0.5 * self.liquid_fuel_comp
                exhaust_consump["O2"] = air_requirement_fuel["O2"] - self.liquid_fuel_comp["C"] - 0.25 * \
                                        self.liquid_fuel_comp["H"] - self.liquid_fuel_comp["S"]
                exhaust_consump["CO2"] = air_requirement_fuel["CO2"] + self.liquid_fuel_comp["C"]
        else:
            exhaust_consump = (self.HRSG_frac_import_gas * self.import_gas_products_comp
                               + self.HRSG_frac_prod_gas * self.prod_gas_products_comp) + \
                              (self.O2_excess_HRSG - 1) / self.O2_excess_HRSG * air_requirement_fuel
        exhaust_consump_sum = exhaust_consump.sum()
        exhaust_consump["C1"] = ureg.Quantity(100.0, "percent")
        exhaust_consump = pd.Series(exhaust_consump, dtype="pint[percent]")
        exhaust_consump_MW = self.gas.molar_weight_from_molar_fracs(
            exhaust_consump.drop(labels=["C1"])) / exhaust_consump.drop(labels=["C1"]).sum()

        return exhaust_consump, exhaust_consump_sum, exhaust_consump_MW

    def get_HRSG_inlet_combustion(self, inlet_temp, gas_MW_combust, gas_LHV, exhaust_consump, exhaust_consump_LHV_fuel):

        tolerance = 1E-6
        duct_additional_fuel = 0.4
        delta_error = duct_additional_fuel

        while delta_error > tolerance:
            O2_excess_duct = (self.O2_excess_HRSG.m - 1) / duct_additional_fuel
            HRSG_inlet = (self.HRSG_frac_import_gas * self.import_gas_products_comp
                          + self.HRSG_frac_prod_gas * self.prod_gas_products_comp) + \
                         (O2_excess_duct - 1) / O2_excess_duct * exhaust_consump
            HRSG_inlet_sum = HRSG_inlet.sum()
            HRSG_inlet["C1"] = ureg.Quantity(100.0, "percent")
            HRSG_inlet = pd.Series(HRSG_inlet, dtype="pint[percent]")
            HRSG_inlet_MW = self.gas.molar_weight_from_molar_fracs(
                HRSG_inlet.drop(labels=["C1"])) / HRSG_inlet.drop(labels=["C1"]).sum()

            temp = HRSG_inlet * self.gas.combustion_enthalpy(HRSG_inlet, inlet_temp)
            HRSG_inlet_LHV_fuel = temp.sum() / gas_MW_combust
            HRSG_inlet_LHV_stream = temp.sum() / HRSG_inlet_MW / HRSG_inlet_sum

            duct_additional_fuel_new = (HRSG_inlet_LHV_fuel.to("MJ/kg").m - exhaust_consump_LHV_fuel.to("MJ/kg").m) / \
                                       gas_LHV.to("MJ/kg").m
            delta_error = (duct_additional_fuel_new - duct_additional_fuel) ** 2
            duct_additional_fuel = duct_additional_fuel_new

        HRSG_inlet = HRSG_inlet.drop(labels=["C1"])

        return HRSG_inlet, HRSG_inlet_sum, HRSG_inlet_MW, HRSG_inlet_LHV_fuel, HRSG_inlet_LHV_stream, duct_additional_fuel
