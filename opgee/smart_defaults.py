#
# TODO:
#   - Should defaults and distros be assigned at a class level?
#     - Attributes are defined at this level, so it makes sense.
#     - This means one default/distro per attribute of Model, Analysis, and Field
#       (and less usefully, Aggregator and Stream) and each Process subclass can
#       have its own set of attributes.
#   - Define a procedure for assigning smart defaults
#     - Walk the model structure and check attributes at each level to find any
#       smart defaults / distros.
#       - 3-level dict: registry[dep_type][class_name][attr_name]
#     - Find attributes that have only simple-default="True", or tag values with
#       smart defaults in the attribute definition? This splits the handling of
#       smart defaults between the XML and code, which is undesirable. Better to
#       be able to add a smart default in the code without touching the XML?
#     - Call obj.attr(name) or obj.set_attr(name, value) as needed
#  - For MCS, walk the model or just walk the registry[Distribution] sub-dict?
#  - It's easy to find a distribution given a class and attr, but can we go the
#    other way as readily?
#    - Descend hierarchy, Model -> Analysis -> Field -> Process / Stream and
#      check for class name in registry[Distribution][class_name]. If found,
#      walk the next level of dict (by attr_name) and operate of the model object.
#   Questions
#   - Does it make sense for an attribute to have both a SmartDefault and Distribution?
#
from collections import defaultdict
import networkx as nx
import pandas as pd
from opgee.core import OpgeeObject
from opgee.error import OpgeeException


class Dependency(OpgeeObject):
    """
    Creates a registry containing both SmartDefaults and Distributions, along
    with their dependencies so we can process these in the required order. The
    ``registry`` is a DataFrame with columns 'dep_type', 'class_name', 'attr_name'
    and 'dep_obj', where ``dep_type`` is the name of a subclass of ``Dependency``
    with which the ``register`` decorator was used; ``class_name`` is the name of
    the OPGEE class containing attributes (i.e., a subclass of ``AttributeMixin``);
    and ``attr_name`` is the name of an attribute in that class's ``attr_dict``.
    """
    registry = pd.DataFrame(columns=['dep_type', 'class_name', 'attr_name', 'dep_obj'])

    def __init__(self, func_class, func_name, func, attr_name, dependencies):
        self.func_class = func_class    # the class containing func
        self.func_name  = func_name
        self.func = func
        self.attr_name = attr_name
        self.dependencies = dependencies
        self.dep_type = dep_type = type(self).__name__      # 'Distribution' or 'SmartDefault'

        self.run_index = None # set by run_order() to help with sorting model objects

        print(f'Saving {dep_type} for attribute {attr_name} of class {func_class}')

        Dependency.registry = Dependency.registry.append(dict(dep_type=dep_type, class_name=func_class,
                                                              attr_name=attr_name, dep_obj=self),
                                                         ignore_index=True)

    @classmethod
    def register(cls, attr_name, dependencies):
        """
        The abstract decorator function. Callers should call it via subclasses
        ``SmartDefault`` or ``Distribution``, e.g.,

        @SmartDefault.register("attr_name", ["dep1", "dep2", ...])
        def my_func() ...

        :param attr_name: (str) The name of an attribute. The class to which the attribute
          pertains will be extracted from the function's metadata via ``func.__qualname__``.
        :param dependencies: (list of str) The names of attributes upon which ``attr_name``
          depends, each specified in the form "class_name.attr_name", if referring to an
          attribute of an enclosing class (e.g., ``Analysis`` or ``Model``) or simply the
          attribute name if referring to the same class inferred for ``attr_name``.
        :return: (function) The decorator function.
        """
        def decorator(user_func):
            # func.__qualname__ is a string of format "func_class.func_name"
            qualname = user_func.__qualname__
            func_class, func_name = qualname.split('.')

            def wrapped_func(*args):
                print(f'Calling {qualname} for attribute {attr_name} with dependencies {dependencies}')
                return user_func(*args)

            cls(func_class, func_name, wrapped_func, attr_name, dependencies)
            return wrapped_func

        return decorator

    @classmethod
    def run_order(cls):
        g = Dependency.graph()
        ordered = nx.topological_sort(g)

        # TBD: obj is a str, not Dependency...
        # for i, obj in enumerate(ordered):
        #     obj.run_index = i

        return ordered

    @classmethod
    def graph(cls):
        """
        Create a directed graph of the dependencies among attributes

        :return: (networkx.DiGraph) the graph
        """
        g = nx.DiGraph()
        for obj in cls.instances:
            g.add_edges_from([(dep, obj.attr_name) for dep in obj.dependencies])

        return g

    @classmethod
    def find_class(cls, dep_type, cls_name):
        pass

    @classmethod
    def find(cls, dep_type, class_name, attr_name):
        rows = cls.registry.query("dep_type == @dep_type and class_name == @class_name and attr_name == @attr_name")
        if len(rows) == 0:
            raise OpgeeException(f"Attribute {attr_name} has no {dep_type} registered for class {class_name}.")

        dep_obj = rows[0].attr_name
        return dep_obj

    # TBD: resolve the issue of finding Analysis from Field
    def find_attr_obj(self, obj, attr_name):
        """
        Find an attribute in the current element or in the object hierarchy above
        this node, as indicated by a name of the form "class_name.attr_name".

        :param obj: (opgee.AttributeMixin) an object for which an attribute has a
          SmartDefault or Distribution defined.
        :param name: (str) a simple attribute name or a dot-delimited name of the
          form "class_name.attr_name".
        :return: (opgee.AttributeMixin) the object containing the attribute found
        """
        items = attr_name.split('.')
        count = len(items)

        if count == 0 or count > 2:
            raise OpgeeException(f"Attribute name '{attr_name}' must have one or two parts, delimited with '.'. Got {items}")

        if count == 2:
            class_name, attr_name = items
            parent = obj.find_parent(class_name)
            if parent is None:
                raise OpgeeException(f"Parent of class '{class_name}' was not found above {obj}.")

            obj = parent

        if not attr_name in obj.attr_dict:
            raise OpgeeException(f"{obj} does not have an attribute named '{attr_name}'")

        return obj


