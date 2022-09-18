#
# Processes used for testing
#
# Author: Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
from ..process import Process
from ..log import getLogger

_logger = getLogger(__name__)


class AfterDewatering(Process):
    def run(self, analysis):
        self.print_running_msg()


class GasFloodingCompressor(Process):
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


class SeparationTemporary(Process):
    def run(self, analysis):
        self.print_running_msg()


class FluidProduction(Process):
    def run(self, analysis):
        self.print_running_msg()


class FluidInjection(Process):
    def run(self, analysis):
        self.print_running_msg()


class SourGasInjectionWells(Process):
    def run(self, analysis):
        self.print_running_msg()


class GasTransmissionCompressors(Process):
    def run(self, analysis):
        self.print_running_msg()


class GasPartitionA(Process):
    def run(self, analysis):
        self.print_running_msg()


class GasPartitionB(Process):
    def run(self, analysis):
        self.print_running_msg()


class FuelGasConsumed(Process):
    def run(self, analysis):
        self.print_running_msg()


class FuelGasImports(Process):
    def run(self, analysis):
        self.print_running_msg()


class NGLOrDiluentProdAndImports(Process):
    def run(self, analysis):
        self.print_running_msg()


class Maintenance(Process):
    def run(self, analysis):
        self.print_running_msg()


class WasteDisposal(Process):
    def run(self, analysis):
        self.print_running_msg()


class GasStorageWells(Process):
    def run(self, analysis):
        self.print_running_msg()


class PetcokeTransport(Process):
    def run(self, analysis):
        self.print_running_msg()


class ElectricityGenAndImports(Process):
    def run(self, analysis):
        self.print_running_msg()


class SurveyTruck(Process):
    def run(self, analysis):
        self.print_running_msg()

    def __str__(self):
        return f'<SurveyTruck>'


class SurveyShip(Process):
    def run(self, analysis):
        self.print_running_msg()

    def __str__(self):
        return f'<SurveyShip>'


class DrillingAndDevelopment(Process):
    def run(self, analysis):
        self.print_running_msg()


class LandUse(Process):
    def run(self, analysis):
        self.print_running_msg()


class Fracking(Process):
    def run(self, analysis):
        self.print_running_msg()
