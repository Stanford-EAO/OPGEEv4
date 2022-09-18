#
# OPGEE stream support
#
# Author: Richard Plevin and Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
import re
from copy import copy

import pandas as pd
import pint

from . import ureg
from .attributes import AttributeMixin
from .core import XmlInstantiable, elt_name, magnitude, TemperaturePressure
from .error import OpgeeException, ModelValidationError
from .log import getLogger
from .table_manager import TableManager
from .utils import getBooleanXML, coercible

_logger = getLogger(__name__)

# constants to use instead of strings
PHASE_SOLID = 'solid'
PHASE_LIQUID = 'liquid'
PHASE_GAS = 'gas'

# Compile the patterns at load time for better performance
_carbon_number_prog = re.compile(r'^C(\d+)$')
_hydrocarbon_prog = re.compile(r'^(C\d+)H(\d+)$')


def is_carbon_number(name):
    return (_carbon_number_prog.match(name) is not None)


def is_hydrocarbon(name):
    return (name == 'CH4' or _hydrocarbon_prog.match(name) is not None)

def molecule_to_carbon(molecule):
    if molecule == "CH4":
        return "C1"

    m = _hydrocarbon_prog.match(molecule)
    if m is None:
        raise OpgeeException(f"Expected hydrocarbon molecule name like CxHy, got {molecule}")

    c_name = m.group(1)
    return c_name

def carbon_to_molecule(c_name):
    if c_name == "C1":
        return "CH4"

    m = _carbon_number_prog.match(c_name)
    if m is None:
        raise OpgeeException(f"Expected carbon number name like Cn, got {c_name}")

    carbons = int(m.group(1))
    hydrogens = 2 * carbons + 2
    molecule = f"{c_name}H{hydrogens}"
    return molecule


