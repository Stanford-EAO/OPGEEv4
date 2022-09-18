#
# TableManager class
#
# Author: Richard Plevin and Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
import os

import pandas as pd

from .core import OpgeeObject
from .error import OpgeeException
from .log import getLogger
from .pkg_utils import resourceStream

_logger = getLogger(__name__)


class TableDef(object):
    """
    Holds meta-data for built-in tables (CSV files loaded into `pandas.DataFrames`).
    """

    def __init__(self, basename, index_col=None, index_row=None, has_units=None, fillna=None):
        self.basename = basename
        self.index_col = index_col
        self.index_row = index_row
        self.has_units = has_units
        self.fillna = fillna


class TableManager(OpgeeObject):
    """
    The TableManager loads built-in CSV files into DataFrames and stores them in a dictionary keyed by the root name
    of the table. When adding CSV files to the opgee “tables” directory, a corresponding entry must be added in the
    TableManager class variable ``TableManager.table_defs``, which holds instances of `TableDef` class.

    Users can add external tables using the ``add_table`` method.
    """
    table_defs = [
        TableDef('constants', index_col='name'),
        TableDef('GWP', index_col=False),
        TableDef('bitumen-mining-energy-intensity', index_col=0),
        TableDef("process-specific-EF", index_col=0, has_units=True),
        TableDef("water-treatment", index_col=0, has_units=True),
        TableDef('heavy-oil-upgrading'),
        TableDef("transport-parameter", index_col=0),
        TableDef("transport-share-fuel", index_col=[0,1], has_units=True),
        TableDef("transport-by-mode", index_col=[0,1], has_units=True),
        TableDef("reaction-combustion-coeff", index_col=0, has_units=True),
        TableDef("product-combustion-coeff", index_col=0, has_units=True),
        TableDef("gas-turbine-specs", index_col=0, has_units=True),
        TableDef("gas-dehydration", index_col=0),
        TableDef("acid-gas-removal", index_col=0, index_row=[0,1]),
        TableDef("ryan-holmes-process", index_col=0, has_units=True),
        TableDef("imported-gas-comp", index_col=0, has_units=True),
        TableDef("upstream-CI", index_col=0, has_units=True),
        TableDef("vertical-drilling-energy-intensity", index_col=[0,1], has_units=True),
        TableDef("horizontal-drilling-energy-intensity", index_col=[0,1], has_units=True),
        TableDef("fracture-consumption-table", index_col=0),
        TableDef("land-use-EF", index_col=[0,1], has_units=True),
        TableDef("pubchem-cid", index_col=0),
        TableDef("demethanizer", index_col=0, index_row=[0,1])
    ]

    _table_def_dict = {tbl_def.basename: tbl_def for tbl_def in table_defs}

    def __init__(self, updates=None):
        self.table_dict = {}
        self.updates = updates

    def get_table(self, name, raiseError=True):
        """
        Retrieve a dataframe representing CSV data loaded by the TableManager

        :param name: (str) the name of a table
        :param raiseError: (bool) whether to raise an error (or just return None) if the table isn't found.
        :return: (pandas.DataFrame) the corresponding data
        :raises: OpgeeException if the `name` is unknown and `raiseError` is True.
        """
        df = self.table_dict.get(name)

        # load on demand, if a TableDef is found
        if df is None:
            try:
                tbl_def = self._table_def_dict[name]
            except KeyError:
                if raiseError:
                    raise OpgeeException(f"Unknown table '{name}'")
                else:
                    return None

            relpath = f"tables/{name}.csv"
            s = resourceStream(relpath, stream_type='text')
            if tbl_def.has_units:
                df = pd.read_csv(s, index_col=tbl_def.index_col, header=[0, 1])

                unitful_cols = [name for name, unit in df.columns if unit != '_']
                for col in unitful_cols:
                    df[col] = df[col].astype(float) # force numeric values to float to avoid complaints from pint

                df_units = df[unitful_cols].pint.quantify(level=-1)
                df[unitful_cols] = df_units[unitful_cols]
                df.columns = df.columns.droplevel(1)        # drop the units from the column index
            else:
                df = pd.read_csv(s, index_col=tbl_def.index_col) if tbl_def.index_row is None \
                    else pd.read_csv(s, index_col=tbl_def.index_col, header=tbl_def.index_row)

            if tbl_def.fillna is not None:
                df.fillna(tbl_def.fillna, inplace=True)

            # apply XML table updates from user
            update = self.updates and self.updates.get(name)
            if update and update.enabled:
                for cell in update.cells:
                    df.loc[cell.row, cell.col] = cell.value

            self.table_dict[name] = df

        return df

    def add_table(self, pathname, index_col=None, skiprows=0):  # , units=None):
        """
        Add a CSV file external to OPGEE to the TableManager.

        :param pathname: (str) the pathname of a CSV file
        :param index_col: (str, int, iterable of str or int, False, or None) see doc
            for `pandas.read_csv()`
        :param skiprows: (int) the number of rows to skip before the table begins.
        :return: none
        """
        df = pd.read_csv(pathname, index_col=index_col, skiprows=skiprows)
        name = os.path.splitext(os.path.basename(pathname))[0]
        self.table_dict[name] = df
