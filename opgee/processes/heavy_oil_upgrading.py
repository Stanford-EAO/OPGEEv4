#
# HeavyOilUpgrading class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
import pandas as pd

from .. import ureg
from ..core import STP
from ..emissions import EM_COMBUSTION, EM_FLARING
from ..energy import EN_NATURAL_GAS, EN_ELECTRICITY, EN_UPG_PROC_GAS, EN_PETCOKE
from ..log import getLogger
from ..process import Process
from ..stream import PHASE_GAS
from ..stream import Stream

_logger = getLogger(__name__)


class HeavyOilUpgrading(Process):
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()
        self.oil = self.field.oil
        self.water = self.field.water
        self.upgrader_gas_comp = field.imported_gas_comp["Upgrader Gas"]
        self.oil_sands_mine = field.attr("oil_sands_mine")
        self.fraction_elec_onsite = field.attr("fraction_elec_onsite")
        self.cogeneration_upgrading = self.attr("cogeneration_upgrading")
        self.NG_heating_value = self.model.const("NG-heating-value")
        self.petro_coke_heating_value = self.model.const("petrocoke-heating-value")
        self.mole_to_scf = self.model.const("mol-per-scf")
        self.upgrader_type = field.attr("upgrader_type")
        self.water = self.field.water
        self.water_density = self.water.density()

        self.upgrading_insitu_oil = True \
            if self.upgrader_type != "None" and \
               self.oil_sands_mine != "Non-integrated with upgrader" else False

    def run(self, analysis):
        self.print_running_msg()
        field = self.field

        # mass rate
        input_oil = self.find_input_stream("oil for upgrading", raiseError=False)
        input_bitumen = self.find_input_stream("bitumen for upgrading", raiseError=False)

        if self.upgrader_type == "None":
            return

        if input_oil is None and input_bitumen is None:
            return

        if (input_oil is not None and input_oil.is_uninitialized()) and\
                (input_bitumen is not None and input_bitumen.is_uninitialized()):
            return

        df = self.model.heavy_oil_upgrading
        totals = df.query("Fraction == 'total'")
        d = {}
        for i, row in totals.iterrows():
            item = row.Items
            fractions = df.query("Fraction != 'total' and Items == @item")[["Fraction", self.upgrader_type, "Unit"]]
            total = totals.query("Items==@item")[self.upgrader_type]
            frac_with_unit = pd.Series(fractions.set_index("Fraction")[self.upgrader_type], dtype="pint[frac]")
            d[item] = frac_with_unit * ureg.Quantity(total.values[0], row.Unit)

        heavy_oil_upgrading_table = df[self.upgrader_type]
        heavy_oil_upgrading_table.index = df["Items"]

        upgrader_process_gas_MW = (self.upgrader_gas_comp * self.oil.component_MW[self.upgrader_gas_comp.index]).sum()
        upgrader_process_gas_heating_value = (self.upgrader_gas_comp *
                                              self.oil.component_LHV_molar[self.upgrader_gas_comp.index] *
                                              self.mole_to_scf).sum()
        SCO_bitumen_ratio = heavy_oil_upgrading_table["SCO/bitumen ratio"]

        field.save_process_data(SCO_bitumen_ratio=SCO_bitumen_ratio) # used in the Flaring process

        SCO_API = heavy_oil_upgrading_table["API gravity of resuling upgraded product output"]
        SCO_specific_gravity = field.oil.specific_gravity(SCO_API)

        oil_mass_rate = input_oil.liquid_flow_rate("oil") if input_oil is not None else ureg.Quantity(0.0, "tonne/day")
        oil_vol_rate = oil_mass_rate / (self.oil.oil_specific_gravity * self.water.density())
        bitumen_mass_rate =\
            input_bitumen.liquid_flow_rate("oil") if input_bitumen is not None else ureg.Quantity(0.0, "tonne/day")
        bitumen_vol_rate = bitumen_mass_rate / (self.oil.oil_specific_gravity * self.water.density())
        if self.upgrading_insitu_oil:
            SCO_output = (bitumen_vol_rate + oil_vol_rate) * SCO_bitumen_ratio
        else:
            if self.oil_sands_mine == "Integrated with upgrader":
                SCO_output = SCO_bitumen_ratio * oil_vol_rate
            else:
                SCO_output = ureg.Quantity(0.0, "bbl/day")

        SCO_output_mass_rate = SCO_output * SCO_specific_gravity * self.water_density
        SCO_to_storage = self.find_output_stream("oil for storage")
        SCO_to_storage.set_liquid_flow_rate("oil", SCO_output_mass_rate)

        coke_dict = d["Coke yield per bbl SCO output"] * SCO_output
        coke_to_stockpile_and_transport = coke_dict["Fraction coke exported"] + coke_dict["Fraction coke stockpiled"]
        coke_to_heat = coke_dict["Fraction coke to self use - Heating"]

        if self.field.get_process_data("frac_coke_exported") is None:
            self.field.save_process_data(
                frac_coke_exported=d["Coke yield per bbl SCO output"]["Fraction coke exported"])

        coke_to_transport = self.find_output_stream("petrocoke")
        coke_to_transport.set_solid_flow_rate("PC", coke_to_stockpile_and_transport)

        proc_gas_dict = d["Process gas (PG) yield per bbl SCO output"] * SCO_output
        proc_gas_to_heat = proc_gas_dict["Fraction PG to self use - Heating (W/O cogen)"]
        proc_gas_to_H2 = proc_gas_dict["Fraction PG to self use - H2 gen"]
        proc_gas_exported = proc_gas_dict["Fraction PG exported"]
        proc_gas_flared = proc_gas_dict["Fraction PG flared"]

        output_proc_gas = Stream("process_gas", tp=self.field.stp)
        proc_gas_mass_rate = (self.upgrader_gas_comp *
                              self.oil.component_MW[self.upgrader_gas_comp.index] *
                              proc_gas_exported *
                              self.mole_to_scf)
        output_proc_gas.set_rates_from_series(proc_gas_mass_rate, PHASE_GAS)

        electricity_yield = ureg.Quantity(heavy_oil_upgrading_table["Electricity intensity"], "kWh/bbl_oil")
        frac_electricity_self_gene = self.fraction_elec_onsite * self.cogeneration_upgrading
        elect_cogen = SCO_output * frac_electricity_self_gene * electricity_yield
        elect_import = SCO_output * electricity_yield * (1 - frac_electricity_self_gene)

        NG_dict = d["Natural gas intensity (W/O cogen)"] * SCO_output
        NG_to_cogen_yield = frac_electricity_self_gene * electricity_yield / \
                            heavy_oil_upgrading_table["Cogen turbine efficiency"] / self.NG_heating_value
        NG_to_H2 = NG_dict["Fraction NG - H2"]
        NG_to_cogen = NG_to_cogen_yield * SCO_output
        heat_from_cogen = NG_to_cogen * self.NG_heating_value * \
                          heavy_oil_upgrading_table["Cogeneration steam efficiency"]
        NG_to_heat = max(
            NG_dict["Fraction NG - Heating (W/O cogen)"] - heat_from_cogen / upgrader_process_gas_heating_value, 0)

        proc_gas_flaring_rate = (self.upgrader_gas_comp *
                                 self.oil.component_MW[self.upgrader_gas_comp.index] *
                                 proc_gas_flared *
                                 self.mole_to_scf)
        flaring_gas = self.find_output_stream("gas for flaring", raiseError=False)
        if flaring_gas:
            flaring_gas.set_rates_from_series(proc_gas_flaring_rate, PHASE_GAS)
            flaring_gas.set_tp(STP)

        # energy use
        energy_use = self.energy
        NG_consumption = (NG_to_cogen + NG_to_H2 + NG_to_heat) * self.NG_heating_value
        upgrader_process_gas_consumption = (proc_gas_to_H2 + proc_gas_flared + proc_gas_to_heat) * self.NG_heating_value
        petro_coke_consumption = coke_to_heat * self.petro_coke_heating_value
        energy_use.set_rate(EN_NATURAL_GAS, NG_consumption.to("mmBtu/day"))
        energy_use.set_rate(EN_UPG_PROC_GAS, upgrader_process_gas_consumption.to("mmBtu/day"))
        energy_use.set_rate(EN_PETCOKE, petro_coke_consumption.to("mmBtu/day"))
        energy_use.set_rate(EN_ELECTRICITY, elect_import.to("mmBtu/day"))

        # import/export
        self.set_import_from_energy(energy_use)
        field.import_export.set_export(self.name, "Electricity", elect_cogen)

        # emission
        emissions = self.emissions
        energy_for_combustion = energy_use.data.drop("Electricity")
        combustion_emission = (energy_for_combustion * self.process_EF).sum()
        emissions.set_rate(EM_COMBUSTION, "CO2", combustion_emission)
        emissions.set_from_series(EM_FLARING, proc_gas_flaring_rate.pint.to("tonne/day"))
