#
# WaterInjection class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
# WaterInjection class
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
import numpy as np

from .shared import get_energy_carrier, get_energy_consumption
from .. import ureg
from ..emissions import EM_COMBUSTION
from ..error import OpgeeException
from ..log import getLogger
from ..process import Process

_logger = getLogger(__name__)


class WaterInjection(Process):
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()
        self.water_reinjection = field.attr("water_reinjection")
        self.water_flooding = field.attr("water_flooding")

        if self.water_reinjection == 0 and self.water_flooding == 0:
            self.set_enabled(False)
            return

        self.prod_index = field.attr("prod_index")
        self.water = field.water
        self.water_density = self.water.density()
        self.res_press = field.attr("res_press")
        self.num_water_inj_wells = field.attr("num_water_inj_wells")
        self.gravitation_acc = self.field.model.const("gravitational-acceleration")
        self.gravitation_const = self.field.model.const("gravitational-constant")
        self.depth = field.attr("depth")
        self.well_diam = field.attr("well_diam")
        self.xsection_area = np.pi * (self.well_diam / 2) ** 2
        self.friction_factor = field.attr("friction_factor")
        self.press_pump = self.attr("press_pump")
        self.eta_pump = self.attr("eta_pump")
        self.prime_mover_type = self.attr("prime_mover_type")

    def run(self, analysis):
        self.print_running_msg()

        if self.num_water_inj_wells.m == 0:
            raise OpgeeException(f"Got zero number of injector in the {self.name} process")

        input_prod = self.find_input_stream("produced water for water injection")
        input_makeup = self.find_input_stream("makeup water for water injection")
        total_water_mass = input_prod.liquid_flow_rate("H2O") + input_makeup.liquid_flow_rate("H2O")
        total_water_volume = total_water_mass / self.water_density
        single_well_water_volume = total_water_volume / self.num_water_inj_wells

        wellbore_flowing_press = single_well_water_volume / self.prod_index + self.res_press
        water_gravitation_head = self.water_density * self.gravitation_acc * self.depth
        water_flow_velocity = single_well_water_volume / self.xsection_area

        friction_loss = (self.friction_factor * self.depth * water_flow_velocity ** 2) / \
                        (2 * self.well_diam * self.gravitation_const) * self.water_density
        diff_press = wellbore_flowing_press - water_gravitation_head

        pumping_press = diff_press + friction_loss - self.press_pump \
            if diff_press + friction_loss >= 0 else ureg.Quantity(0.0, "psia")
        pumping_hp = pumping_press * single_well_water_volume / self.eta_pump

        # energy-use
        water_pump_power = get_energy_consumption(self.prime_mover_type, pumping_hp)
        energy_use = self.energy

        energy_carrier = get_energy_carrier(self.prime_mover_type)
        energy_use.set_rate(energy_carrier, water_pump_power)

        # import/export
        # import_product = field.import_export
        self.set_import_from_energy(energy_use)

        # emission
        emissions = self.emissions
        energy_for_combustion = energy_use.data.drop("Electricity")
        combustion_emission = (energy_for_combustion * self.process_EF).sum()
        emissions.set_rate(EM_COMBUSTION, "CO2", combustion_emission)
