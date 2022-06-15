What is OPGEE?
====================

The ``opgee`` Python package comprises a set of data files, Python modules, and a main driver script that
implement the `Oil Production Greenhouse gas Emissions Estimator <https://eao.stanford.edu/research-areas/opgee>`_ (OPGEE).
This site documents OPGEEv4. Note that OPGEEv3 and earlier versions were implemented in Excel.

OPGEEv4 is [NOT QUITE YET] installable as a Python package from the “pip” package server. The Python
package includes these components:

    * Classes implementing the required LCA components for the default set of fields,
      processes, technologies, and streams. User-defined classes can augment those provided
      in the package.

    * Configuration default files customized for the three supported computing platforms,
      Windows 10 and macOS.

    * The default LCA model, expressed in the opgee.xml file. This file describes a runnable
      model equivalent to the contents of the OPGEEv3 Excel workbook. It also provides the
      basis for customizations by the user: any and all components defined in this file can
      be modified or deleted, and new components can be defined in a user’s model description
      file to create a custom model.

    * Source files for the documentation system, from which this online documentation is generated.
      Users can optionally build the documentation on their own systems.

    * Tutorials and example files demonstrating customization of the model.


Users can control several aspects of ``opgee`` through a :doc:`configuration file <config>`
found in ``${HOME}/opgee.cfg``. When :doc:`opg` is run the first time, a simple, default
configuration file is created.

:doc:`opg` implements several "subcommands" that provide access to various
features such as running models, graphing aspects of the LCA model and class structure.
The script implements a :doc:`plug-in <opgee.subcommand>`
architecture allowing users to customize :doc:`opg <opg>` and avoid a proliferation
of scripts. The available subcommands for general use include:

   * ``config`` displays the values of configuration parameters and edits the
     user's configuration file.

   * ``run`` reads an XML input file and runs one or more steps of an analysis,
     and these steps typically invoke other sub-commands as required.


..   * ``gui`` runs a local web server that provides a browser-based graphical
..     user interface (GUI) at the address http://127.0.0.1:8050.


Design Goals
--------------------


