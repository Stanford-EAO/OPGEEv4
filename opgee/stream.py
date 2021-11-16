'''
.. OPGEE stream support

.. Copyright (c) 2021 Richard Plevin and Adam Brandt
   See the https://opensource.org/licenses/MIT for license details.
'''
import pandas as pd
import pint_pandas
import pint
import re

from . import ureg
from .attributes import AttributeMixin
from .core import XmlInstantiable, elt_name, magnitude
from .error import OpgeeException
from .log import getLogger
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
    flow rates (e.g., Mg per day). The default set of substances is defined by ``Stream.components`` but can be
    extended by the user to include other substances, by setting the configuration file variable
    `OPGEE.StreamComponents`.

    Streams are defined within the `<Field>` element and are stored in a `Field` instance. The `Field` class tracks
    all `Stream` instances in a dictionary keyed by `Stream` name.
    """
    _phases = [PHASE_SOLID, PHASE_LIQUID, PHASE_GAS]

    # HCs with 1-60 carbon atoms, i.e., C1, C2, ..., C50
    max_carbon_number = 50
    _hydrocarbons = [f'C{n}' for n in range(1, max_carbon_number + 1)]

    # All hydrocarbon gases other than methane (C1) are considered VOCs.
    VOCs = _hydrocarbons[1:]

    _solids = ['PC']  # petcoke
    _liquids = ['oil']

    # _hc_molecules = ['CH4', 'C2H6', 'C3H8', 'C4H10']
    _gases = ['N2', 'O2', 'CO2', 'H2O', 'H2', 'H2S', 'SO2', "CO"]
    _other = ['Na+', 'Cl-', 'Si-']

    emission_composition = _hydrocarbons + _gases
    _carbon_number_dict = {f'C{n}': float(n) for n in range(1, max_carbon_number + 1)}

    for gas in _gases:
        _carbon_number_dict[gas] = 1 if gas[0] == "C" else 0
    carbon_number = pd.Series(_carbon_number_dict, dtype="pint[dimensionless]")


    #: The stream components tracked by OPGEE. This list can be extended by calling ``Stream.extend_components(names)``,
    #: or more simply by defining configuration file variable ``OPGEE.StreamComponents``.
    components = _solids + _liquids + _gases + _other + _hydrocarbons

    # Remember extensions to avoid applying any redundantly.
    # Value is a dict keyed by set(added_component_names).
    _extensions = {}

    _units = ureg.Unit('tonne/day')

    def __init__(self, name, number=0, temperature=None, pressure=None,
                 src_name=None, dst_name=None, comp_matrix=None, contents=None, impute=True):
        super().__init__(name)

        self.components = self.create_component_matrix() if comp_matrix is None else comp_matrix
        self.number = number
        self.temperature = temperature if isinstance(temperature, pint.Quantity) else ureg.Quantity(temperature, "degF")
        self.pressure = pressure if isinstance(pressure, pint.Quantity) else ureg.Quantity(pressure, "psi")
        self.src_name = src_name
        self.dst_name = dst_name

        self.src_proc = None  # set in Field.connect_processes()
        self.dst_proc = None

        self.contents = contents or []

        self.impute = impute
        self.has_exogenous_data = False

        # indicates whether any data have been written to the stream yet
        self.dirty = comp_matrix is not None

    def _after_init(self):
        self.check_attr_constraints(self.attr_dict)

    def __str__(self):
        number_str = f" #{self.number}" if self.number else ''
        return f"<Stream '{self.name}'{number_str}>"

    def reset(self):
        """
        Reset an existing `Stream` to a state suitable for re-running the model.

        :return: none
        """
        self.components = self.create_component_matrix()
        self.temperature = ureg.Quantity(0.0, "degF")
        self.pressure = ureg.Quantity(0.0, "psia")
        self.dirty = False

    @classmethod
    def units(cls):
        return cls._units

    @classmethod
    def extend_components(cls, names):
        """
        Allows the user to extend the global `Component` list. This must be called before any streams
        are instantiated. This method is called automatically if the configuration file variable
        ``OPGEE.StreamComponents`` is not empty: set it to a comma-delimited list of component names
        and they will be added to ``Stream.components`` at startup.

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

        cls.components.extend(names)

    @classmethod
    def create_component_matrix(cls):
        """
        Create a pandas DataFrame to hold the 3 phases of the known Components.

        :return: (pandas.DataFrame) Zero-filled stream DataFrame
        """
        return pd.DataFrame(data=0.0, index=cls.components, columns=cls._phases, dtype='pint[tonne/day]')

    def is_empty(self):
        return not self.dirty

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
        Summarize rates for each hydrocarbons

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
        Set the value of the stream component `name` for `phase` to `rate`.

        :param name: (str) the name of a stream component
        :param phase: (str) the name of a phase of matter ('gas', 'liquid' or 'solid')
        :param rate: (float) the flow rate for the given stream component
        :return: None
        """
        # TBD: it's currently not possible to assign a Quantity to a DataFrame even if
        # TBD: the units match. It's magnitude must be extracted. We check the units first...
        self.components.loc[name, phase] = magnitude(rate, units=self.units())
        self.dirty = True

    #
    # Convenience functions
    #
    def gas_flow_rate(self, name):
        """Calls ``self.flow_rate(name, PHASE_GAS)``"""
        return self.flow_rate(name, PHASE_GAS)

    def liquid_flow_rate(self, name):
        """Calls ``self.flow_rate(name, PHASE_LIQUID)``"""
        return self.flow_rate(name, PHASE_LIQUID)

    def solid_flow_rate(self, name):
        """Calls ``self.flow_rate(name, PHASE_SOLID)``"""
        return self.flow_rate(name, PHASE_SOLID)

    def set_gas_flow_rate(self, name, rate):
        """Calls ``self.set_flow_rate(name, PHASE_GAS, rate)``"""
        self.dirty = True
        return self.set_flow_rate(name, PHASE_GAS, rate)

    def set_liquid_flow_rate(self, name, rate, t=None, p=None):
        """Calls ``self.set_flow_rate(name, PHASE_LIQUID, rate)``"""
        if t is not None:
            self.temperature = t
        if p is not None:
            self.pressure = p

        self.dirty = True
        return self.set_flow_rate(name, PHASE_LIQUID, rate)

    def set_solid_flow_rate(self, name, rate):
        """Calls ``self.set_flow_rate(name, PHASE_SOLID, rate)``"""
        self.dirty = True
        return self.set_flow_rate(name, PHASE_SOLID, rate)

    def set_rates_from_series(self, series, phase):
        """
        set rates from pandas series given phase

        :param series:
        :param phase:
        :return:
        """
        self.dirty = True
        self.components.loc[series.index, phase] = series

    def multiply_factor_from_series(self, series, phase):
        """
        multiply from series

        :param series:
        :param phase:
        :return:
        """
        self.dirty = True
        self.components.loc[series.index, phase] = series * self.components.loc[series.index, phase]

    def set_temperature_and_pressure(self, t, p):
        self.temperature = t
        self.pressure = p
        self.dirty = True

    def copy_flow_rates_from(self, stream, phase=None):
        """
        Copy all mass flow rates from `stream` to `self`

        :param phase: solid, liquid and gas phase
        :param stream: (Stream) to copy

        :return: none
        """
        if phase:
            self.components[phase] = stream.components[phase]
        else:
            self.components[:] = stream.components

        self.dirty = True


    def copy_gas_rates_from(self, stream):
        """
        Copy gas mass flow rates from `stream` to `self`

        :param stream: (Stream) to copy
        :return: none
        """
        self.dirty = True
        self.components[PHASE_GAS] = stream.components[PHASE_GAS]

    def copy_liquid_rates_from(self, stream):
        """
        Copy liquid mass flow rates from `stream` to `self`

        :param stream: (Stream) to copy
        :return: none
        """
        self.dirty = True
        self.components[PHASE_LIQUID] = stream.components[PHASE_LIQUID]

    def multiply_flow_rates(self, factor):
        """
        Multiply all our mass flow rates by `factor`.

        :param factor: (float) what to multiply by
        :return: none
        """
        self.dirty = True
        self.components *= magnitude(factor, 'fraction')

    def add_flow_rates_from(self, stream):
        """
        Add the mass flow rates from `stream` to our own.

        :param stream: (Stream) the source of the rates to add
        :return: none
        """
        self.dirty = True
        self.components += stream.components

    def subtract_gas_rates_from(self, stream):
        """
        Subtract the gas mass flow rates of `stream` from our own.

        :param stream: (Stream) the source of the rates to subtract
        :return: none
        """
        self.dirty = True
        self.components[PHASE_GAS] -= stream.components[PHASE_GAS]

    # @classmethod
    # def combine(cls, streams, temperature=None, pressure=None):
    #     """
    #     Thermodynamically combine multiple streams' components into a new
    #     anonymous Stream. This is used on input streams since it makes no
    #     sense for output streams.
    #
    #     :param streams: (list of Streams) the Streams to combine
    #     :return: (Stream) if len(streams) > 1, returns a new Stream. If
    #        len(streams) == 1, the original stream is returned.
    #     """
    #     from statistics import mean
    #
    #     if len(streams) == 1:  # corner case
    #         return streams[0]
    #
    #     matrices = [stream.components for stream in streams]
    #
    #     comp_matrix = sum(matrices)
    #     numerator = 0
    #     denumerator = 0
    #     for stream in streams:
    #         total_mass_rate = stream.components.sum().sum()
    #         numerator += stream.temperature * total_mass_rate * cls.mixture_heat_capacity(stream)
    #         denumerator += total_mass_rate * cls.mixture_heat_capacity(stream)
    #     temperature = numerator / denumerator
    #     pressure = pressure if pressure is not None else mean([stream.pressure for stream in streams])
    #     stream = Stream('-', temperature=temperature, pressure=pressure, comp_matrix=comp_matrix)
    #     return stream
    #
    # @staticmethod
    # def mixture_heat_capacity(stream):
    #     """
    #     cp_mix = (mass_1/mass_mix)cp_1 + (mass_2/mass_mix)cp_2 + ...
    #
    #     :param stream:
    #     :return: (float) heat capacity of mixture (unit = btu/degF/day)
    #     """
    #     temperature = stream.temperature
    #     total_mass_rate = stream.components.sum().sum()
    #     oil_heat_capacity = stream.hydrocarbon_rate(PHASE_LIQUID) * Oil().specific_heat(temperature)
    #     water_heat_capacity = Water().heat_capacity(stream)
    #     gas_heat_capacity = Gas().heat_capacity(stream)
    #
    #     heat_capacity = (oil_heat_capacity + water_heat_capacity + gas_heat_capacity) / total_mass_rate
    #     return heat_capacity

    def contains(self, stream_type):
        """
        Return whether `stream_type` is one of named contents of `stream`.

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

        # The following are optional
        number_str = a.get('number')
        number = coercible(number_str, int, raiseError=False) if number_str else None

        # There should be 2 attributes: temperature and pressure
        attr_dict = cls.instantiate_attrs(elt)
        expected = {'temperature', 'pressure'}
        if set(attr_dict.keys()) != expected:
            raise OpgeeException(f"Stream {name}: expected 2 attributes, {expected}")

        temp = attr_dict['temperature'].value
        pres = attr_dict['pressure'].value

        contents = [node.text for node in elt.findall('Contains')]

        obj = Stream(name, number=number, temperature=temp, pressure=pres,
                     src_name=src, dst_name=dst, contents=contents, impute=impute)
        comp_df = obj.components  # this is an empty DataFrame; it is filled in below or at runtime

        # Set up the stream component info
        comp_elts = elt.findall('Component')
        obj.has_exogenous_data = len(comp_elts) > 0

        for comp_elt in comp_elts:
            a = comp_elt.attrib
            comp_name = elt_name(comp_elt)
            rate = coercible(comp_elt.text, float)
            phase = a['phase']  # required by XML schema to be one of the 3 legal values

            # convert hydrocarbon molecule name to carbon number format
            if is_hydrocarbon(comp_name):
                comp_name = molecule_to_carbon(comp_name)

            if comp_name not in comp_df.index:
                raise OpgeeException(f"Unrecognized stream component name '{comp_name}'.")

            # TBD: if stream is to include electricity, it will be in MWh/day
            comp_df.loc[comp_name, phase] = rate

        return obj

    @property
    def hydrocarbons(self):
        return self._hydrocarbons
