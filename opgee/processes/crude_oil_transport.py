from opgee.processes.transport_energy import TransportEnergy
from .shared import get_energy_carrier
from ..emissions import EM_COMBUSTION
from ..import_export import CRUDE_OIL
from ..log import getLogger
from ..process import Process

_logger = getLogger(__name__)


class CrudeOilTransport(Process):
    """
    Crude oil transport calculate emissions from crude oil to the market

    """

    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()
        self.oil = field.oil
        self.transport_share_fuel = field.transport_share_fuel.loc["Crude"]
        self.transport_parameter = field.transport_parameter[["Crude", "Units"]]
        self.frac_transport_mode = field.attrs_with_prefix("frac_transport_").rename("Fraction")
        self.transport_dist = field.attrs_with_prefix("transport_dist_").rename("Distance")
        self.transport_by_mode = self.frac_transport_mode.to_frame().join(self.transport_dist)

    def run(self, analysis):
        self.print_running_msg()
        field = self.field

        input_oil = self.find_input_stream("oil")

        if input_oil.is_uninitialized():
            return

        oil_mass_rate = input_oil.liquid_flow_rate("oil")
        oil_mass_energy_density = self.oil.mass_energy_density()
        oil_LHV_rate = oil_mass_rate * oil_mass_energy_density

        if self.field.get_process_data("crude_LHV") is None:
            self.field.save_process_data(crude_LHV=oil_mass_energy_density)

        output = self.find_output_stream("oil")
        output.copy_flow_rates_from(input_oil)

        # energy use
        energy_use = self.energy
        fuel_consumption = TransportEnergy.get_transport_energy_dict(self.field,
                                                                     self.transport_parameter,
                                                                     self.transport_share_fuel,
                                                                     self.transport_by_mode,
                                                                     oil_LHV_rate,
                                                                     "Crude")

        for name, value in fuel_consumption.items():
            energy_use.set_rate(get_energy_carrier(name), value.to("mmBtu/day"))

        # import/export
        import_product = field.import_export
        self.set_import_from_energy(energy_use)
        import_product.set_export(self.name, CRUDE_OIL, oil_LHV_rate)

        # emission
        emissions = self.emissions
        energy_for_combustion = energy_use.data.drop("Electricity")
        combustion_emission = (energy_for_combustion * self.process_EF).sum()
        emissions.set_rate(EM_COMBUSTION, "CO2", combustion_emission)