class SmartDefault(Dependency):
    def set_value(self, obj):
        """
        Set the value of the attribute referenced by this ``SmartDefault`` instance,
        found in ``obj``, which must be a subclass of ``AttributeMixin``.

        :param obj: (opgee.AttributeMixin) An object with an attribute dictionary.
        :return: (float) the value stored in the referenced attribute.
        """
        # TBD: handles deps on higher-level (e.g., Analysis) attribute
        #      Problem: no unique Analysis for each Field
        #      Consider solutions like setting field.parent = analysis
        #      for all fields when running an analysis. Then we can't
        #      run 2 analyses in separate threads. Not really: can't
        #      anyway because Fields are shared among Analyses.

        # collect values of all attributes we depend on
        values = [obj.attr(attr_name) for attr_name in self.dependencies]

        # invoke the function on the object, passing all the values
        result = self.func(obj, *values)
        obj.set_attr(self.attr_name, result)

        return result

#
# TBD: might fold into one class or distill upward to superclass.
#
class Distribution(Dependency):
    # TBD: something like this
    def set_value(self, obj, attr_dict):
        values = [attr_dict[attr_name] for attr_name in self.dependencies]
        result = self.func(obj, *values)
        attr_dict[self.attr_name] = result
        return result


# def set_smart_default(cls, attr_name):
#     class_name = cls.__name__
#     func = smart_default_registry.get((class_name, attr_name))
#     if func:
#         func(cls, attr_name)
#     else:
#         raise OpgeeException(f"There is no function registered to handle attribute {attr_name} for class {class_name}")
