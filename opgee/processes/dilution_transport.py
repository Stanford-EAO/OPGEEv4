from ..emissions import EM_COMBUSTION
from ..log import getLogger
from ..process import Process
from opgee.processes.transport_energy import TransportEnergy
from .shared import get_energy_carrier
from ..import_export import ImportExport, DILUENT

_logger = getLogger(__name__)


class DiluentTransport(Process):
    def _after_init(self):
        super()._after_init()
        self.field = field = self.get_field()
        self.oil = field.oil
        self.API_diluent = field.attr("diluent_API")
        self.transport_share_fuel = field.transport_share_fuel.loc["Diluent"]
        self.transport_parameter = field.transport_parameter[["Diluent", "Units"]]
        self.transport_by_mode = field.transport_by_mode.loc["Diluent"]

    def run(self, analysis):
        self.print_running_msg()
        field = self.field

        input = self.find_input_stream("oil for transport")

        if input.is_uninitialized():
            return

        oil_mass_rate = input.liquid_flow_rate("oil")
        oil_mass_energy_density = self.oil.mass_energy_density(self.API_diluent)
        oil_LHV_rate = oil_mass_rate * oil_mass_energy_density

        # energy use
        energy_use = self.energy
        fuel_consumption = TransportEnergy.get_transport_energy_dict(self.field,
                                                                     self.transport_parameter,
                                                                     self.transport_share_fuel,
                                                                     self.transport_by_mode,
                                                                     oil_LHV_rate,
                                                                     "Diluent")

        for name, value in fuel_consumption.items():
            energy_use.set_rate(get_energy_carrier(name), value.to("mmBtu/day"))

        # import/export
        import_product = field.import_export
        self.set_import_from_energy(energy_use)
        import_product.set_export(self.name, DILUENT, oil_LHV_rate)

        # emission
        emissions = self.emissions
        energy_for_combustion = energy_use.data.drop("Electricity")
        combustion_emission = (energy_for_combustion * self.process_EF).sum()
        emissions.set_rate(EM_COMBUSTION, "CO2", combustion_emission)

    def impute(self):
        output = self.find_output_stream("oil for dilution")
        input = self.find_input_stream("oil for transport")
        input.copy_flow_rates_from(output)


