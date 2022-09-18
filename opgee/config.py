'''
.. Created 2016 as part of pygcam.
   Imported into opgee on 3/29/21

.. Copyright (c) 2015-2022 Richard Plevin
   See the https://opensource.org/licenses/MIT for license details.
'''
import configparser
import os
import platform

from .error import ConfigFileError, OpgeeException
from .pkg_utils import getResource

DEFAULT_SECTION = 'DEFAULT'
USR_CONFIG_FILE = 'opgee.cfg'
USR_DEFAULTS_FILE = '.opgee.defaults'

PlatformName = platform.system()

IsWindows = platform.system() == 'Windows'

_ConfigParser = None # type: configparser.ConfigParser

_ProjectSection = DEFAULT_SECTION

# Deprecated (docker)
# Support for path translations to access docker-mounted host dirs
# _PathMap = None
# _PathPattern = None     # compiled regex matching any mapped paths

_DEFAULT_CONFIG = """# Default configuration file
#
[DEFAULT]
OPGEE.DefaultProject = my_project
OPGEE.LogLevel = INFO
OPGEE.LogConsole = True
OPGEE.ShowStackTrace = True

[my_project]
# OPGEE.ClassPath = %(Home)s/my_directory/my_opgee_procs.py
# OPGEE.StreamComponents = foo, bar , baz
"""

# The unixPath and pathjoin funcs are here rather than in utils.py
# since this functionality is needed here and this avoids import loops.
def unixPath(path, abspath=False):
    """
    Convert a path to use Unix-style slashes, optionally
    removing the final slash, if present.

    :param path: (str) a pathname
    :param rmFinalSlash: (bool) True if a final slash should
           be removed, if present.
    :return: (str) the modified pathname
    """

    # Use str values, not Paths
    path = str(path).replace('\\', '/')

    if abspath:
        path = os.path.abspath(path)

    return path

def pathjoin(*elements, **kwargs):
    path = os.path.join(*elements)

    if kwargs.get('expanduser'):
        path = os.path.expanduser(path)

    if kwargs.get('abspath'):
        path = os.path.abspath(path)

    # if kwargs.get('normpath'):
    #     path = os.path.normpath(path)

    if kwargs.get('realpath'):
        path = os.path.realpath(path)

    return unixPath(path)

# Deprecated (docker)
# def savePathMap(mapString):
#     """
#     Save a list of pathname translations (sorted, descending by length)
#     for use with docker, mapping host directories to container-mounted
#     directories. The function getParam() performs the translations.
#
#     :param mapString: (str) sequence of newline-limited lines, each
#        containing a pair of the form "host-path:container-path".
#
#     :return: nothing
#     """
#     global _PathMap, _PathPattern
#
#     pairStrings = mapString.split()
#     pairs = [s.split(':') for s in pairStrings]
#
#     # strip whitespace
#     pairs = [[s.strip() for s in pair] for pair in pairs]
#
#     # process the longest strings first to avoid overlooking long prefixes
#     pairs = sorted(pairs, key = lambda pair: len(pair[0]), reverse=True)
#     pattern = '|'.join([pair[0] for pair in pairs])
#
#     _PathPattern = re.compile(pattern)
#     _PathMap = dict(pairs)
#
# def _translatePath(value):
#     """
#     Translate a value if it matches _PathPattern.
#
#     :param value: (str) the config value to translate
#     :return: (str) the translated value or original if no key was matched
#     """
#     matches = re.findall(_PathPattern, value)
#     if matches:
#         for m in sorted(matches, key=len, reverse=True):
#             hostPath = m
#             contPath = _PathMap[hostPath]
#             # print("re.sub({}, {}, {})".format(hostPath, contPath, value))
#             value = re.sub(hostPath, contPath, value)
#
#     return value

# may not be needed in opgee
# def parse_version_info(vers=None):
#     import semver
#
#     vers = vers or getParam('OPGEE.VersionNumber')
#
#     # if only major.minor is given (e.g., "4.4"), add .patch of zero (e.g., "4.4.0")
#     if re.match(r'^\d\.\d$', vers):
#         vers += '.0'
#
#     return semver.parse_version_info(vers)

def getSection():
    return _ProjectSection

def setSection(section):
    """
    Set the name of the default config file section to read from.

    :param section: (str) a config file section name.
    :return: none
    """
    global _ProjectSection
    _ProjectSection = section

def configLoaded():
    return bool(_ConfigParser)

def ensure_default_config():
    '''
    Check that config file exists or create default one.
    '''
    configPath = userConfigPath()

    if not os.path.lexists(configPath) or os.stat(configPath).st_size == 0:
        try:
            with open(configPath, 'w') as f:
                f.write(_DEFAULT_CONFIG)

        except Exception as e:
            raise OpgeeException(f'\n***\n*** Failed to write default opgee configuration file {configPath}: {e}.\n***\n')

