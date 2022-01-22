from copy import deepcopy
import os
from pathlib import Path
from .attributes import AttrDefs
from .config import getParam, unixPath
from .error import OpgeeException, XmlFormatError
from .log import getLogger
from .model import Model
from .pkg_utils import resourceStream
from .process import reload_subclass_dict
from .stream import Stream
from .utils import loadModuleFromPath, splitAndStrip
from .XMLFile import XMLFile
from .xml_utils import merge_elements, save_xml

_logger = getLogger(__name__)


class ModelFile(XMLFile):
    """
    Represents the overall opgee.xml file.
    """

    # Remember paths loaded so we avoid reloading them and re-defining Process subclasses
    _loaded_module_paths = dict()

    _loaded_stream_components = False
    _loaded_user_classes = False

    def __init__(self, pathnames, add_stream_components=True,
                 use_class_path=True, use_default_model=True,
                 instantiate_model=True, save_to_path=None):
        """
        Several steps are performed, some of which are dependent on the function's parameters:

        1. If `add_stream_components` is True, load any extra stream components defined by config file
        variable "OPGEE.StreamComponents".

        2. Reads the input XML filename using either from `filename` (if `stream` is None) or from
        `stream`. In the latter case, the filename is used only as a description of the stream.

        3. If `use_class_path` is True, loads any Python files found in the path list defined by
        "OPGEE.ClassPath". Note that all classes referenced by the XML must be defined internally
        by opgee, or in the user's files indicated by "OPGEE.ClassPath".

        4. Construct the model data structure from the input XML file and store the result in `self.model`.

        :param pathnames: (str, or list or tuple of str) the name(s) of the file(s) to read, if
           `stream` is None, else the description of the file, e.g., "[opgee package]/etc/opgee.xml".
        :param add_stream_components: (bool) whether to load additional `Stream` components using the
           value of config parameter "OPGEE.StreamComponents".
        :param use_class_path: (bool) whether to load custom python classes from the path indicated by
           config file variable "OPGEE.ClassPath".
        :param use_default_model: (bool) whether to load the built-in files "etc/opgee.xml" and
           "/etc/attributes.xml".
        :param instantiate_model: (bool) whether to parse the merged XML to create a ``Model``
            instance.
        :param save_to_path: (str) If provided, the final merged XML will written to this pathname.
        """
        _logger.debug(f"Loading model from: {pathnames}")

        if not isinstance(pathnames, (list, tuple)):
            pathnames = [] if pathnames is None else [pathnames]

        if not (pathnames or use_default_model):
            raise OpgeeException(f"ModelFile: no model XML file specified")

        opgee_xml = 'etc/opgee.xml'
        attributes_xml = 'etc/attributes.xml'

        # Assemble a list of built-in and user XML files to read and merge
        base_stream = resourceStream(opgee_xml, stream_type='bytes', decode=None) if use_default_model else None
        base_path   = pathnames.pop(0) if (pathnames and not use_default_model) else None

        # Use superclass XMLFile to load base file we will merge into
        super().__init__(base_stream or base_path, schemaPath='etc/opgee.xsd')
        self.root = base_root = self.tree.getroot()

        # Read and validate the format of any other input files.
        xml_files = [XMLFile(path, schemaPath='etc/opgee.xsd') for path in pathnames]

        # Push the XMLFile for attributes.xml onto the front of 'xml_files'
        attr_stream = resourceStream(attributes_xml, stream_type='bytes', decode=None)
        xml_files.insert(0, XMLFile(attr_stream, schemaPath='etc/opgee.xsd'))

        # Read all XML files and merge everything below <Model> into base_root
        for xml_file in xml_files:
            root = xml_file.getRoot()
            merge_elements(base_root, root[:])

        # Find Fields with modifies="..." attribute, copy the indicated Field, merge in the
        # elements under the Field with modifies=, and replace elt. This is useful for
        # debugging and storing the expanded "final" XML facilitates publication and replication.
        found = base_root.xpath('//Analysis/Field[@modifies]')
        for elt in found:
            modifies = elt.attrib['modifies']
            new_name = elt.attrib['name']

            if base_root.find(f"Field[@name='{new_name}']") is not None:
                raise XmlFormatError(f"Can't copy field '{modifies}' to '{new_name}': a field named '{new_name}' already exists.")

            to_copy = base_root.find(f"Field[@name='{modifies}']")
            copied = deepcopy(to_copy)          # don't modify the original
            copied.attrib.update(elt.attrib)    # copy elt's attributes into `copied`

            # N.B. Elements don't match unless *all* attribs are identical. Maybe match only on tag and name attribute??
            merge_elements(copied, elt[:])      # merge elt's children into `copied`
            base_root.append(copied)            # add the copy to the Model

        # function argument overrides config file variable
        save_to_path = save_to_path or getParam('OPGEE.XmlSavePathname')

        # Save the merged file if indicated
        if save_to_path:
            save_xml(save_to_path, base_root, backup=True)

        # There must be exactly one <AttrDefs> as child of <Model>
        found = base_root.findall('AttrDefs')
        if found is None:
            raise XmlFormatError(f"Missing <AttrDefs> as child of <Model> in '{pathnames}'")
        elif len(found) > 1:
            raise XmlFormatError("Multiple <AttrDefs> appear as children of <Model> in '{pathnames}'")

        AttrDefs.load_attr_defs(found[0])

        # Process user configuration settings
        if add_stream_components:
            extra_components = getParam('OPGEE.StreamComponents')
            if extra_components:
                names = splitAndStrip(extra_components, ',')
                Stream.extend_components(names)

        def _load_from_path(module_path):
            module_path = unixPath(module_path, abspath=True)
            if module_path in self._loaded_module_paths:
                _logger.warn(f"ModelFile: refusing to reload previously loaded module path {module_path}")
            else:
                loadModuleFromPath(module_path)
                self._loaded_module_paths[module_path] = True

        # Load user classes, if indicated in config file, prior to parsing the XML structure
        if use_class_path:
            class_path = getParam('OPGEE.ClassPath')
            paths = [Path(path) for path in class_path.split(os.path.pathsep) if path]
            for path in paths:
                if path.is_dir():
                    for module_path in path.glob('*.py'):  # load all .py files found in directory
                        _load_from_path(module_path)
                else:
                    print(f"Loading module from '{path}'")
                    _load_from_path(path)

            reload_subclass_dict()

        # the merge subcommand specifies instantiate_model=False, but normally the model is loaded.
        if instantiate_model:
            self.model = model = Model.from_xml(base_root)
            model.validate()

            # Show the list of paths read in the GUI
            pathnames.insert(0, opgee_xml if base_stream else base_path)
            model.set_pathnames(pathnames)

    @classmethod
    def attr_defs(cls):
        return cls._attr_defs
