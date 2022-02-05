import pandas as pd
import pint
from .core import OpgeeObject
from .error import OpgeeException

from .log import getLogger

_logger = getLogger(__name__)


class ImportExport(OpgeeObject):
    IMPORT = 'import'
    EXPORT = 'export'
    NET_IMPORTS = 'net imports'

    NATURAL_GAS = "NG"
    UPG_PROC_GAS = "upg_proc_gas"
    NGL_LPG = "NLG_LPG"
    DILUENT = "diluent"
    CRUDE_OIL = "crude_oil"  # does not contain diluent
    DIESEL = "diesel"
    RESID = "resid"
    PETCOKE = "petcoke"
    ELECTRICITY = "electricity"
    WATER = "water"

    unit_dict = {NATURAL_GAS : "mmbtu/day",
                 UPG_PROC_GAS: "mmbtu/day",
                 NGL_LPG     : "mmbtu/day",
                 DILUENT     : "mmbtu/day",
                 CRUDE_OIL   : "mmbtu/day",
                 DIESEL      : "mmbtu/day",
                 RESID       : "mmbtu/day",
                 PETCOKE     : "mmbtu/day",
                 ELECTRICITY : "kWh/day",
                 WATER       : "gal/day"}

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

    def add_import_export(self, proc_name, imp_exp, item, value):
        """
        Add imports for a given ``item`` by process ``proc_name``, of
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

    def add_import(self, proc_name, item, value):
        """
        Add imports for a given ``item`` by process ``proc_name``, of
        quantity ``value``.

        :param proc_name: (str) the name of a process
        :param item: (str) one of the known import items (see ImportExport.imports_set)
        :param value: (float or pint.Quantity) the quantity imported. If a Quantity
           is passed, it is converted to the import's standard units.
        :return: none
        """
        self.add_import_export(proc_name, self.IMPORT, item, value)

    def add_export(self, proc_name, item, value):
        """
        Add imports for a given ``item`` by process ``proc_name``, of
        quantity ``value``.

        :param proc_name: (str) the name of a process
        :param item: (str) one of the known import items (see ImportExport.imports_set)
        :param value: (float or pint.Quantity) the quantity exported. If a Quantity
           is passed, it is converted to the import's standard units.
        :return: none
        """
        self.add_import_export(proc_name, self.EXPORT, item, value)

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
        def _totals(df):
            totals = {name : df[name].sum() for name in df.columns}
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
