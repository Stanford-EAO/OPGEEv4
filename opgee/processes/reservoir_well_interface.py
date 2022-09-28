#
# ReservoirWellInterface class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
import numpy as np

from .. import ureg
from ..core import TemperaturePressure, STP
from ..error import ModelValidationError
from ..log import getLogger
from ..process import Process
from ..stream import PHASE_GAS

_logger = getLogger(__name__)  # data logging


class ReservoirWellInterface(Process):
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()

        self.res_tp = TemperaturePressure(field.attr("res_temp"),
                                          field.attr("res_press"))
        self.oil_sand_mine = field.attr("oil_sands_mine")
        if self.oil_sand_mine != "None":
            self.set_enabled(False)
            return

        self.num_prod_wells = field.attr("num_prod_wells")
        self.productivity_index = field.attr("prod_index")
        self.permeability = field.attr("res_perm")
        self.thickness = field.attr("res_thickness")
        self.gas_flooding = field.attr("gas_flooding")
        self.flood_gas_type = field.attr("flood_gas_type")
        self.oil_prod = field.attr("oil_prod")
        self.GFIR = field.attr("GFIR")
        self.frac_CO2_breakthrough = self.attr("frac_CO2_breakthrough")
        self.CO2_flooding_vol_rate = self.oil_prod * self.GFIR * self.frac_CO2_breakthrough

    def run(self, analysis):
        self.print_running_msg()
        field = self.field

        # mass rate
        input = self.find_input_stream("crude oil")

        if input.is_uninitialized():
            return

        input.set_tp(self.res_tp)

        output = self.find_output_stream("crude oil")
        # Check
        self.set_iteration_value(output.total_flow_rate())

        if self.gas_flooding and self.flood_gas_type == "CO2":
            flooding_CO2_rate = field.gas.component_gas_rho_STP["CO2"] * self.CO2_flooding_vol_rate
            output.copy_flow_rates_from(input)
            output.add_flow_rate("CO2", PHASE_GAS, flooding_CO2_rate)
        else:
            output.copy_flow_rates_from(input)

        # bottom hole flowing pressure
        bottomhole_flowing_press = self.get_bottomhole_press(input)
        output.tp.set(T=self.res_tp.T, P=bottomhole_flowing_press)

    def impute(self):
        output = self.find_output_stream("crude oil")

        input = self.find_input_stream("crude oil")
        input.copy_flow_rates_from(output)

    def get_bottomhole_press(self, input_stream):
        """
        Get the bottomhole pressure (BHP)

        :param input_stream: (Stream) a combined stream with all flows from Reservoir
           to Reservoir-Well Interface

        :return:(pint.Quantity) bottomhole pressure (BHP) in units "psia"
        """
        oil = self.field.oil
        gas = self.field.gas
        water = self.field.water

        stream_temp = input_stream.tp.T.to("kelvin")
        res_press = input_stream.tp.P.to("psia")

        std_T = STP.T.to("kelvin")
        std_P = STP.P.to("Pa")

        # injection and production rate
        oil_prod_volume_rate = oil.volume_flow_rate(input_stream,
                                                    oil.oil_specific_gravity,
                                                    oil.gas_specific_gravity,
                                                    oil.gas_oil_ratio).to("bbl_oil/day")  # bbl/day
        water_prod_volume_rate = water.volume_flow_rate(input_stream).to("bbl_water/day")  # bbl/day
        gas_prod_volume_rate = gas.volume_flow_rate(input_stream).to("ft**3/day")
        fluid_rate_per_well = (oil_prod_volume_rate + water_prod_volume_rate) / self.num_prod_wells
        gas_rate_per_well = gas_prod_volume_rate / self.num_prod_wells

        # fluid properties at reservoir condition
        z_factor = gas.Z_factor(gas.reduced_temperature(input_stream), gas.reduced_pressure(input_stream))
        gas_viscosity = gas.viscosity(input_stream)  # cP
        gas_formation_volume_factor = gas.volume_factor(input_stream)

        # reservoir and flowing pressures at wellbore interface
        prod_liquid_flowing_BHP = (input_stream.tp.P - fluid_rate_per_well / self.productivity_index).to("psia")

        # TODO: replace line 112 and line 113 in the smart default
        if prod_liquid_flowing_BHP.m < 0:
            prod_liquid_flowing_BHP = ureg.Quantity(100, "psia")

        boundary = ureg.Quantity(2000., "psia")
        if res_press <= boundary:
            # flowing bottomhole pressure at producer (gas phase, low pressure)
            delta_P_square = (gas_viscosity * z_factor * std_P * stream_temp *
                              np.log(1000 / 0.5) * gas_rate_per_well /
                              (np.pi * self.permeability * self.thickness * std_T)).to("psia**2")
            prod_gas_flowing_BHP = np.sqrt(abs(res_press ** 2 - delta_P_square))  #: TODO
        else:
            # flowing bottomhole pressure at producer (gas phase, high pressure)
            delta_P_high = (gas_viscosity * gas_formation_volume_factor * np.log(1000 / 0.5) * gas_rate_per_well /
                            (2 * np.pi * self.permeability * self.thickness)).to("psia")
            prod_gas_flowing_BHP = res_press - delta_P_high

        prod_flowing_BHP = min(prod_liquid_flowing_BHP, prod_gas_flowing_BHP)

        if prod_flowing_BHP.m < 0.0:
            raise ModelValidationError(f"ReservoirWellInterface: prod_flowing_BHP.m < 0.0")

        return prod_flowing_BHP
