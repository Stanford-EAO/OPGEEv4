'''
.. Energy use tracking

.. Copyright (c) 2021 Richard Plevin and Stanford University
   See the https://opensource.org/licenses/MIT for license details.
'''
import pandas as pd
from .core import OpgeeObject
from .error import OpgeeException

# TBD: Decide if these strings are the ones we want to use throughout.
EN_NATURAL_GAS = 'Natural gas'
EN_UPG_PROC_GAS = 'Upgrader proc. gas'
EN_NGL = 'NGL'
EN_CRUDE_OIL = 'Crude oil'
EN_DIESEL = 'Diesel'
EN_RESID = 'Residual fuel'
EN_PETCOKE = 'Pet. coke'
EN_ELECTRICITY = 'Electricity'

class Energy(OpgeeObject):
    """
    Energy is an object wrapper around a pandas.Series holding energy consumption
    rates for a pre-defined set of energy carriers, defined in Energy.carriers.
    Note that when used in the code, the defined variables (e.g., EN_NATURAL_GAS,
    EN_DIESEL, etc.) should be used to avoid dependencies on the specific strings.
    """
    carriers = [EN_NATURAL_GAS, EN_UPG_PROC_GAS, EN_NGL, EN_CRUDE_OIL,
                EN_DIESEL, EN_RESID, EN_PETCOKE, EN_ELECTRICITY]

    _carrier_set = set(carriers)

    @classmethod
    def create_energy_series(cls):
        """
         Create a pandas Series to hold energy consumption rates.

         :return: (pandas.Series) Zero-filled energy carrier Series
         """
        # TBD: use the units via pint's pandas support
        # TBD: all are in mmbtu/day except electricity in kWh/day
        return pd.Series(data=0.0, index=cls.carriers, name='energy', dtype=float)

    def __init__(self):
        self.data = self.create_energy_series()

    def rates(self):
        return self.data

    def set_rate(self, carrier, rate):
        """
        Set the rate of energy use for a single carrier.

        :param carrier: (str) one of the defined energy carriers (values of Energy.carriers)
        :param rate: (float) the rate of use (e.g., mmbtu/day (LHV) for all but electricity,
            which is in units of kWh/day.
        :return: none
        """
        if carrier not in self._carrier_set:
            raise OpgeeException(f"Energy.set_rate: Unrecognized carrier '{carrier}'")

        self.data[carrier] = rate

    def set_rates(self, dictionary):
        """
        Set the energy use rate of one or more carriers.

        :param dictionary: (dict) the carriers and rates
        :return: none
        """
        for carrier, rate in dictionary.items():
            self.set_rate(carrier, rate)