def getConfig(reload=False, allowMissing=False, createDefault=False, systemConfigOnly=False):
    """
    Return the configuration object. If one has been created already via
    `readConfigFiles`, it is returned; otherwise a new one is created
    and the configuration files are read. Applications generally do not
    need to use this object directly since the single instance is stored
    internally and referenced by the other API functions.

    :param reload: (bool) if True, instantiate a new global ConfigParser.
    :param allowMissing: (bool) if True, a missing config file is not
       treated as an error. This is used only when generating documentation,
       e.g., on readthedocs.org.
    :param createDefault: (bool) Check that the config file exists, and if not,
       write the default config file. Optional so we don't have to check the file
       on every call.
    :param systemConfigOnly: (bool) This is set to True when generating sphinx
       documentation to avoid presenting user's settings in the generated pages.
    :return: a `ConfigParser` instance.
    """
    if createDefault:
        ensure_default_config()

    if reload or systemConfigOnly:
        global _ConfigParser
        _ConfigParser = None

    return _ConfigParser or readConfigFiles(allowMissing=allowMissing,
                                            systemConfigOnly=systemConfigOnly)


def _readConfigResourceFile(filename, package='opgee', raiseError=True):
    try:
        data = getResource(filename, decode='utf-8')
    except IOError:
        if raiseError:
            raise
        else:
            return None

    _ConfigParser.read_string(data, source=filename)
    return data

def getHomeDir():
    env = os.environ

    if PlatformName == 'Windows':
        # HOME exists on all Unix-like systems; for Windows it's HOMEPATH or HOMESHARE.
        # If set, we use OPGEE_HOME to identify the folder with the config file;
        # otherwise, we use HOMESHARE if set, or HOMEPATH, in that order.
        homedir = env.get('OPGEE_HOME') or env.get('HOMESHARE') or env.get('HOMEPATH')
        drive, path = os.path.splitdrive(homedir)
        drive = drive or env.get('HOMEDRIVE') or 'C:'
        home = os.path.realpath(drive + path)
        home = home.replace('\\', '/')            # avoids '\' quoting issues
    else:
        home = env.get('OPGEE_HOME') or os.getenv('HOME')

    return home

def userConfigPath():
    path = pathjoin(getHomeDir(), USR_CONFIG_FILE)
    return path

def readConfigFiles(allowMissing=False, systemConfigOnly=False):
    """
    Read the OPGEE configuration files, starting with ``opgee/etc/system.cfg``,
    followed by ``opgee/etc/{platform}.cfg`` if present. If the environment variable
    ``PYGCAM_SITE_CONFIG`` is defined, its value should be a config file, which is
    read next. Finally, the user's config file, ``~/opgee.cfg``, is read. Each
    successive file overrides values for any variable defined in an earlier file.

    :return: a populated ConfigParser instance
    """
    global _ConfigParser

    # Strict mode prevents duplicate sections, which we do not restrict
    _ConfigParser = configparser.ConfigParser(comment_prefixes=('#'),
                                              strict=False,
                                              empty_lines_in_values=False)

    # don't force keys to lower-case: variable names are case sensitive
    _ConfigParser.optionxform = lambda option: option

    home = getHomeDir()
    _ConfigParser.set(DEFAULT_SECTION, 'Home', home)

    if not systemConfigOnly:
        _ConfigParser.set(DEFAULT_SECTION, 'User', os.getenv('USER', 'unknown'))

        # Create vars from environment variables as '$' + variable name, as in the shell
        for name, value in os.environ.items():
            value = value.replace(r'%', r'%%')
            _ConfigParser.set(DEFAULT_SECTION, '$' + name, value)

    # Initialize config parser with default values
    _readConfigResourceFile('etc/system.cfg')

    if not systemConfigOnly:
        # Read platform-specific defaults, if defined. No error if file is missing.
        _readConfigResourceFile('etc/%s.cfg' % PlatformName, raiseError=False)

        siteConfig = os.getenv('OPGEE_SITE_CONFIG')
        if siteConfig:
            try:
                with open(siteConfig) as f:
                   _ConfigParser.read_file(f)
            except Exception as e:
                print("WARNING: Failed to read site config file: %s" % e)

        # Customizations are stored in ~/opgee.cfg
        usrConfigPath = userConfigPath()

        # os.path.exists doesn't always work on Windows, so just try opening it.
        try:
            with open(usrConfigPath) as f:
               _ConfigParser.read_file(f)

        except IOError:
            if not allowMissing:
                if not os.path.lexists(usrConfigPath):
                    raise ConfigFileError("Missing configuration file %s" % usrConfigPath)
                else:
                    raise ConfigFileError("Can't read configuration file %s" % usrConfigPath)

        # Dynamically set (if not defined) OPGEE.ProjectName in each section, holding the
        # section (i.e., project) name. If user has set this, the value is unchanged.
        projectNameVar = 'OPGEE.ProjectName'
        for section in getSections():
            if not (_ConfigParser.has_option(section, projectNameVar) and   # var must exist
                    _ConfigParser.get(section, projectNameVar)):            # and not be blank
                _ConfigParser.set(section, projectNameVar, section)

        projectName = getParam('OPGEE.DefaultProject', section=DEFAULT_SECTION)
        if projectName:
            setSection(projectName)

    return _ConfigParser

