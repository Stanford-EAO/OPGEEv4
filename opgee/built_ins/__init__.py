from .compare_plugin import CompareCommand
from .config_plugin import ConfigCommand
from .graph_plugin import GraphCommand
from .gui_plugin import GUICommand
from .run_plugin import RunCommand
from .csv2xml_plugin import Csv2XmlCommand
from .merge_plugin import MergeCommand
from .gensim_plugin import GensimCommand
from .runsim_plugin import RunsimCommand
#from .genwor_plugin import GenworCommand

BuiltinSubcommands = [
    CompareCommand, ConfigCommand, GraphCommand, GensimCommand, # GenworCommand,
    GUICommand, MergeCommand, RunCommand, RunsimCommand, Csv2XmlCommand
]