#
# Can streams have emissions (e.g., leakage) or is that attributed to a process?
#
class Stream(XmlInstantiable, AttributeMixin):
    """
    The `Stream` class represent the flow rates of single substances or mingled combinations of co-flowing substances
    in any of the three states of matter (solid, liquid, or gas). Streams and stream components are specified in mass
    flow rates (e.g., Mg per day). The default set of substances is defined by ``Stream.component_names`` but can be
    extended by the user to include other substances, by setting the configuration file variable
    `OPGEE.StreamComponents`.

    Streams are defined within the `<Field>` element and are stored in a `Field` instance. The `Field` class tracks
    all `Stream` instances in a dictionary keyed by `Stream` name.

    See also :doc:`OPGEE XML documentation <opgee-xml>`
    """
    _phases = [PHASE_SOLID, PHASE_LIQUID, PHASE_GAS]

    # HCs with 1-60 carbon atoms, i.e., C1, C2, ..., C50
    table_name = "pubchem-cid"
    mgr = TableManager()
    pubchem_cid_df = mgr.get_table("pubchem-cid")

    idx = pubchem_cid_df.index
    _hydrocarbons = list(idx)
    max_carbon_number = len(_hydrocarbons)
    _carbon_number_dict = {f'C{n}': float(n) for n in range(1, max_carbon_number + 1)}

    # Verify that the pubchem-cid index includes 1..N where N is the max_carbon number
    if set(_carbon_number_dict.keys()) != set(idx):
        raise ModelValidationError(f"{table_name} must contain carbon numbers 1..{max_carbon_number}.")

    # All hydrocarbon gases other than methane (C1) are considered VOCs.
    VOCs = _hydrocarbons[1:]

    _solids = ['PC']  # petcoke
    _liquids = ['oil']

    # _hc_molecules = ['CH4', 'C2H6', 'C3H8', 'C4H10']
    non_hydrocarbon_gases = _gases = ['N2', 'O2', 'CO2', 'H2O', 'H2', 'H2S', 'SO2', "CO"]
    _other = ['Na+', 'Cl-', 'Si-']

    combustible_components = _hydrocarbons + _gases

    for gas in _gases:
        _carbon_number_dict[gas] = 1.0 if gas[0] == "C" else 0.0

    carbon_number = pd.Series(_carbon_number_dict, dtype="pint[dimensionless]")

    #: The stream components tracked by OPGEE. This list can be extended by calling ``Stream.extend_components(names)``,
    #: or more simply by defining configuration file variable ``OPGEE.StreamComponents``.
    component_names = _solids + _liquids + _gases + _other + _hydrocarbons

    # Remember extensions to avoid applying any redundantly.
    # Value is a dict keyed by set(added_component_names).
    _extensions = {}

    _units = ureg.Unit('tonne/day')

    def __init__(self, name, tp,
                 src_name=None, dst_name=None, comp_matrix=None,
                 contents=None, impute=True):
        super().__init__(name)

        # TBD: rename this self.comp_matrix for clarity
        self.components = self.create_component_matrix() if comp_matrix is None else comp_matrix

        self.electricity = ureg.Quantity(0.0, "kWh/day")

        self.tp = copy(tp)

        # These values are used by self.reset() to restore the stream to it's initial state per the XML.
        self.initial_tp = copy(self.tp)
        self.xml_data = comp_matrix

        self.src_name = src_name
        self.dst_name = dst_name

        self.src_proc = None  # set in Field.connect_processes()
        self.dst_proc = None
        self.field = None

        self.contents = contents or []  # generic description of what the stream carries

        self.impute = impute

        # This flag indicates whether any data have been written to the stream yet. Note that it is False
        # if only temperature and pressure are set, though setting T & P makes no sense on an empty stream.
        self.has_exogenous_data = self.initialized = comp_matrix is not None

    def _after_init(self):
        self.check_attr_constraints(self.attr_dict)

    def __str__(self):
        return f"<Stream '{self.name}'>"

    def reset(self):
        """
        Reset an existing `Stream` to a state suitable for re-running the model. If the stream
        was initialized with data from the XML, this will have been stored in self.xml_data and
        is used to reset the stream. Otherwise, a new component matrix is created.

        :return: none
        """
        self.initialized = has_xml_data = self.xml_data is not None
        self.components = self.xml_data if has_xml_data else self.create_component_matrix()

        self.tp.copy_from(self.initial_tp)

    @classmethod
    def units(cls):
        return cls._units

    @classmethod
    def extend_components(cls, names):
        """
        Allows the user to extend the global `Component` list. This must be called before any streams
        are instantiated. This method is called automatically if the configuration file variable
        ``OPGEE.StreamComponents`` is not empty: set it to a comma-delimited list of component names
        and they will be added to ``Stream.names`` at startup.

        :param names: (iterable of str) the names of new stream components.
        :return: None
        :raises: OpgeeException if any of the names were previously defined stream components.
        """
        name_set = frozenset(names)  # frozenset so we can use as index into _extensions

        if name_set in cls._extensions:
            _logger.debug(f"Redundantly tried to extend components with {names}")
        else:
            cls._extensions[name_set] = True

        # ensure no duplicate names
        bad = name_set.intersection(set(cls._extensions))
        if bad:
            raise OpgeeException(f"extend_components: these proposed extensions are already defined: {bad}")

        _logger.info(f"Extended stream components to include {names}")

        cls.component_names.extend(names)

    @classmethod
    def create_component_matrix(cls):
        """
        Create a pandas DataFrame to hold the 3 phases of the known Components.

        :return: (pandas.DataFrame) Zero-filled stream DataFrame
        """
        return pd.DataFrame(data=0.0, index=cls.component_names, columns=cls._phases, dtype='pint[tonne/day]')

    def is_initialized(self):
        return self.initialized

    def is_uninitialized(self):
        return not self.initialized

    def has_zero_flow(self):
        return self.total_flow_rate().m == 0

    def component_phases(self, name):
        """
        Return the flow rates for all phases of stream component `name`.

        :param name: (str) The name of a stream component
        :return: (pandas.Series) the flow rates for the three phases of component `name`
        """
        return self.components.loc[name]

    def flow_rate(self, name, phase):
        """
        Set the value of the stream component `name` for `phase` to `rate`.

        :param name: (str) the name of a stream component
        :param phase: (str) the name of a phase of matter ('gas', 'liquid' or 'solid')
        :return: (float) the flow rate for the given stream component
        """
        rate = self.components.loc[name, phase]
        return rate

    def total_flow_rate(self):
        """
        total mass flow rate

        :return:
        """
        return self.components.sum(axis='columns').sum()

    def hydrocarbons_rates(self, phase):
        """
        Set rates for each hydrocarbons

        :param phase: (str) the name of a phase of matter ('gas', 'liquid' or 'solid')
        :return: (float) the flow rates for all the hydrocarbons
        """
        return self.flow_rate(self._hydrocarbons + self._liquids, phase)

    def hydrocarbon_rate(self, phase):
        """
        Summarize rates for each hydrocarbon

        :param phase: (str) the name of a phase of matter ('gas', 'liquid' or 'solid')
        :return: (float) the summation of flow rates of all hydrocarbons
        """
        return self.hydrocarbons_rates(phase).sum()

    def total_gases_rates(self):
        """

        :return:
        """
        return self.gas_flow_rate(self._hydrocarbons + self._gases)

    def total_gas_rate(self):
        """

        :return:
        """
        return self.total_gases_rates().sum()

    def set_flow_rate(self, name, phase, rate):
        """
        Set the value of the stream component ``name`` for ``phase` to ``rate``.

        :param name: (str) the name of a stream component
        :param phase: (str) the name of a phase of matter ('gas', 'liquid' or 'solid')
        :param rate: (float) the flow rate for the given stream component
        :return: none
        """
        rate = rate.to("tonne/day") if isinstance(rate, pint.Quantity) else rate
        # TBD: Check that this comment remains true with updates to pint. (If not, update the code)
        # It's currently not possible to assign a Quantity to a DataFrame even if
        # the units match. It's magnitude must be extracted. We check the units first...
        self.components.loc[name, phase] = magnitude(rate, units="tonne/day")
        self.initialized = True

    #
    # Convenience functions
    #
    def gas_flow_rates(self):
        """
        Return all positive gas flows

        :return: (pandas.Series) all flow rates
        """
        gas = self.components.gas
        return gas[gas > 0]

    def gas_flow_rate(self, name):
        """
        Convenience method to get the flow rate of a gas.

        :param name: (str) the name of the component
        :return: (pint.Quantity) the flow rate of the component
        """
        return self.flow_rate(name, PHASE_GAS)

    def liquid_flow_rate(self, name):
        """
        Convenience method to get the flow rate of a liquid.

        :param name: (str) the name of the component
        :return: (pint.Quantity) the flow rate of the component
        """
        return self.flow_rate(name, PHASE_LIQUID)

    def solid_flow_rate(self, name):
        """
        Convenience method to get the flow rate of a solid.

        :param name: (str) the name of the component
        :return: (pint.Quantity) the flow rate of the component
        """
        return self.flow_rate(name, PHASE_SOLID)

    def voc_flow_rates(self):
        return self.components.gas[Stream.VOCs]

    def non_zero_flow_rates(self):
        zero = ureg.Quantity(0.0, 'tonne/day')
        c = self.components
        return c[(c.solid > zero) | (c.liquid > zero) | (c.gas > zero)]

    def set_gas_flow_rate(self, name, rate):
        """
        Convenience method to set the flow rate for a gas.
        """
        return self.set_flow_rate(name, PHASE_GAS, rate)

    def set_liquid_flow_rate(self, name, rate, tp=None):
        """
        Sets the flow rate of a liquid substance
        """
        if tp:
            self.tp.copy_from(tp)

        self.initialized = True
        return self.set_flow_rate(name, PHASE_LIQUID, rate)

    def set_solid_flow_rate(self, name, rate, tp=None):
        """
        Sets the flow rate of a solid substance
        """
        if tp:
            self.tp.copy_from(tp)

        self.initialized = True
        return self.set_flow_rate(name, PHASE_SOLID, rate)

    def set_rates_from_series(self, series, phase):
        """
        set rates from pandas series given phase

        :param series:
        :param phase:
        :return:
        """
        self.initialized = True
        self.components.loc[series.index, phase] = series

    def multiply_factor_from_series(self, series, phase):
        """
        Multiply the flow rates for the given ``phase`` by the values in ``series``

        :param series: (pandas.Series) index must refer to components of `Stream`
        :param phase: (str) one of {'gas', 'liquid', or 'solid'}
        :return:
        """
        self.initialized = True
        self.components.loc[series.index, phase] = series * self.components.loc[series.index, phase]

    def set_electricity_flow_rate(self, rate):
        """
        Set the electricity flow rate.

        :param rate: (pint.Quantity) the flow rate (energy per day)
        :return: none
        """
        self.electricity = rate

    def electricity_flow_rate(self):
        """
        Get the electricity flow rate.

        :return: (pint.Quantity) the flow rate (energy per day)
        """
        return self.electricity

    def set_tp(self, tp):
        """
        Set the stream's temperature and pressure, unless the pressure is zero,
        in which case nothing is done.

        :param tp: (TemperaturePressure) temperature and pressure
        :return: none
        """
        if tp is None:
            raise OpgeeException("Called Stream.set_tp() with None")

        if tp.P.m == 0:
            _logger.warning("Called Stream.set_tp() with zero pressure")
            return

        self.tp = copy(tp)
        self.initialized = True

    def copy_flow_rates_from(self, stream, phase=None, tp=None):
        """
        Copy all mass flow rates from ``stream`` to ``self``

        :param tp: (TemperaturePressure) temperature and pressure to set
        :param phase: (str) one of {'gas', 'liquid', or 'solid'}
        :param stream: (Stream) to copy

        :return: none
        """
        if stream.is_uninitialized():
            raise OpgeeException(f"Can't copy from uninitialized stream: {stream}")

        if phase:
            self.components[phase] = stream.components[phase]
        else:
            self.components[:] = stream.components

        self.electricity = stream.electricity
        self.tp.copy_from(tp or stream.tp)

        self.initialized = True

    def copy_gas_rates_from(self, stream, tp=None):
        """
        Copy gas mass flow rates from ``stream`` to ``self``

        :param stream: (Stream) to copy
        :return: none
        """

        if stream.is_uninitialized():
            raise OpgeeException(f"Can't copy from uninitialized stream: {stream}")

        self.initialized = True
        self.components[PHASE_GAS] = stream.components[PHASE_GAS]

        if tp:
            self.set_tp(tp)

    def copy_liquid_rates_from(self, stream):
        """
        Copy liquid mass flow rates from ``stream`` to ``self``

        :param stream: (Stream) to copy
        :return: none
        """
        if stream.is_uninitialized():
            return OpgeeException(f"copy NULL stream from {stream.name}")

        self.initialized = True
        self.components[PHASE_LIQUID] = stream.components[PHASE_LIQUID]

    def copy_electricity_rate_from(self, stream):
        """
        Copy electricity flow rate from `stream` to `self`

        :param stream: (Stream) to copy electricity from
        :return: none
        """
        self.electricity = stream.electricity

    def multiply_flow_rates(self, factor):
        """
        Multiply all our mass flow and electricity rates by `factor`.

        :param factor: (float) the value to multiply by
        :return: none
        """
        factor = factor.to("fraction") if isinstance(factor, pint.Quantity) else factor
        self.initialized = True

        multiplier = magnitude(factor, 'fraction')
        self.components *= multiplier
        self.electricity *= multiplier

    def add_flow_rate(self, name, phase, rate):
        """
        Add the mass flow ``rate`` to our own.

        :param name: (str) the name of the component
        :param phase: (str) one of {'gas', 'liquid', or 'solid'}
        :param rate: (pint.Quantity) in units of mass/time
        :return: none
        """
        self.set_flow_rate(name, phase, self.flow_rate(name, phase) + rate)

    def add_flow_rates_from(self, stream):
        """
        Add the mass flow rates and electricity rate from `stream` to our own.

        :param stream: (Stream) the source of the rates to add
        :return: none
        """
        if stream.is_uninitialized():
            return

        self.initialized = True
        self.components += stream.components
        self.electricity += stream.electricity


    def subtract_rates_from(self, stream, phase=PHASE_GAS):
        """
        Subtract the gas mass flow rates of ``stream`` from our own.

        :param phase: solid, liquid, gas phase
        :param stream: (Stream) the source of the rates to subtract
        :return: none
        """
        if stream.is_uninitialized():
            return

        self.initialized = True
        self.components[phase] -= stream.components[phase]

    def add_combustion_CO2_from(self, stream):
        """
        Compute the amount of CO2 from the combustible components in `stream`
        and add these to ``self`` as CO2, assuming complete combustion.

        :param stream: (Stream) a Stream with combustible components
        :return: (pint.Quantity(unit="tonne/day")) the mass rate of CO2 from combustion.
        """
        from .thermodynamics import ChemicalInfo    # avoids circular imports (stream <-> thermodynamics)

        component_MW = ChemicalInfo.mol_weights()

        combustibles = stream.combustible_components

        rate = (stream.components.loc[combustibles, PHASE_GAS] / component_MW[combustibles] *
                Stream.carbon_number * component_MW["CO2"]).sum()

        self.set_flow_rate("CO2", PHASE_GAS, rate)      # sets initialized flag
        return rate

    def contains(self, stream_type):
        """
        Return whether ``stream_type`` is one of named contents of ``self``.

        :param stream_type: (str) a symbolic name for contents of `stream`
        :return: (bool) True if `stream_type` is among the contents of `stream`
        """
        return stream_type in self.contents

    @classmethod
    def from_xml(cls, elt):
        """
        Instantiate an instance from an XML element

        :param elt: (etree.Element) representing a <Stream> element
        :return: (Stream) instance of class Stream
        """
        a = elt.attrib
        src = a['src']
        dst = a['dst']
        name = a.get('name') or f"{src} => {dst}"
        impute = getBooleanXML(a.get('impute', "1"))

        # There should be 2 attributes: temperature and pressure
        attr_dict = cls.instantiate_attrs(elt)
        expected = {'temperature', 'pressure'}
        if set(attr_dict.keys()) != expected:
            raise OpgeeException(f"Stream {name}: expected 2 attributes, {expected}")

        temp = attr_dict['temperature'].value
        pres = attr_dict['pressure'].value
        tp = TemperaturePressure(temp, pres)

        contents = [node.text for node in elt.findall('Contains')]

        # Set up the stream component info, if provided
        comp_elts = elt.findall('Component')
        has_exogenous_data = len(comp_elts) > 0

        if has_exogenous_data:
            matrix = cls.create_component_matrix()

            for comp_elt in comp_elts:
                a = comp_elt.attrib
                comp_name = elt_name(comp_elt)
                rate = coercible(comp_elt.text, float)
                phase = a['phase']  # required by XML schema to be one of the 3 legal values

                # convert hydrocarbon molecule name to carbon number format
                if is_hydrocarbon(comp_name):
                    comp_name = molecule_to_carbon(comp_name)

                if comp_name not in matrix.index:
                    raise OpgeeException(f"Unrecognized stream component name '{comp_name}'.")

                matrix.loc[comp_name, phase] = rate

        else:
            matrix = None  # let the stream create it

        obj = Stream(name, tp, comp_matrix=matrix, src_name=src, dst_name=dst,
                     contents=contents, impute=impute)

        return obj

    @property
    def hydrocarbons(self):
        return self._hydrocarbons
