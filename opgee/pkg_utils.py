'''
.. Created as part of pygcam (2015)
   Imported into opgee (2021)

   Common functions and data

.. Copyright (c) 2015-2022 Richard Plevin
   See the https://opensource.org/licenses/MIT for license details.
'''
import io
import pkgutil

from .error import OpgeeException

DFLT_ENCODING = 'utf-8'

def getResource(relpath, decode=DFLT_ENCODING):
    """
    Extract a resource (e.g., file) from the given relative path in
    the opgee package.

    :param relpath: (str) a path relative to the opgee package
    :param decode: (str) the argument to use to decode the data, or
        None to return the data without decoding.
    :return: the file contents
    """
    contents = pkgutil.get_data('opgee', relpath)
    return contents.decode(decode) if decode else contents

def resourceStream(relpath, stream_type='text', decode=DFLT_ENCODING):
    """
    Return a stream on the resource found on the given path relative
    to the opgee package.

    :param relpath: (str) a path relative to the opgee package
    :param stream_type: (str) the type of stream to create, either 'text' or 'bytes'
    :return: (file-like stream) a file-like buffer opened on the desired resource.
    """
    valid_types = ('text', 'bytes')
    if stream_type not in valid_types:
        raise OpgeeException(f"resourceStream type argument {type} is not allowed; it must be one of {valid_types}")

    text = getResource(relpath, decode=decode)
    return io.BytesIO(text) if stream_type == 'bytes' else io.StringIO(text)
