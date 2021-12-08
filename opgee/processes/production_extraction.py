from ..process import Process
from ..log import getLogger

_logger = getLogger(__name__)


class CrudeStorage(Process):
    def run(self, analysis):
        self.print_running_msg()


class SourGasReinjectionCompressor(Process):
    def run(self, analysis):
        self.print_running_msg()


class HCGasInjectionWells(Process):
    def run(self, analysis):
        self.print_running_msg()


class CO2InjectionWells(Process):
    def run(self, analysis):
        self.print_running_msg()


class GasFloodWells(Process):
    def run(self, analysis):
        self.print_running_msg()


class SteamInjectionWells(Process):
    def run(self, analysis):
        self.print_running_msg()


