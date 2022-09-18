#
# ImportExport class
#
# Author: Richard Plevin
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
import pandas as pd
import pint

from .core import OpgeeObject
from .error import OpgeeException
from .log import getLogger

_logger = getLogger(__name__)

NATURAL_GAS = "Natural gas"
UPG_PROC_GAS = "Upgrader proc. gas"
NGL_LPG = "NGL"
DILUENT = "Diluent"
CRUDE_OIL = "Crude oil"  # does not contain diluent
DIESEL = "Diesel"
RESID = "Residual fuel"
PETCOKE = "Pet. coke"
ELECTRICITY = "Electricity"
WATER = "Water"

class ImportExport(OpgeeObject):
    IMPORT = 'import'
    EXPORT = 'export'
    NET_IMPORTS = 'net imports'

    unit_dict = {NATURAL_GAS : "mmbtu/day",
                 UPG_PROC_GAS: "mmbtu/day",
                 NGL_LPG     : "mmbtu/day",
                 DILUENT     : "mmbtu/day",
                 CRUDE_OIL   : "mmbtu/day",
                 DIESEL      : "mmbtu/day",
                 RESID       : "mmbtu/day",
                 PETCOKE     : "mmbtu/day",
                 ELECTRICITY : "kWh/day",
                 WATER       : "tonne/day"}

    imports_set = set(unit_dict.keys())

    @classmethod
    def _create_dataframe(cls):
        """
         Create a DataFrame to hold import or export rates.
         Used only by the __init__ method.

         :return: (pandas.DataFrame) An empty imports or exports DataFrame with
            the columns and types set
         """
        df = pd.DataFrame({name : pd.Series([], dtype=f"pint[{units}]")
                           for name, units in cls.unit_dict.items()})

        return df

    def __init__(self):
        self.import_df = self._create_dataframe()
        self.export_df = self._create_dataframe()

    def set_import_export(self, proc_name, imp_exp, item, value):
        """
        Set imports for a given ``item`` by process ``proc_name``, of
        quantity ``value``.

        :param proc_name: (str) the name of a process
        :param imp_exp: (str) one of "import" or "export" (ImportExport.IMPORT, ImportExport.EXPORT)
        :param item: (str) one of the known import items (see ImportExport.imports_set)
        :param value: (float or pint.Quantity) the quantity imported. If a Quantity
           is passed, it is converted to the import's standard units.
        :return: none
        """
        directions = (self.IMPORT, self.EXPORT)
        if imp_exp not in directions:
            raise OpgeeException(f"Unknown value for imp_exp: must be one of to add {directions}; got '{imp_exp}'")

        if item not in self.imports_set:
            raise OpgeeException(f"Tried to add {imp_exp} of unknown item '{item}'")

        df = self.import_df if imp_exp == self.IMPORT else self.export_df

        if proc_name not in df.index:
            df.loc[proc_name, :] = 0.0

        if isinstance(value, pint.Quantity):
            value = value.to(df[item].pint.units).m  # get value in expected units

        df.loc[proc_name, item] = value

    def set_import(self, proc_name, item, value):
        """
        Set imports for a given ``item`` by process ``proc_name``, of
        quantity ``value``.

        :param proc_name: (str) the name of a process
        :param item: (str) one of the known import items (see ImportExport.imports_set)
        :param value: (float or pint.Quantity) the quantity imported. If a Quantity
           is passed, it is converted to the import's standard units.
        :return: none
        """
        self.set_import_export(proc_name, self.IMPORT, item, value)

    def set_import_from_energy(self, proc_name, energy_use):
        """
        Set imports from energy use

        :param proc_name: (str) the name of a process
        :param energy_use: OPGEE.energy
        :return: none
        """
        for energy_carrier in energy_use.carriers:
            self.set_import_export(proc_name, self.IMPORT, energy_carrier, energy_use.get_rate(energy_carrier))

    def set_export(self, proc_name, item, value):
        """
        Set imports for a given ``item`` by process ``proc_name``, of
        quantity ``value``.

        :param proc_name: (str) the name of a process
        :param item: (str) one of the known import items (see ImportExport.imports_set)
        :param value: (float or pint.Quantity) the quantity exported. If a Quantity
           is passed, it is converted to the import's standard units.
        :return: none
        """
        self.set_import_export(proc_name, self.EXPORT, item, value)

    def importing_processes(self):
        """
        Return a list of the names of importing processes.
        """
        return list(self.import_df.index)

    def exporting_processes(self):
        """
        Return a list of the names of exporting processes.
        """
        return list(self.export_df.index)

    def imports_exports(self):
        """
        Return a DataFrame with 3 columns, holding total imports, total exports,
        and net imports, i.e., net = (imports - exports).

        :return: (pandas.DataFrame) total imports, exports, and net imports by resource
        """
        def _sum(series, name):
            from . import ureg
            # Sum of an empty series is returned as int(0); need to initialize units
            return series.sum() if len(series) > 0 else ureg.Quantity(0.0, self.unit_dict[name])

        def _totals(df):
            totals = {name : _sum(df[name], name) for name in df.columns}
            return pd.Series(totals)

        imports = _totals(self.import_df)
        exports = _totals(self.export_df)

        d = {self.IMPORT: imports,
             self.EXPORT: exports,
             self.NET_IMPORTS: imports - exports}

        return pd.DataFrame(d)

    def proc_imports(self, proc_name):
        """
        Return a Series holding the imports for the given ``proc_name``.

        :param proc_name: (str) the name of a process
        :return: (pandas.Series) the values stored for the ``proc_name``
        """
        row = self.import_df.loc[proc_name]
        return row

    def proc_exports(self, proc_name):
        """
        Return a Series holding the exports for the given ``proc_name``.

        :param proc_name: (str) the name of a process
        :return: (pandas.Series) the values stored for the ``proc_name``
        """
        row = self.export_df.loc[proc_name]
        return row
