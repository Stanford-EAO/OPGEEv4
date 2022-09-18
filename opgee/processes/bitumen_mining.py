#
# BitumenMining class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
from .. import ureg
from ..core import TemperaturePressure
from ..emissions import EM_COMBUSTION, EM_FUGITIVES
from ..energy import EN_NATURAL_GAS, EN_ELECTRICITY, EN_DIESEL
from ..log import getLogger
from ..process import Process
from ..stream import PHASE_GAS, Stream

_logger = getLogger(__name__)


class BitumenMining(Process):
    """
    This process takes ... do ...

    input streams:
        - (optional)

    output streams:
        - (optional)

    field data stored:
        -
    """

    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()

        self.oil_sands_mine = field.attr("oil_sands_mine")
        if self.oil_sands_mine == "None":
            self.set_enabled(False)
            return

        self.oil = field.oil
        self.API_bitumen = field.attr("API_bitumen")
        self.bitumen_SG = self.oil.specific_gravity(self.API_bitumen)

        self.mined_bitumen_tp = TemperaturePressure(field.attr("temperature_mined_bitumen"),
                                                    field.attr("pressure_mined_bitumen"))
        self.downhole_pump = field.attr("downhole_pump")
        self.oil_prod_rate = field.attr("oil_prod")
        self.upgrader_type = self.field.attr("upgrader_type")
        self.upgrader_mining_prod_onsite = True if self.upgrader_type != "None" else False
        self.gas_comp = field.attrs_with_prefix("gas_comp_")
        self.FOR = field.attr("FOR")
        self.VOR = field.attr("VOR")

        self.water = self.field.water
        self.water_density = self.water.density()

    def run(self, analysis):
        self.print_running_msg()
        field = self.field

        bitumen_to_dilution_mass_rate = (
            self.oil_prod_rate * self.bitumen_SG * self.water_density
            if not self.upgrader_mining_prod_onsite
            else ureg.Quantity(0.0, "tonne/day"))

        if bitumen_to_dilution_mass_rate.m != 0:
            bitumen_to_dilution_stream = self.find_output_stream("bitumen for dilution")
            bitumen_to_dilution_stream.set_liquid_flow_rate("oil",
                                                            bitumen_to_dilution_mass_rate,
                                                            self.mined_bitumen_tp)

        bitumen_to_upgrading_mass_rate = (
            self.oil_prod_rate * self.bitumen_SG * self.water_density
            if self.upgrader_mining_prod_onsite
            else ureg.Quantity(0.0, "tonne/day"))

        if bitumen_to_upgrading_mass_rate.m != 0:
            bitumen_to_upgrading_stream = self.find_output_stream("bitumen for upgrading")
            bitumen_to_upgrading_stream.set_liquid_flow_rate("oil",
                                                             bitumen_to_upgrading_mass_rate,
                                                             self.mined_bitumen_tp)

        bitumen_mass_rate_tot = bitumen_to_dilution_mass_rate + bitumen_to_upgrading_mass_rate
        bitumen_volume_rate = bitumen_mass_rate_tot / self.bitumen_SG / self.water_density

        d = self.model.mining_energy_intensity

        mining_intensity_table = d[self.oil_sands_mine]
        unit_col = d["Units"]

        oil_rate = (bitumen_volume_rate * self.gas_comp *
                    self.model.const("mol-per-scf") * self.oil.component_MW[self.gas_comp.index])
        mine_flaring_rate = self.FOR * oil_rate
        mine_offgas_rate = self.VOR * oil_rate

        gas_fugitives = Stream("gas_fugitives", tp=self.field.stp)
        gas_fugitives.set_rates_from_series(mine_offgas_rate, PHASE_GAS)

        gas_flaring = self.find_output_stream("gas for flaring", raiseError=False)
        if gas_flaring:
            gas_flaring.set_rates_from_series(mine_flaring_rate, PHASE_GAS)

        # energy-use
        energy_use = self.energy
        NG_consumption = bitumen_volume_rate * ureg.Quantity(mining_intensity_table["Natural gas use"],
                                                             unit_col["Natural gas use"]) * self.model.const(
            "NG-heating-value")
        diesel_consumption = bitumen_volume_rate * ureg.Quantity(mining_intensity_table["Diesel fuel use"],
                                                                 unit_col["Diesel fuel use"]) * self.model.const(
            "diesel-LHV")
        electricity_consumption = bitumen_volume_rate * ureg.Quantity(mining_intensity_table["Electricity use"],
                                                                      unit_col["Electricity use"])
        energy_use.set_rate(EN_NATURAL_GAS, NG_consumption.to("mmBtu/day"))
        energy_use.set_rate(EN_DIESEL, diesel_consumption.to("mmBtu/day"))
        energy_use.set_rate(EN_ELECTRICITY, electricity_consumption.to("mmBtu/day"))

        # import/export
        self.set_import_from_energy(energy_use)

        # emissions
        emissions = self.emissions
        energy_for_combustion = energy_use.data.drop("Electricity")
        combustion_emission = (energy_for_combustion * self.process_EF).sum()
        emissions.set_rate(EM_COMBUSTION, "CO2", combustion_emission)

        emissions.set_from_stream(EM_FUGITIVES, gas_fugitives)
