from ..log import getLogger
from ..process import Process
from ..energy import EN_ELECTRICITY
from ..stream import Stream, PHASE_GAS, PHASE_LIQUID, PHASE_SOLID
from ..error import OpgeeException
from opgee import ureg

_logger = getLogger(__name__)


class WaterTreatment(Process):
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()
        self.std_temp = field.model.const("std-temperature")
        self.std_press = field.model.const("std-pressure")
        self.oil_volume_rate = field.attr("oil_prod")
        self.WOR = field.attr("WOR")
        self.WIR = field.attr("WIR")

        self.water_reinjection = field.attr("water_reinjection")
        self.water_flooding = field.attr("water_flooding")
        self.frac_water_reinj = field.attr("fraction_water_reinjected")

        self.steam_flooding = field.attr("steam_flooding")
        self.SOR = field.attr("SOR")
        self.steam_quality_outlet = field.attr("steam_quality_at_generator_outlet")
        self.steam_quality_blowdown = field.attr("steam_quality_after_blowdown")

        self.frac_disp_subsurface = self.attr("fraction_disp_water_subsurface")
        self.frac_disp_surface = self.attr("fraction_disp_water_surface")

        self.water_treatment_table = self.model.water_treatment
        self.makeup_water_treatment_tbl = self.attr("makeup_water_treatment_table")
        self.num_stages = self.attr("number_of_stages")
        self.makeup_water_temp = self.attr("makeup_water_temp")
        self.makeup_water_press = self.attr("makeup_water_press")

    def run(self, analysis):
        self.print_running_msg()

        # mass rate
        input = self.find_input_streams("water", combine=True)
        prod_water_mass_rate = input.liquid_flow_rate("H2O")

        water = self.field.water
        water_density = water.density(input.temperature, input.pressure)
        prod_water_volume = prod_water_mass_rate / water_density

        # calculate makeup water volume rate
        if self.water_reinjection:
            total_water_inj_demand = self.oil_volume_rate * self.WOR * self.frac_water_reinj
        else:
            if self.water_flooding:
                total_water_inj_demand = self.oil_volume_rate * self.WIR
        makeup_water_volume_reinjection = max(total_water_inj_demand - prod_water_volume, ureg.Quantity(0.0, "barrel_water/day"))
        makeup_water_mass_reinjection = makeup_water_volume_reinjection * water_density

        if self.steam_flooding:
            total_steam_inj_demand = self.oil_volume_rate * self.SOR
        else:
            total_steam_inj_demand = ureg.Quantity(0.0, "m**3/day")
        makeup_water_volume_steam = max(total_steam_inj_demand - prod_water_volume, ureg.Quantity(0.0, "barrel_water/day"))
        makeup_water_mass_steam = makeup_water_volume_steam * water_density

        total_makeup_water_volume = makeup_water_volume_steam + makeup_water_volume_reinjection

        makeup_water_to_reinjection = self.find_output_stream("makeup water for water injection", raiseError=False)
        if makeup_water_to_reinjection is not None:
            makeup_water_to_reinjection.set_liquid_flow_rate("H2O",
                                                             makeup_water_mass_reinjection.to("tonne/day"),
                                                             self.makeup_water_temp,
                                                             self.makeup_water_press)

        makeup_water_to_steam = self.find_output_stream("makeup water for steam generation", raiseError=False)
        if makeup_water_to_steam is not None:
            makeup_water_to_steam.set_liquid_flow_rate("H2O", makeup_water_mass_steam.to("tonne/day"),
                                                       self.makeup_water_temp, self.makeup_water_press)

        # produced water stream
        prod_water_to_reinjection = self.find_output_stream("produced water for water injection", raiseError=False)
        if prod_water_to_reinjection is not None:
            prod_water_mass = min(total_water_inj_demand * water_density, prod_water_mass_rate)
            prod_water_to_reinjection.set_liquid_flow_rate("H2O", prod_water_mass.to("tonne/day"), input.temperature, input.pressure)

        prod_water_to_steam = self.find_output_stream("produced water for steam generation", raiseError=False)
        if prod_water_to_steam is not None:
            prod_water_mass = min(total_steam_inj_demand * water_density, prod_water_mass_rate)
            prod_water_to_steam.set_liquid_flow_rate("H2O", prod_water_mass.to("tonne/day"), input.temperature, input.pressure)


        output_surface_disposal = self.find_output_stream("water for surface disposal")
        # water_for_disp = (1 - frac_prod_water_as_steam - frac_prod_water_as_water) * prod_water_mass_rate
        # surface_disp_rate = water_for_disp * self.frac_disp_surface + steam_rate
        # # surface disp rate is frac*tonne/day
        # output_surface_disposal.set_liquid_flow_rate("H2O", surface_disp_rate.to("tonne/day"),
        #                                              t=self.std_temp, p=self.std_press)

        output_subsurface_disposal = self.find_output_stream("water for subsurface disposal")
        # subsurface_disp_rate = water_for_disp * self.frac_disp_subsurface
        # # subsurface disp rate is frac*tonne/day
        # output_subsurface_disposal.set_liquid_flow_rate("H2O", subsurface_disp_rate.to("tonne/day"),
        #                                                 t=input.temperature, p=input.pressure)

        # enegy use
        prod_water_elec = self.get_water_treatment_elec(self.water_treatment_table, prod_water_volume)
        if self.makeup_water_treatment_tbl:
            makeup_water_table = self.water_treatment_table
        else:
            if self.makeup_water_treatment is None:
                raise OpgeeException("no makeup water table provided")
            else:
                makeup_water_table = self.makeup_water_treatment
        makeup_water_elec = self.get_water_treatment_elec(makeup_water_table, total_makeup_water_volume)
        electricity = prod_water_elec + makeup_water_elec
            
        energy_use = self.energy
        energy_use.set_rate(EN_ELECTRICITY, electricity.to("mmBtu/day"))

        # emission
        emissions = self.emissions

    def get_water_treatment_elec(self, water_treatment_table, water_volume_rate):

        electricity = 0
        stages = sorted(water_treatment_table.index.unique())

        if self.num_stages > len(stages) or self.num_stages < 0:
            raise OpgeeException(f"water treatment: number of stages ({self.num_stages}) must be > 0 and <= {len(stages)}")

        for stage in stages[:self.num_stages]:
            stage_row = water_treatment_table.loc[stage]
            electricity_factor = (stage_row["Apply"].squeeze() *
                                  stage_row["EC"].squeeze()).sum()
            electricity += electricity_factor * water_volume_rate
            loss_factor = (stage_row["Apply"].squeeze() *
                           stage_row["Volume loss"].squeeze()).sum()
            water_volume_rate *= (1 - loss_factor)

        return electricity
