#
# Field class
#
# Author: Richard Plevin and Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
import networkx as nx
import pint

from . import ureg
from .config import getParamAsList
from .container import Container
from .core import elt_name, instantiate_subelts, dict_from_list, TemperaturePressure, STP
from .energy import Energy
from .error import (OpgeeException, OpgeeStopIteration, OpgeeMaxIterationsReached,
                    OpgeeIterationConverged, ModelValidationError, ZeroEnergyFlowError)
from .import_export import ImportExport
from .log import getLogger
from .process import Process, Aggregator, Reservoir
from .process_groups import ProcessChoice
from .processes.steam_generator import SteamGenerator
from .smart_defaults import SmartDefault
from .stream import Stream
from .thermodynamics import Oil, Gas, Water, MultiOil
from .processes.steam_generator import SteamGenerator
from .utils import getBooleanXML, flatten, roundup

_logger = getLogger(__name__)


class Field(Container):
    """
    A `Field` contains all the `Process` instances associated with a single oil or
    gas field, and the `Stream` instances that connect them. It also holds an instance
    of `Reservoir`, which is a source (it has outputs only), in the process structure.

    Fields can contain mutually exclusive process choice sets that group processes to
    be enabled or disabled together as a coherent group. The "active" set is determimed
    by the value of attributes named the same as the `<ProcessChoice>` element.

    See {opgee}/etc/attributes.xml for attributes defined for the `<Field>`.
    See also :doc:`OPGEE XML documentation <opgee-xml>`
    """

    def __init__(self, name, attr_dict=None, aggs=None, procs=None, streams=None, group_names=None,
                 process_choice_dict=None):

        # Note that `procs` include only Processes defined at the top-level of the field.
        # Other Processes maybe defined within the Aggregators in `aggs`.
        super().__init__(name, attr_dict=attr_dict, aggs=aggs, procs=procs)

        self.model = None  # set in _after_init

        self.group_names = group_names
        self.stream_dict = dict_from_list(streams)

        # Remember streams that declare themselves as system boundaries. Keys must be one of the
        # values in the tuples in the _known_boundaries dictionary above.
        self.boundary_dict = boundary_dict = {}
        self.oil_mode = None

        # DOCUMENT: boundary names must be predefined, but can be set in configuration.
        #   Each name must appear 0 or 1 times, and at least one boundary must be defined.
        self.known_boundaries = known_boundaries = set(getParamAsList('OPGEE.Boundaries'))

        # Save references to boundary processes by name; fail if duplicate definitions are found.
        for proc in procs:
            boundary = proc.boundary
            if boundary:
                if boundary not in known_boundaries:
                    raise OpgeeException(
                        f"{self}: {proc} boundary {boundary} is not a known boundary name. Must be one of {known_boundaries}")

                other = boundary_dict.get(boundary)
                if other:
                    raise OpgeeException(
                        f"{self}: Duplicate declaration of boundary '{boundary}' in {proc} and {other}")

                boundary_dict[boundary] = proc
                #_logger.debug(f"{self}: {proc} defines boundary '{boundary}'")

        self.process_choice_dict = process_choice_dict

        # Each Field has one of these built-in processes
        self.reservoir = Reservoir()

        # Additional builtin processes can be instantiated and added here if needed
        self.builtin_procs = [self.reservoir]

        all_procs = self.collect_processes()  # includes Reservoir
        self.process_dict = self.adopt(all_procs, asDict=True)

        self.agg_dict = {agg.name : agg for agg in self.descendant_aggs()}

        self.extend = False

        # Stores the name of a Field that the current field copies then modifies
        # If a Field named X appears in an Analysis element, and specifies that it
        # modifies another Field Y, Field Y is copied and any elements defined within
        # Field X are merged into the copy, and the copy is added to the Model with the
        # new name. The "modifies" value is stored to record this behavior.
        self.modifies = None

        self.carbon_intensity = ureg.Quantity(0.0, "g/MJ")
        self.procs_beyond_boundary = None

        self.graph = self.cycles = None

        self.process_data = {}

        # Set in _after_init()
        self.m_oil = self.oil = self.gas = self.water = self.steam_generator = None

        self.wellhead_tp = None

        self.stp = STP

        self.import_export = ImportExport()

    def _check_run_after_procs(self):
        """
        For procs tagged 'after="True"', allow outputs only to other "after" procs.
        """
        def _run_after_ok(proc):
            for dst in proc.successors():
                if not dst.run_after:
                    return False
            return True

        bad = [proc for proc in self.processes() if proc.run_after and not _run_after_ok(proc)]
        if bad:
            # DOCUMENT after=True attribute
            raise OpgeeException(f"Processes {bad} are tagged 'after=True' but have output streams to non-'after' processes")

        return True

    def _after_init(self):
        self.check_attr_constraints(self.attr_dict)

        self.model = model = self.find_parent('Model')

        self.LNG_temp = model.const("LNG-temp")

        # TODO: not used anywhere
        # self.stab_column = self.attr("stabilizer_column")

        self.upgrader_type = self.attr("upgrader_type")     # used only in smart default

        self.prime_mover_type_lifting = self.attr("prime_mover_type_gas_lifting")
        self.eta_compressor_lifting = self.attr("eta_compressor_lifting")

        self.wellhead_tp = TemperaturePressure(self.attr("wellhead_temperature"), self.attr("wellhead_pressure"))

        # TODO: Why are these copied into the Field object? Why not access them from Model?
        # TODO: It's good practice to declare all instance vars in __init__ (set to None perhaps)
        #       other programmers (and PyCharm) recognize them as proper instance variables and
        #       not random values set in other methods.
        self.transport_share_fuel = model.transport_share_fuel
        self.transport_parameter = model.transport_parameter
        self.transport_by_mode = model.transport_by_mode
        self.upstream_CI = model.upstream_CI
        self.vertical_drill_df = model.vertical_drill_df
        self.horizontal_drill_df = model.horizontal_drill_df

        self.imported_gas_comp = model.imported_gas_comp

        self.oil = Oil(self)
        self.gas = Gas(self)
        self.water = Water(self)
        self.m_oil = MultiOil(self)
        self.steam_generator = SteamGenerator(self)

        SmartDefault.apply_defaults(None, self)
        self.resolve_process_choices()  # allows smart defaults to set process choices
        self._check_run_after_procs()       # TBD: write test (also, move call to validate()?

        # TBD: Document the "_after_init" processing order
        # for iterator in [self.processes(), self.streams()]:
        for obj in self.processes():
            obj._after_init()

        # we use networkx to reason about the directed graph of Processes (nodes)
        # and Streams (edges).
        self.graph = g = self._connect_processes()

        self.cycles = cycles = list(nx.simple_cycles(g))

        # if cycles:
        #     _logger.debug(f"Field '{self.name}' has cycles: {cycles}")



    def __str__(self):
        return f"<Field '{self.name}'>"

    def _impute(self):
        # recursive helper function
        def _impute_upstream(proc):
            # recurse upstream, calling impute(), but don't cycle
            if proc and proc.enabled and not proc.visited():
                proc.visit()
                proc.impute()

                upstream_procs = {stream.src_proc for stream in proc.inputs if stream.impute}
                for upstream_proc in upstream_procs:
                    _impute_upstream(upstream_proc)

        start_streams = self.find_start_streams()

        for stream in start_streams:
            if not stream.impute:
                raise OpgeeException(f"A start stream {stream} cannot have its 'impute' flag set to '0'.")

        # Find procs with start == True or find start_procs upstream from streams with exogenous data.from
        # We require that all start streams emerge from one Process.
        start_procs = {p for p in self.processes() if p.impute_start} or {stream.src_proc for stream in start_streams}

        start_count = len(start_procs)
        # No impute
        if start_count == 0:
            return

        if start_count != 1:
            procs = f": {start_procs}" if start_count else ""

            raise OpgeeException(
                f"Expected one start process upstream from start streams, got {len(start_procs)}{procs}")

        start_proc = start_procs.pop()
        _logger.debug(f"Running impute() for {start_proc}")

        try:
            _impute_upstream(start_proc)
        except OpgeeStopIteration:
            # TODO: shouldn't be possible
            raise OpgeeException("Impute failed due to a process loop. Use Stream attribute impute='0' to break cycle.")

    def run(self, analysis, compute_ci=True, smart_defaults=True):
        """
        Run all Processes defined for this Field, in the order computed from the graph
        characteristics, using the settings in `analysis` (e.g., GWP).

        :param analysis: (Analysis) the `Analysis` to use for analysis-specific settings.
        :param compute_ci: (bool) if False, CI calculation is not performed (used by some tests)
        :param smart_defaults: (bool) if False, don't run smart defaults. (For testing only.)
        :return: None
        """
        if self.is_enabled():
            _logger.info(f"Running '{self}'")

            # Cache the sets of processes within and outside the current boundary. We use
            # this information in compute_carbon_intensity() to ignore irrelevant procs.
            boundary_proc = self.boundary_process(analysis)
            self.oil_mode = self.set_oil_mode(analysis)

            if self.oil_mode == "comp_oil":
                self.oil = self.m_oil

            self.procs_beyond_boundary = boundary_proc.beyond_boundary()

            self.reset()
            # if smart_defaults:
            #     SmartDefault.apply_defaults(analysis, self)
            #     self.resolve_process_choices()  # allows smart defaults to set process choices

            self._impute()
            self.reset_iteration()
            self.run_processes(analysis)

            self.check_balances()

            # Perform aggregations
            self.get_energy_rates()

            self.get_emission_rates(analysis, procs_to_exclude=self.procs_beyond_boundary)
            self.carbon_intensity = self.compute_carbon_intensity(analysis) if compute_ci else None


    def reset(self):
        self.reset_streams()
        self.reset_processes()

    def reset_iteration(self):
        Process.clear_iterating_process_list()
        for proc in self.processes():
            proc.reset_iteration()

    def reset_processes(self):
        for proc in self.processes():
            proc.reset()  # also resets iteration

    def reset_streams(self):
        for stream in self.streams():
            # If a stream is disabled, leave it so. Otherwise disable it if either of
            # its source or destination processes is disabled.
            if stream.enabled and not (stream.src_proc.enabled and stream.dst_proc.enabled):
                stream.set_enabled(False)

            stream.reset()

    def check_balances(self):
        for p in self.processes():
            p.check_balances()

    def boundary_processes(self):
        boundary_procs = [proc for proc in self.processes() if proc.boundary]
        return boundary_procs

    def boundary_process(self, analysis) -> Process:
        """
        Return the currently chosen boundary process.

        :return: (opgee.Process) the currently chosen boundary process
        """
        try:
            return self.boundary_dict[analysis.boundary]
        except KeyError:
            raise OpgeeException(f"{self} does not declare boundary process '{analysis.boundary}'.")

    def set_oil_mode(self, analysis) -> str:
        # TODO sz parallel implementation not finished
        """
        Return the currently chosen oil mode.

        :return: (str) the currently chosen oil mode
        """
        try:
            analysis.oil_mode in ["black_oil", "comp_oil"]
            return analysis.oil_mode
        except KeyError:
            raise OpgeeException(f"{self} does not declare oil mode '{analysis.oil_mode}'.")

    def defined_boundaries(self):
        """
        Return the names of all boundaries defined in configuration system)
        """
        return self.known_boundaries

    def boundary_energy_flow_rate(self, analysis, raiseError=True):
        """
        Return the energy flow rate for the user's chosen system boundary, functional unit
        (oil vs gas)

        :param analysis: (Analysis) the analysis this field is part of
        :param raiseError: (bool) whether to raise an error if the energy flow is zero at the boundary
        :return: (pint.Quantity) the energy flow at the boundary
        """
        boundary_proc = self.boundary_process(analysis)
        stream = boundary_proc.sum_input_streams()

        # TODO: displacement method
        obj = self.oil if analysis.fn_unit == 'oil' else self.gas
        # TODO: Add method to calculate petrocoke energy flow rate
        energy = obj.energy_flow_rate(stream)

        if energy.m == 0:
            if raiseError:
                raise ZeroEnergyFlowError(boundary_proc)
            else:
                _logger.warning(f"Zero energy flow rate for {boundary_proc.boundary} boundary process {boundary_proc}")

        return energy

    def compute_carbon_intensity(self, analysis):
        """
        Compute carbon intensity by summing emissions from all processes within the
        selected system boundary and dividing by the flow of the functional unit
        across that boundary stream.

        :param analysis: (Analysis) the analysis this field is part of
        :return: (pint.Quantity) carbon intensity in units of g CO2e/MJ
        """
        rates = self.emissions.rates(analysis.gwp)
        onsite_emissions = rates.loc['GHG'].sum()
        net_import = self.get_net_imported_product()
        imported_emissions = self.get_imported_emissions(net_import)
        total_emissions = onsite_emissions + imported_emissions

        #TODO: add option for displacement method
        # fn_unit = NATURAL_GAS if analysis.fn_unit == 'gas' else CRUDE_OIL
        # byproduct_names = self.product_names.drop(fn_unit)
        # byproduct_carbon_credit = self.get_carbon_credit(byproduct_names, analysis)
        # total_emissions = onsite_emissions + imported_emissions - byproduct_carbon_credit
        # energy = self.boundary_energy_flow_rate(analysis)

        # export_df = self.import_export.export_df
        #export_LHV = export_df.drop(columns=["Water"]).sum(axis='columns').sum()
        # self.carbon_intensity = ci = (total_emissions / export_LHV).to('grams/MJ')

        boundary_energy_flow_rate = self.boundary_energy_flow_rate(analysis)
        self.carbon_intensity = ci = (total_emissions / boundary_energy_flow_rate).to('grams/MJ')

        return ci

    def get_imported_emissions(self, net_import):
        """
        Calculate imported product emissions based on the upstream CI from GREET1_2016

        :param net_import: (Pandas.Series) net import energy rates (water is mass rate)
        :return: total emissions (units of g CO2)
        """
        from .import_export import WATER

        imported_emissions = ureg.Quantity(0.0, "tonne/day")

        for product, energy_rate in net_import.items():
            # TODO: Water is not in self.upstream_CI and not in upstream-CI.csv,
            #  which has units of g/mmbtu
            if product == WATER:
                continue

            energy_rate = (energy_rate if isinstance(energy_rate, pint.Quantity)
                           else ureg.Quantity(energy_rate, "mmbtu/day"))

            if energy_rate.m > 0:
                imported_emissions += energy_rate * self.upstream_CI.loc[product, "EF"]

        return imported_emissions

    # TODO Is this function deprecated or just not used yet?
    def get_carbon_credit(self, byproduct_names, analysis):
        """
        Calculate carbon credit from byproduct

        :param net_import: (Pandas.Series) net import energy rates (water is mass rate)
        :return: total emissions (units of g CO2)
        """

        carbon_credit = ureg.Quantity(0.0, "tonne/day")
        export = self.import_export.export_df
        process_names = set(export.index)
        for name in byproduct_names:
            process_name = self.product_boundaries.loc[name, analysis.boundary]
            if process_name and process_name in process_names:
                carbon_credit += export.loc[process_name, name] * self.upstream_CI.loc[name, "EF"]

        return carbon_credit

    def validate(self):
        """
        Perform logical checks on the field after loading the entire model to ensure the field
        is "well-defined". This allows the processing code to avoid testing validity at run-time.
        Field conditions include:

        - Cycles cannot span the current boundary.
        - Aggregators cannot span the current boundary.
        - The chosen system boundary is defined for this field
        - Logical contradictions in attribute some settings

        :return: none
        :raises ModelValidationError: raised if any validation condition is violated.
        """

        # Accumulate error msgs so user can correct them all at once.
        msgs = []

        for proc in self.boundary_processes():
            # Cycles cannot span the current boundary. Test this by checking that the boundary
            # proc is not in any cycle. (N.B. __init__ evaluates and stores cycles.)

            # Check that there are Processes outside the current boundary. If not, nothing more to do.
            beyond = proc.beyond_boundary()
            if not beyond:
                continue

            for cycle in self.cycles:
                if proc in cycle:
                    msgs.append(f"{proc.boundary} boundary {proc} is in one or more cycles.")
                    break

            # There will generally be far fewer Processes outside the system boundary than within,
            # so we check that procs outside the boundary are not in Aggregators with members inside.
            aggs = self.descendant_aggs()
            for agg in aggs:
                procs = agg.descendant_procs()
                if not procs:
                    continue

                # See if first proc is inside or beyond the boundary, then make sure the rest are the same
                is_inside = procs[0] not in beyond
                is_beyond = not is_inside  # improves readability
                for proc in procs:
                    if (is_inside and proc in beyond) or (is_beyond and proc not in beyond):
                        msgs.append(f"{agg} spans the {proc.boundary} boundary.")

        if self.attr("steam_flooding") and not self.attr("SOR"):
            msgs.append("SOR cannot be 0 when steam_flooding is chosen")

        if msgs:
            msg = "\n - ".join(msgs)
            raise ModelValidationError(f"Field validation failed: {msg}")

    def report(self, include_streams=False):
        """
        Print a text report showing Streams, energy, and emissions.
        """
        from .utils import dequantify_dataframe

        name = self.name

        if include_streams:
            _logger.debug(f"\n*** Streams for field '{name}'")
            for stream in self.streams():
                _logger.debug(f"{stream} (tonne/day)\n{dequantify_dataframe(stream.components)}\n")

        _logger.debug(f"{self}\nEnergy consumption:\n{self.energy.data}")
        _logger.debug(f"\nCumulative emissions to environment (tonne/day):\n{dequantify_dataframe(self.emissions.data)}")
        _logger.debug(f"CI: {self.carbon_intensity:.2f}")

    def _is_cycle_member(self, process):
        """
        Return True if `process` is a member of any process cycle.

        :param process: (Process)
        :return: (bool)
        """
        return any([process in cycle for cycle in self.cycles])

    def _depends_on_cycle(self, process, visited=None):
        visited = visited or set()

        for predecessor in process.predecessors():
            if predecessor in visited:
                return True

            visited.add(predecessor)
            if self._depends_on_cycle(predecessor, visited=visited):
                return True

        return False

    def _compute_graph_sections(self):
        """
        Divide the nodes of ``self.graph`` into four disjoint sets:
        1. Nodes neither in cycle nor dependent on cycles
        2. Nodes in cycles
        3. Nodes dependent on cycles
        4. Nodes tagged "after='true'" in the XML, sorted topologically

        :return: (4-tuple of sets of Processes)
        """
        processes = self.processes()

        enabled_procs_cycles = []
        for cycle in self.cycles:
            for proc in cycle:
                if proc.enabled:
                    enabled_procs_cycles.append(proc)

        procs_in_cycles = set(enabled_procs_cycles) if enabled_procs_cycles else set()
        cycle_dependent = set()

        if enabled_procs_cycles:
            for process in processes:
                if process not in procs_in_cycles and self._depends_on_cycle(process):
                    cycle_dependent.add(process)

        run_afters = {process for process in processes if process.run_after}

        cycle_independent = set(processes) - procs_in_cycles - cycle_dependent - run_afters
        return cycle_independent, procs_in_cycles, cycle_dependent, run_afters

    def run_processes(self, analysis):
        cycle_independent, procs_in_cycles, cycle_dependent, run_afters = self._compute_graph_sections()

        for proc in procs_in_cycles:
            proc.in_cycle = True

        # helper function
        def run_procs_in_order(processes):
            if not processes:
                return

            sg = self.graph.subgraph(processes)
            run_order = nx.topological_sort(sg)
            for proc in run_order:
                proc.run_if_enabled(analysis)

        # run all the cycle-independent nodes in topological order
        run_procs_in_order(cycle_independent)

        # If user has indicated a process with start-cycle="true", start there, otherwise
        # find a process with cycle-independent processes as inputs, and start there.
        start_procs = [proc for proc in procs_in_cycles if proc.cycle_start]

        if len(start_procs) > 1:
            raise OpgeeException(
                f"""Only one process can have cycle-start="true"; found {len(start_procs)}: {start_procs}""")

        max_iter = self.model.maximum_iterations

        if procs_in_cycles:
            # Walk the cycle, starting at the indicated start process to generate an ordered list
            unvisited = procs_in_cycles.copy()

            if start_procs:
                ordered_cycle = []

                # recursive function to walk successors until we've visited all the procs in cycles
                def process_successors(proc):
                    if proc in unvisited:
                        unvisited.remove(proc)
                        ordered_cycle.append(proc)

                        for successor in proc.successors():
                            process_successors(successor)

                process_successors(start_procs[0])

                # add in any processes in cycles not reachable from the start proc
                for other in list(unvisited):
                    process_successors(other)

            else:
                # TBD: Compute ordering by looking for procs in cycle that are successors to
                #      cycle_independent procs. For now, just copy run using procs_in_cycles.
                ordered_cycle = procs_in_cycles

            # Iterate on the processes in cycle until a termination condition is met and an
            # OpgeeStopIteration exception is thrown, or we exceed max iterations.
            iter_count = 0
            while True:
                iter_count += 1
                if iter_count > max_iter:
                    raise OpgeeMaxIterationsReached(f"Maximum iterations ({max_iter}) reached without convergence")

                try:
                    for proc in ordered_cycle:
                        proc.run_if_enabled(analysis)

                except OpgeeIterationConverged as e:
                    _logger.debug(e)
                    break

        # run all processes dependent on cycles, which are now complete
        run_procs_in_order(cycle_dependent)

        # finally, run all "after='True'" procs, in sort order
        run_procs_in_order(run_afters)

    def _connect_processes(self):
        """
        Connect streams and processes in a directed graph.

        :return: (networkx.DiGraph) a directed graph representing the processes and streams.
        """
        g = nx.MultiDiGraph()  # allows parallel edges

        # first add all defined Processes since some (Exploration, Development & Drilling)
        # have no streams associated with them, but we still need to run the processes.
        for p in self.processes():
            g.add_node(p)
            p.inputs.clear()   # since we append to inputs and outputs below
            p.outputs.clear()

        for s in self.streams():
            s.src_proc = src = self.find_process(s.src_name)
            s.dst_proc = dst = self.find_process(s.dst_name)

            src.add_output_stream(s)
            dst.add_input_stream(s)

            g.add_edge(src, dst, stream=s)

        return g

    def streams(self):
        """
        Gets all enabled `Stream` instances for this `Field`.

        :return: (iterator of `Stream` instances) streams in this `Field`
        """
        return [s for s in self.stream_dict.values() if s.enabled]

    def processes(self):
        """
        Gets all instances of subclasses of `Process` for this `Field`.

        :return: (iterator of `Process` (subclasses) instances) in this `Field`
        """
        procs = [proc for proc in self.all_processes() if proc.is_enabled()]
        return procs

    def all_processes(self):
        """
        Gets all instances of subclasses of `Process` for this `Field`, including
        disabled Processes.

        :return: (iterator of `Process` (subclasses) instances) in this `Field`
        """
        return self.process_dict.values()

    # TBD: not used currently
    def process_choice_node(self, name, raiseError=True):
        """
        Find a `ProcessChoice` instance by name.

        :param name: (str) the name of the choice element
        :param raiseError: (bool) whether to raise an error if `name` is not found
        :return: (opgee.ProcessChoice) the instance found, or None
        """
        choice_node = self.process_choice_dict.get(name)
        if choice_node is None and raiseError:
            raise OpgeeException(f"Process choice '{name}' not found in field '{self.name}'")

        return choice_node

    def find_stream(self, name, raiseError=True):
        """
        Find the Stream with `name` in this Field. If not found: if
        `raiseError` is True, an error is raised, else None is returned.

        :param name: (str) the name of the Stream to find
        :param raiseError: (bool) whether to raise an error if the Stream is not found.
        :return: (Stream or None) the requested Stream, or None if not found and `raiseError` is False.
        :raises: OpgeeException if `name` is not found and `raiseError` is True
        """
        stream = self.stream_dict.get(name)

        if stream is None and raiseError:
            raise OpgeeException(f"Stream named '{name}' was not found in field '{self.name}'")

        return stream

    def find_process(self, name, raiseError=True):
        """
        Find the Process of class `name` in this Field. If not found: if
        `raiseError` is True, an error is raised, else None is returned.

        :param name: (str) the name of the subclass of Process to find
        :param raiseError: (bool) whether to raise an error if the Process is not found.
        :return: (Process or None) the requested Process, or None if not found and `raiseError` is False.
        :raises: OpgeeException if `name` is not found and `raiseError` is True
        """
        process = self.process_dict.get(name)

        if process is None and raiseError:
            raise OpgeeException(f"Process '{name}' was not found in field '{self.name}'")

        return process

    def find_start_streams(self):
        streams = [s for s in self.streams() if s.has_exogenous_data]
        return streams

    def set_extend(self, value):
        self.extend = getBooleanXML(value)

    def set_modifies(self, modifies):
        self.modifies = modifies

    @classmethod
    def from_xml(cls, elt):
        """
        Instantiate an instance from an XML element

        :param elt: (etree.Element) representing a <Field> element
        :return: (Field) instance populated from XML
        """
        name = elt_name(elt)
        attrib = elt.attrib

        attr_dict = cls.instantiate_attrs(elt)

        aggs = instantiate_subelts(elt, Aggregator)
        procs = instantiate_subelts(elt, Process)
        streams = instantiate_subelts(elt, Stream)

        choices = instantiate_subelts(elt, ProcessChoice)
        # Convert to lowercase to avoid simple lookup errors
        process_choice_dict = {choice.name.lower(): choice for choice in choices}

        group_names = [node.text for node in elt.findall('Group')]

        obj = Field(name, attr_dict=attr_dict, aggs=aggs, procs=procs,
                    streams=streams, group_names=group_names,
                    process_choice_dict=process_choice_dict)

        obj.set_enabled(attrib.get('enabled', '1'))
        obj.set_extend(attrib.get('extend', '0'))
        obj.set_modifies(attrib.get('modifies'))

        return obj

    def collect_processes(self):
        """
        Recursively descend the Field's Aggregators to create a list of all
        processes defined for this field. Includes Field's builtin processes.

        :return: (list of instances of Process subclasses) the processes
           defined for this field
        """

        def _collect(process_list, obj):
            for child in obj.children():
                if isinstance(child, Process):
                    process_list.append(child)
                else:
                    _collect(process_list, child)

        processes = self.builtin_procs.copy()  # copy since we're appending to this list recursively
        _collect(processes, self)
        return processes

    def save_process_data(self, **kwargs):
        """
        Allows a Process to store arbitrary data in the field's `process_data` dictionary
        for access by other processes.

        :param name: (str) the name of the data element (the dictionary key)
        :param value: (any) the value to store in the dictionary
        :return: none
        """
        for name, value in kwargs.items():
            self.process_data[name] = value

    def get_process_data(self, name, raiseError=None):
        """
        Retrieve a stored value from the field's `process_data` dictionary.

        :param name: (str) the name of the data element (the dictionary key)
        :return: (any) the value
        :raises OpgeeException: if the name is not found in `process_data`.
        """
        try:
            return self.process_data[name]
        except KeyError:
            if raiseError:
                raise OpgeeException(f"Process data dictionary does not include {name}")
            else:
                return None

    def resolve_process_choices(self, process_choice_dict=None):
        """
        Disable all processes referenced in a `ProcessChoice`, then enable only the processes
        in the selected `ProcessGroup`. The name of each `ProcessChoice` must also identify an
        field-level attribute, whose value indicates the user's choice of `ProcessGroup`.

        :param process_choice_dict: (dict) optional dictionary for nested process choices. Used
            in recursive calls only.
        :return: None
        """
        attr_dict = self.attr_dict

        if process_choice_dict is None: # might be an empty dict, but that's ok
            process_choice_dict = self.process_choice_dict

        #
        # Turn off all processes identified in groups, then turn on those in the selected groups.
        #
        to_enable = []
        for choice_name, choice in process_choice_dict.items():
            attr = attr_dict.get(choice_name)
            if attr is None:
                raise OpgeeException(
                    f"ProcessChoice '{choice_name}' has no corresponding attribute in field '{self.name}'")

            selected_group_name = attr.value.lower()

            for group_name, group in choice.groups_dict.items():
                procs, streams = group.processes_and_streams(self)

                if group_name == selected_group_name:  # remember the ones to turn back on
                    to_enable.extend(procs)
                    to_enable.extend(streams)

                    # Handle nested process groups in the enabled group
                    self.resolve_process_choices(process_choice_dict=group.process_choice_dict)

                # disable all objects in all groups
                for obj in procs + streams:
                    obj.set_enabled(False)

        # enable the chosen procs and streams
        for obj in to_enable:
            obj.set_enabled(True)

    def sum_process_energy(self, processes_to_exclude=None) -> Energy:

        total = Energy()
        processes_to_exclude = processes_to_exclude or []
        for proc in self.processes():
            if proc.name not in processes_to_exclude:
                total.add_rates_from(proc.energy)

        return total

    def dump(self):
        """
        Print out a representation of the field's processes and streams for debugging.

        :return: none
        """
        visited = {}  # traverse a process only the first time it's encountered

        def debug(msg):
            print(msg)

        def visit(process):
            visited[process] = True
            next = []

            debug(f"\n> {process} outputs:")
            for stream in process.outputs:
                debug(f"  * {stream}")
                dst = stream.dst_proc
                if not dst in visited:
                    next.append(dst)

            for proc in next:
                visit(proc)

        debug(f"\n{self}:")
        visit(self.reservoir)

    def instances_by_class(self, cls):
        """
        Find one or more instances of ``cls`` known to this Field instance.
        If ``cls`` is ``Field``, just return ``self``; if ``cls`` is a subclass
        of ``Process``, find any instances in the field's ``process_dict``.

        :param cls: (Class) the class to find
        :return: (Field or list of instances of the Process subclass) if found,
          else None
        """
        if issubclass(cls, self.__class__):
            return self

        if issubclass(cls, Process):
            results = [proc for proc in self.processes() if isinstance(proc, cls)]
            return results or None

        return None

    #
    # Smart Defaults and Distributions
    #

    @SmartDefault.register('WOR', ['steam_flooding', 'age', 'SOR'])
    def WOR_default(self, steam_flooding, age, SOR):
        from math import exp

        # =IF(Steam_flooding_01=0,
        #     IF(4.021*EXP(0.024*Field_age)-4.021<=100, 4.021*EXP(0.024*Field_age)-4.021, 100),
        #     SOR)
        if steam_flooding:
            return SOR

        tmp = 4.021 * exp(0.024 * age.m) - 4.021
        return tmp if tmp <= 100 else 100

    @SmartDefault.register('SOR', ['steam_flooding'])
    def SOR_default(self, steam_flooding):
        return 3.0 if steam_flooding else 1.0

    # NOTE: If GOR is not known, it can be computed from API_grav, but we avoid
    # registering the dependency as this would create a dependency cycle.
    @SmartDefault.register('GOR', ['API'])
    def GOR_default(self, API):
        # =IF(API_grav<20,1122.4,IF(AND(API_grav>=20,API_grav<=30),1205.4,2429.3))
        if API.m < 20:
            return 1122.4           # TODO: explain these constants
        elif 20 <= API.m <= 30:
            return 1205.4
        else:
            return 2429.3

    # TODO: handle special case of API depending on GOR
    # @SmartDefault.register('API', ['GOR'])
    # def api_default(self, GOR):
    #     # =IF(GOR > 10000, Z73, 32.8) [Z73 = constant 47]
    #     return 47.0 if GOR > 10000 else 32.8

    # TODO: Is the default always 7, or always the value of WOR plus 1?
    @SmartDefault.register('WIR', ['WOR'])
    def WIR_default(self, wor):
        # =J86+1  [J86 is WOR default, 6]
        return wor + 1

    @SmartDefault.register('stabilizer_column', ['GOR', 'gas_lifting', 'oil_sands_mine'])
    def stabilizer_default(self, GOR, gas_lifting, oil_sands_mine):
        # =IF(OR(J55+J56=1,AND(J85<=500,J52=0)),0,1)
        # J52 = gas_lifting (binary)
        # J55 = oil_sands_mine, integrated with upgrader (binary)
        # J56 = oil_sands_mine, non-integrated with upgrader (binary)
        # J85 = GOR
        #
        # Note: in OPGEEv4, there's one attribute 'oil_sands_mine' that can have values
        # 'None', 'Integrated with upgrader', or 'Non-integrated with upgrader'.
        return 0 if (oil_sands_mine != 'None') or (not gas_lifting and GOR <= 500) else 1

    # gas flooding injection ratio
    @SmartDefault.register('GFIR', ['flood_gas_type', 'GOR'])
    def GFIR_default(self, flood_gas_type, GOR):
        # =IF(Flood_gas_type=1, 1.5*J85, IF(Flood_gas_type=2, 1200,  IF(Flood_gas_type=3, 10000,  1.5*J85)))
        # J85 is GOR
        if flood_gas_type == 1:
            return 1.5 * GOR

        elif flood_gas_type == 2:
            return 1200

        elif flood_gas_type == 3:
            return 10000

        else:
            return 1.5 * GOR

    @SmartDefault.register('depth', ['GOR'])
    def depth_default(self, GOR):
        # =IF(GOR > 10000, Z62, 7122), where Z62 has constant 8285 [gas field default depth]
        gas_field_default_depth = 8285.
        return gas_field_default_depth if GOR.m > 1000 else 7122.

    @SmartDefault.register('res_press', ['country', 'depth', 'steam_flooding'])
    def res_press_default(self, country, depth, steam_flooding):
        # =IF(AND('Active Field'!J59="California",'Active Field'!J54=1),100,0.5*(J62*0.43))
        # J59 = country, J62 = depth, J54 = steam_flooding
        return 100.0 if (country == 'California' and steam_flooding) else 0.5 * depth.m * 0.43

    @SmartDefault.register('res_temp', ['depth'])
    def res_temp_default(self, depth):
        # = 70+1.8*J62/100 [J62 = depth]
        return 70 + 1.8 * depth.m/100.0

    @SmartDefault.register('CrudeOilDewatering.heater_treater', ['API'])
    def heater_treater_default(self, API):
        # =IF(J73<18,1,0)  [J73 is API gravity]
        return API.m < 18

    @SmartDefault.register('num_prod_wells', ['oil_sands_mine', 'oil_prod'])
    def num_producing_wells_default(self, oil_sands_mine, oil_prod):
        # =IF(OR(Oil_sands_mine_int_01=1,Oil_sands_mine_nonint_01=1),0,IF(ROUND(J63/87.5,0)<1,1,ROUNDUP(J63/87.5,0)))
        # J63 = oil_prod
        return 0 if oil_sands_mine != 'None' else max(1.0, round(oil_prod.m/87.5, 0))

    @SmartDefault.register('num_water_inj_wells', ['oil_sands_mine', 'oil_prod', 'num_prod_wells'])
    def oil_prod_default(self, oil_sands_mine, oil_prod, num_prod_wells):
        # =IF(OR(Oil_sands_mine_int_01=1,Oil_sands_mine_nonint_01=1),
        #     0,
        #     IF($J$63<=10,                     [J63 = oil_prod]
        #        ROUNDUP(J64*0.143,0),          [J64 = num_prod_wells]
        #        IF(AND($J$63>10,$J$63<=100),
        #           ROUNDUP(J64*0.267,0),
        #           IF(AND($J$63>100, $J$63<=1000),
        #              ROUNDUP(J64*0.512,0),
        #              ROUNDUP(J64*0.829,0)))))
        if oil_sands_mine != 'None':
            return 0

        oil_prod_m = oil_prod.m

        if oil_prod_m <= 10:
            fraction = 0.143
        elif 10 < oil_prod_m <= 100:
            fraction = 0.267
        elif 100 < oil_prod_m <= 1000:
            fraction = 0.512
        else:
            fraction = 0.829

        return roundup(num_prod_wells * fraction, 0)

    @SmartDefault.register('HeavyOilDilution.fraction_diluent', ['oil_sands_mine', 'upgrader_type'])
    def fraction_diluent_default(self, oil_sands_mine, upgrader_type):
        # =IF(AND(J56=1,J111=0),0.3,0) [J56 = 'oil sands mine nonint'; ; J111 = upgrader_type
        return 0.3 if (oil_sands_mine == 'Non-integrated with upgrader' and upgrader_type == 'None') else 0.0

    @SmartDefault.register('fraction_elec_onsite', ['offshore'])
    def fraction_elec_onsite_default(self, offshore):
        return 1.0 if offshore else 0.0

    @SmartDefault.register('fraction_remaining_gas_inj', ['natural_gas_reinjection', 'gas_flooding'])
    def fraction_remaining_gas_inj_default(self, natural_gas_reinjection, gas_flooding):
        # =IF(J53=1,1,IF(J50=1,0.5,0)) [J53 = gas_flooding, J50 = natural_gas_reinjection]
        return 1.0 if gas_flooding else (0.5 if natural_gas_reinjection else 0.0)

    @SmartDefault.register('ecosystem_richness', ['offshore'])
    def ecosystem_richness_default(self, offshore):
        # Excel has 3 separate booleans for low, med, high ecosystem richness, but we have
        # just one attribute here; value is one of ('Low carbon', 'Med carbon', 'High carbon').
        # Low : =IF(J70=1,1,0) [J70 = offshore]
        # Med : =IF(J70=1,0,1)
        # High: =IF(J70=1,0,0) # TODO: high carbon isn't used?
        return 'Low carbon' if offshore else 'Med carbon'

    @SmartDefault.register('field_development_intensity', ['offshore'])
    def field_development_intensity_default(self, offshore):
        # Excel has 3 separate booleans for low, med, high intensity, but we have
        # just one attribute here; value is one of ('Low', 'Med', 'High').
        # Low : =IF(J70=1,1,0) [J70 = offshore]
        # Med : =IF(J70=1,0,1)
        # High: =IF(J70=1,0,0) # TODO: high intensity isn't used?
        return 'Low' if offshore else 'Med'

    @SmartDefault.register('common_gas_process_choice', ['oil_sands_mine'])
    def common_gas_process_choice_default(self, oil_sands_mine):
        # Disable the ancillary group of gas-related processes when there is oil sand mine.
        # Otherwise enable all of those processes.
        return 'None' if oil_sands_mine != 'None' else 'All'


    # TODO: decide how to handle "associated gas defaults", which is just global vs CA-LCFS values currently
