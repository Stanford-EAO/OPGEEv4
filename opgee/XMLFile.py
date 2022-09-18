'''
.. Created as part of pygcam (2015)
   Imported into opgee (2021)

.. Copyright (c) 2015-2022 Richard Plevin
   See the https://opensource.org/licenses/MIT for license details.
'''
from lxml import etree as ET

from .config import getConfigDict, getParam
from .error import XmlFormatError
from .log import getLogger

_logger = getLogger(__name__)

class XMLFile(object):

    parsed_schemas = {} # cache parsed schemas to avoid re-reading and parsing opgee.xsd

    def __init__(self, filename, load=True, schemaPath=None,
                 removeComments=True, conditionalXML=False, varDict=None):
        """
        Stores information about an XML file; provides wrapper to parse and access
        the file tree, and handle "conditional XML".

        :param filename: (str) The pathname to the XML file
        :param load: (bool) If True, the file is loaded, otherwise, the instance is
           set up, but the file is not read.
        :param schemaPath: (str) If not None, the path relative to the root of the
           package to the .xsd (schema definition) file to use to validate the XML file.
        :param removeComments: (bool) If True, comments are discarded upon reading the file.
        :param conditionalXML: (bool) If True, the XML is processed using Conditional XML
           prior to validation.
        :param varDict: (dict) A dictionary to use in place of the configuration dictionary
           when processing Conditional XML.
        """
        self.filename = filename
        self.tree = None
        self.conditionalXML = conditionalXML
        self.varDict = varDict or getConfigDict(section=getParam('OPGEE.DefaultProject'))
        self.removeComments = removeComments

        self.schemaPath   = schemaPath
        self.schemaStream = None

        if filename and load:
            self.read()

    def getRoot(self):
        'Return the root node of the parse tree'
        return self.tree.getroot()

    def getTree(self):
        'Return XML parse tree.'
        return self.tree

    def getFilename(self):
        'Return the filename for this ``XMLFile``'
        return self.filename

    def read(self):
        """
        Read the XML file, and if validate if ``self.schemaFile`` is not None.
        """
        filename = self.filename

        _logger.debug("Reading '%s'", filename)
        parser = ET.XMLParser(remove_blank_text=True, remove_comments=self.removeComments)

        try:
            tree = self.tree = ET.parse(filename, parser)

        except Exception as e:
            raise XmlFormatError(f"Can't read XML file '{filename}': {e}")

        if self.removeComments:
            for elt in tree.iterfind('//comment'):
                parent = elt.getparent()
                if parent is not None:
                    parent.remove(elt)

        self.validate()

        return tree

    def validate(self, raiseOnError=True):
        """
        Validate a ParameterList against ``self.schemaFile``. Optionally raises an
        error on failure, else return boolean validity status. If no schema file
        is defined, return ``True``.
        """
        import importlib_resources as imp

        if not self.schemaPath:
            return True

        tree = self.tree

        # use the cached version if available
        schema = self.parsed_schemas.get(self.schemaPath)
        if not schema:
            ref = imp.files('opgee') / self.schemaPath

            with imp.as_file(ref) as path:
                xsd = ET.parse(path)
                schema = ET.XMLSchema(xsd)
                self.parsed_schemas[self.schemaPath] = schema

        if raiseOnError:
            try:
                schema.assertValid(tree)
                return True
            except ET.DocumentInvalid as e:
                raise XmlFormatError(f"Validation of '{self.filename}'\n  using schema '{self.schemaPath}' failed:\n  {e}")
        else:
            valid = schema.validate(tree)
            return valid
