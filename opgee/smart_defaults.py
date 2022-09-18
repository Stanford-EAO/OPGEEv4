#
# Smart Defaults
#
# Author: Richard Plevin
#
# Copyright (c) 2021-2022 The Board of Trustees of the Leland Stanford Junior University.
# See LICENSE.txt for license details.
#
import networkx as nx

from .core import OpgeeObject, split_attr_name
from .error import OpgeeException
from .log import getLogger

_logger = getLogger(__name__)

NO_DEP = '_'    # dummy dependency so these also show up in graph

class ProcessNotFound(OpgeeException):
    """
    Raised when an attribute of a named `Process` is unavailable for
    Smart Default processing because the `Process` doesn't exist in
    the `Field` under evaluation.
    """
    pass

class SmartDefault(OpgeeObject):
    """
    Create a ``SmartDefault`` instance. Do not use this method directly: use
    the :obj:`opgee.smart_defaults.SmartDefault.register` decorator instead. The
    decorator can be used both on methods of OPGEE classes and on ordinary functions.

    Attribute names can be of the form ``class_name.attr_name`` or ``attr_name``.
    If the ``class_name`` is "Field" or "Analysis", the current ``Field`` or ``Analysis``
    instance, respectively, is assumed to hold ``attr_name``. Class names other than
    "Field" or "Analysis"  are interpreted as OPGEE ``Process`` names in the current
    ``Field``.

    If a ``class_name`` is not specified, the default class name is "Field" for
    ordinary functions. For methods, the default class name is that of class defining
    the method.

    If a ``SmartDefault`` is defined for a ``Process`` that is not included in the
    current ``Field``, a warning is issued and the smart default is ignored.

    :param attr_name: (str) the attribute name
    :param wrapper: (callable) the wrapper produced by the decorator
    :param user_func: (callable) the wrapped function
    :param dependencies: (list of str) names of attributes on which ``attr_name``
      depends.
    """
    registry = {}   # Dictionary of ``SmartDefault`` instances keyed by attribute name.

    _run_order = None   # cached result of run_order() method.

    def __init__(self, attr_name, wrapper, user_func, dependencies):
        self.attr_name = attr_name
        self.wrapper = wrapper
        self.user_func = user_func
        self.dependencies = dependencies

        # func.__qualname__ is a string of format "func_class.func_name"
        # for methods and simply the func_name for normal functions
        qualname = user_func.__qualname__
        items = qualname.split('.')
        self.func_class = items[0] if len(items) == 2 else None
        self.func_name = qualname
        self.func_module = user_func.__module__

        self.registry[attr_name] = self
        _logger.debug(f'Saving dependency for attribute {attr_name} of class {self.func_class}')

    # TBD: consider using @functools.wraps:
    #  def my_decorator(f):
    #     @wraps(f)
    #     def wrapper(*args, **kwds):
    #         print('Calling decorated function')
    #         return f(*args, **kwds)
    #     return wrapper

    @classmethod
    def register(cls, attr_name, dependencies):
        """
        The ``@register`` decorator function. Users can wrap methods or regular functions.

        :param attr_name: (str) The name of an attribute, with or without a class or Process name
          specifier.
        :param dependencies: (list of str) The names of attributes on which ``attr_name`` depends.
           These follow the same rules for class or Process specifier defined above.
        :return: (function) The decorator function.
        """
        def decorator(user_func):
            def wrapper(*args):
                _logger.debug(f'Calling {user_func.__qualname__} for attribute {attr_name} with dependencies {dependencies}')
                return user_func(*args)

            cls(attr_name, wrapper, user_func, dependencies)
            return wrapper

        return decorator

    @classmethod
    def run_order(cls):
        """
        Create a directed graph of the dependencies among attributes and return the
        list of dependencies in topologically-sorted order. The result is cached
        since for any set of code, the smart default dependency network is fixed.

        :return: (list of SmartDefault instances) in dependency order
        """
        if cls._run_order is None:
            g = nx.DiGraph()

            for attr_name, obj in cls.registry.items():
                g.add_edges_from([(dep, attr_name) for dep in obj.dependencies])

            cycles = list(nx.simple_cycles(g))
            if cycles:
                raise OpgeeException(f"Smart default dependencies contain cycles: {cycles}")

            cls._run_order = nx.topological_sort(g)

        return cls._run_order

    @classmethod
    def apply_defaults(cls, analysis, field):
        """
        Apply all SmartDefaults for the given ``analysis`` and ``field`` objects,
        in dependency order.

        :param analysis: (opgee.Analysis) The analysis being run.
        :param field: (opgee.Field) The field being run.
        :return: none
        """
        for attr_name in cls.run_order():
            dep: SmartDefault = cls.registry.get(attr_name)
            if dep is None:
                # not a dependency; it's just an attribute that is depended upon
                continue

            try:
                obj, attr_obj = dep.find_attr(attr_name, analysis, field)
            except ProcessNotFound as e:
                _logger.warn(f"{e} (ignoring)")
                continue    # skip this smart default

            # Don't set smart defaults on explicitly set values
            if attr_obj.explicit:
                _logger.debug(f"Ignoring smart default for '{attr_name}', which has an explicit value")
                continue

            # collect values of all attributes we depend on
            try:
                tups = [dep.find_attr(name, analysis, field) for name in dep.dependencies]
            except ProcessNotFound as e:
                _logger.warn(f"{e} (ignoring)")
                continue    # skip this smart default

            values = [attr_obj.value for _, attr_obj in tups]

            # invoke the function on the object, passing all the values; type of call
            # depends on whether it's a method or not (i.e., if func_class is not None)
            try:
                result = dep.wrapper(obj, *values) if dep.func_class else dep.wrapper(*values)
            except Exception as e:
                raise OpgeeException(f"Attempt to call SmartDefault function for attribute '{attr_name}' failed: {e}")

            try:
                attr_obj.set_value(result)
            except Exception as e:
                raise OpgeeException(f"Attempt to set SmartDefault value for attribute '{attr_name}' failed: {e}")


    def find_attr(self, attr_name, analysis, field):
        """
        Find an attribute in the Analysis, Field, or in a named Process.

        :param attr_name: (str) a simple attribute name or a dot-delimited name
          of the form "class_name.attr_name".
        :param analysis: (opgee.Analysis) the Analysis being run.
        :param field: (opgee.Field) the Field being run.
        :param raise_error: (bool) whether to raise an error
        :return: (tuple of (opgee.AttributeMixin, opgee.Attribute)) the object
          containing the Attribute object, and the Attribute object itself. If
          a specified process is not found and raise_error is False, the tuple
          ``(None, None)`` is returned.
        :raises OpgeeException: if the attribute is not found
        :raises ProcessNotFound: if the process specified as containing an attribute
          is not found.
        """
        class_name, attr_name = split_attr_name(attr_name)

        if class_name is None:
            class_name = self.func_class or 'Field'

        if class_name == 'Field':
            obj = field

        elif class_name == 'Analysis':
            obj = analysis

        else:
            obj = field.find_process(class_name, raiseError=False)
            if obj is None:
                    raise ProcessNotFound(f"Process not found for '{class_name}.{attr_name}' in {field}")

        attr_obj = obj.attr_dict.get(attr_name)
        if attr_obj is None:
            raise OpgeeException(f"Attribute '{attr_name}' was not found in '{obj}'")

        return obj, attr_obj