def getSections():
    return _ConfigParser.sections()

def getConfigDict(section=DEFAULT_SECTION, raw=False):
    """
    Return all variables defined in `section` as a dictionary.

    :param section: (str) the name of a section in the config file
    :param raw: (bool) whether to return raw or interpolated values.
    :return: (dict) all variables defined in the section (which includes
       those defined in DEFAULT.)
    """

    # Deprecated (docker)
    # Translation function of identity
    # func = _translatePath if _PathMap else lambda x: x

    func = lambda x: x  # no-op

    d = {key : func(value) for key, value in _ConfigParser.items(section, raw=raw)}
    return d

def setParam(name, value, section=None):
    """
    Set a configuration parameter in memory.

    :param name: (str) parameter name
    :param value: (any, coerced to str) parameter value
    :param section: (str) if given, the name of the section in which to set the value.
       If not given, the value is set in the established project section, or DEFAULT
       if no project section has been set.
    :return: value
    """
    section = section or getSection()
    _ConfigParser.set(section, name, value)
    return value

def getParam(name, section=None, raw=False, raiseError=True):
    """
    Get the value of the configuration parameter `name`. Calls
    :py:func:`getConfig` if needed.

    :param name: (str) the name of a configuration parameters. Note
       that variable names are case-insensitive. Note that environment
       variables are available using the '$' prefix as in a shell.
       To access the value of environment variable FOO, use getParam('$FOO').

    :param section: (str) the name of the section to read from, which
      defaults to the value used in the first call to ``getConfig``,
      ``readConfigFiles``, or any of the ``getParam`` variants.
    :return: (str) the value of the variable, or None if the variable
      doesn't exist and raiseError is False.
    :raises NoOptionError: if the variable is not found in the given
      section and raiseError is True
    """
    section = section or getSection()

    if not section:
        raise OpgeeException('getParam was called without setting "section"')

    if not _ConfigParser:
        getConfig()

    try:
        value = _ConfigParser.get(section, name, raw=raw)

    except configparser.NoSectionError:
        if raiseError:
            raise OpgeeException('getParam: unknown section "%s"' % section)
        else:
            return None

    except configparser.NoOptionError:
        if raiseError:
            raise OpgeeException('getParam: unknown variable "%s"' % name)
        else:
            return None

    # Deprecated (docker)
    # perform pathname translation for use of opgee.cfg in Docker images
    # if _PathMap:
    #     value = _translatePath(value)

    return value

_True  = ['t', 'y', 'true',  'yes', 'on',  '1']
_False = ['f', 'n', 'false', 'no',  'off', '0']

def stringTrue(value, raiseError=True):
    value = str(value).lower()

    if value in _True:
        return True

    if value in _False:
        return False

    if raiseError:
        msg = 'Unrecognized boolean value: "{}". Must one of {}'.format(value, _True + _False)
        raise ConfigFileError(msg)
    else:
        return None

def getParamAsBoolean(name, section=None):
    """
    Get the value of the configuration parameter `name`, coerced
    into a boolean value, where any (case-insensitive) value in the
    set ``{'true','yes','on','1'}`` are converted to ``True``, and
    any value in the set ``{'false','no','off','0'}`` is converted to
    ``False``. Any other value raises an exception.
    Calls :py:func:`getConfig` if needed.

    :param name: (str) the name of a configuration parameters.
    :param section: (str) the name of the section to read from, which
      defaults to the value used in the first call to ``getConfig``,
      ``readConfigFiles``, or any of the ``getParam`` variants.
    :return: (bool) the value of the variable
    :raises: :py:exc:`opgee.error.ConfigFileError`
    """
    value = getParam(name, section=section)
    result = stringTrue(value, raiseError=False)

    if result is None:
        msg = 'The value of variable "{}", {}, could not converted to boolean.'.format(name, value)
        raise ConfigFileError(msg)

    return result

def getParamAsInt(name, section=None):
    """
    Get the value of the configuration parameter `name`, coerced
    to an integer. Calls :py:func:`getConfig` if needed.

    :param name: (str) the name of a configuration parameters.
    :param section: (str) the name of the section to read from, which
      defaults to the value used in the first call to ``getConfig``,
      ``readConfigFiles``, or any of the ``getParam`` variants.
    :return: (int) the value of the variable
    """
    value = getParam(name, section=section)
    return int(value)

def getParamAsFloat(name, section=None):
    """
    Get the value of the configuration parameter `name` as a
    float. Calls :py:func:`getConfig` if needed.

    :param name: (str) the name of a configuration parameters.
    :param section: (str) the name of the section to read from, which
      defaults to the value used in the first call to ``getConfig``,
      ``readConfigFiles``, or any of the ``getParam`` variants.
    :return: (float) the value of the variable
    """
    value = getParam(name, section=section)
    return float(value)

def getParamAsList(name):
    value = getParam(name)
    values = [s.strip() for s in value.split(',')]
    return values
