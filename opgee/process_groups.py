#
# Support for process groups
#
# Author: Richard Plevin and Wennan Long
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
from collections import OrderedDict

from .core import XmlInstantiable, elt_name, instantiate_subelts
from .error import OpgeeException
from .log import getLogger
from .utils import getBooleanXML

_logger = getLogger(__name__)


class ProcessChoice(XmlInstantiable):
    """
    Contains a set of mutually-exclusive `ProcessGroups`.
    """
    def __init__(self, name, groups, extend, default):
        super().__init__(name)

        self.extend = extend
        self.default = default

        # store the groups in a dict for fast lookup, but maintain order for display
        self.groups_dict = OrderedDict()
        for group in groups:
            self.groups_dict[group.name.lower()] = group

    def group_names(self):
        names = list(self.groups_dict.keys())
        return names

    def get_group(self, name, raiseError=True):
        name = name.lower()
        group = self.groups_dict.get(name)
        if group is None and raiseError:
            raise OpgeeException(f"Process choice '{name}' not found in field '{self.name}'")

        return group

    # def _after_init(self):
    #     self.field = self.get_field()

    @classmethod
    def from_xml(cls, elt):
        """
        Instantiate an instance from an XML element

        :param elt: (etree.Element) representing a <Process> element
        :return: (Process) instance populated from XML
        """
        name = elt_name(elt)

        a = elt.attrib
        extend = getBooleanXML(a.get('extend', 'false'))
        default = a.get('default')

        groups  = instantiate_subelts(elt, ProcessGroup)

        obj = ProcessChoice(name, groups, extend, default)
        return obj


class ProcessGroup(XmlInstantiable):
    """
    Contains a set of `ProcessRef` and `StreamRef` instances defining one coherent
    choice of Processes.
    """
    def __init__(self, name, process_refs, stream_refs, choices):
        super().__init__(name)

        self.process_refs = process_refs
        self.stream_refs = stream_refs

        # Nested process choices, if any
        self.process_choice_dict = {choice.name.lower(): choice for choice in choices}

    def process_and_stream_refs(self):
        """
        Return a tuple of lists of referenced Process and Stream names.

        :return: (tuple of lists of Process and Stream names)
        """
        return (self.process_refs, self.stream_refs)

    def processes_and_streams(self, field):
        """
        Return referenced `Process` and `Stream` instances in the given `Field`.

        :return: (tuple of lists of Process and Stream instances)
        """
        procs   = [field.find_process(name) for name in self.process_refs]
        streams = [field.find_stream(name)  for name in self.stream_refs]
        return (procs, streams)

    @classmethod
    def from_xml(cls, elt):
        """
        Instantiate an instance from an XML element

        :param elt: (etree.Element) representing a <Process> element
        :return: (Process) instance populated from XML
        """
        name = elt_name(elt)
        process_refs = [elt_name(node) for node in elt.findall('ProcessRef')]
        stream_refs  = [elt_name(node) for node in elt.findall('StreamRef')]

        choices = instantiate_subelts(elt, ProcessChoice)   # nested choices

        return ProcessGroup(name, process_refs, stream_refs, choices)
