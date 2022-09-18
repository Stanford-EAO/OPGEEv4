#
# Graphing support
#
# Author: Richard Plevin
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
import pydot

from .core import OpgeeObject
from .log import getLogger
from .process import Process

_logger = getLogger(__name__)

def add_subclasses(graph, cls, show_process_subclasses=False):
    name = cls.__name__
    graph.add_node(pydot.Node(name, shape='box'))

    if (not show_process_subclasses) and (cls == Process):
        return

    subs = cls.__subclasses__()
    for sub in subs:
        graph.add_edge(pydot.Edge(name, sub.__name__, color='black'))
        add_subclasses(graph, sub, show_process_subclasses=show_process_subclasses)

def display_in_notebook(graph):
    from .utils import ipython_info

    # if in a notebook, also display it directly
    if ipython_info() == 'notebook':
        from IPython.display import Image, display
        png = graph.create_png()
        display(Image(png))

def write_class_diagram(pathname, show_process_subclasses=False):
    """
    Create and save a graph of the class hierarchy starting from OpgeeObject.
    If `show_process_subclasses` is True, all classes are shown, notably including
    the dozens of subclasses of Process; otherwise, subclasses of Process are excluded.

    :param pathname: (str) the file to create
    :param limit: (str) either 'all' or 'core')
    :return: None
    """
    graph = pydot.Dot('classes', graph_type='graph', bgcolor='white')
    add_subclasses(graph, OpgeeObject, show_process_subclasses=show_process_subclasses)

    _logger.info(f"Writing {pathname}")
    graph.write_png(pathname)
    display_in_notebook(graph)

def write_model_diagram(model, pathname, levels=0):
    """
    Create a network graph from an OPGEE Model.

    :param model: (Model) a populated Model instance
    :param pathname: (str) the pathname of the PNG file to create
    :param levels: (int) the number of levels of the hierarchy to display.
        A value of zero implies no limit.
    :return: None
    """
    def name_of(obj):
        class_name = obj.__class__.__name__
        obj_name = obj.name
        return f"{class_name}({obj_name})" if obj_name else class_name

    def add_tree(graph, obj, level):
        name = name_of(obj)
        _logger.debug(f"Adding node '{name}'")
        graph.add_node(pydot.Node(name, shape='box'))

        if levels == 0 or level < levels:
            level += 1
            for child in obj.children():
                add_tree(graph, child, level)
                _logger.debug(f"Adding edge('{name}', '{name_of(child)}')")
                graph.add_edge(pydot.Edge(name, name_of(child), color='black'))

    graph = pydot.Dot('model', graph_type='graph', bgcolor='white')
    for obj in model.fields():
        add_tree(graph, obj, 1)

    for obj in model.fields():
        add_tree(graph, obj, 1)

    _logger.info(f"Writing {pathname}")
    graph.write_png(pathname)
    display_in_notebook(graph)

def write_process_diagram(field, pathname):
    graph = pydot.Dot('model', graph_type='graph', bgcolor='white')

    for name, proc in field.process_dict.items():
        graph.add_node(pydot.Node(name, shape='box'))

    for name, stream in field.stream_dict.items():
        graph.add_edge(pydot.Edge(stream.src_name, stream.dst_name, color='black'))

    _logger.info(f"Writing {pathname}")
    graph.write_png(pathname)
    display_in_notebook(graph)
