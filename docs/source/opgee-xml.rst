XML File Format
====================

The `opgee` package includes two built-in XML files:

* `opgee/etc/opgee.xml` describes the default model, and

* `opgee/etc/attributes.xml` describes attributes of various model components.

Users can provide their own XML files which can be merged with or used in place of,
the built-in definitions. The elements of the two files are described below,
followed by the contents of the built-in files.

XML file merging
-----------------
The user can specify multiple XML filenames to the `opg run` sub-command. The purpose of this
feature is to allow users to use the built-in model specification as much as possible, by
specifying only modifications changes to that model. The built-in files etc/opgee.xml and
etc/attributes.xml are first loaded unless the user specifies `--no-default-model` on the command-line
to the `opg run` sub-command. Files are merged in the order they are given on the command-line.

How merging works
^^^^^^^^^^^^^^^^^^^^^
The first loaded XML is considered the "base" file into which subsequent files are merged.
Each subsequent file contain the complete XML structure, from the `<Model>` element down, but
it needs to specify only

    * new elements not present in the base or previously merged files
    * modifications to existing elements, or
    * elements to delete

For an elements to "match" a previously defined one, it must be in the position in the XML
hierarchy where each element in the hierarchy of the new and old models have the same tag
and attributes (attribute order is irrelevant).

An element is inserted into the XML in the position where a non-matching element first appears
in the structure. **Give example**

If a match is found and the attribute ``delete=true`` is specified in the new XML, that element
and everything below it in original XML is deleted, and any XML below this element is inserted
in its place. **Give example**

If a match is found and the attribute ``delete=true`` is *not* specified in the new XML, the
matching process proceeds recursively to the next lower level of the XML structure. If a final
XML element (i.e., one with no children) matches, its text is copied in place of any that appeared
in the currently merged XML. **Give example.**

opgee.xml
------------

The elements that comprise the ``opgee.xml`` file are described below.

<Model>
^^^^^^^^^^

The top-most element, ``<Model>``, encloses one or more ``<Analysis>``,
``<Field>``, and ``<A>`` elements. The ``<Model>`` element takes no attributes.

..
  [Saved for later]
  The ``delete`` attribute is used only by user-defined files. If the value
  of the attribute is "1", "yes", or "true" (case insensitive), and a corresponding
  value exists in the built-in XML structure, the built-in element and all elements
  below it in the hierarchy are deleted before the new element is added.

<A>
^^^^^^^^^^^^^^^

The ``<A>`` element is used to set values for attributes in a ``<Model>``, ``<Analysis>``,
``<Field>`` or ``<Process>`` element.
The XML schema allows model elements to have zero or more attributes. The XML schema ensures that the
``<A>`` elements are syntactically correct. The semantics of these elements is defined by a corresponding
``<AttrDef>`` element (see attributes.xml) in the named class. For example,

.. code-block:: xml

    <Process class="SurveyShip">
        <A name="weight">124</A>
        <A name="distance">2342</A>
    </Process >

provides values for two attributes, `weight` and `distance`, for the `SurveyShip` class. These have a
corresponding (**required**) ``<AttrDef>`` definition in attributes.xml that provides the units, description, type, and
default value:

.. code-block:: xml

    <ClassAttrs name="SurveyShip">
        <AttrDef name="distance" type="float" desc="Distance of travel for survey" unit="mi">10000</Attr>
        <AttrDef name="weight" type="float" desc="Weight of ocean survey vehicle" unit="tons">100</Attr>
    </ClassAttrs>


The ``<A>`` element contains no further elements, but it contains an optional value for the attribute,
which if absent is assigned the default for this attribute. The `name` attribute must refer to
the name of an ``<AttrDef>`` defined in the built-in `attributes.xml` or a file loaded by
the user.

.. list-table:: <A> Attributes
   :widths: 10 10 10 10
   :header-rows: 1

   * - Attribute
     - Required
     - Default
     - Values
   * - name
     - yes
     - (none)
     - text

<Analysis>
^^^^^^^^^^^^^
This element contains one or more ``<Field>`` or ``<Group>`` elements and accepts one
required attribute, `name`. The ``<Field>`` elements identify fields to include in the
analysis by field name, whereas ``<Group>`` elements allow matching of group names
indicated in ``<Field>`` definitions, by direct string match or by regular expression match.

.. list-table:: <Analysis> Attributes
   :widths: 10 10 10 10
   :header-rows: 1

   * - Attribute
     - Required
     - Default
     - Values
   * - name
     - yes
     - (none)
     - text

<Group>
^^^^^^^^^
The ``<Group>`` element provides a system of keyword matching by which ``<Field>``
elements can declare themselves members of a group, and ``<Analysis>`` elements
can reference members of the group.

.. list-table:: <Group> Attributes
   :widths: 10 10 10 10
   :header-rows: 1

   * - Attribute
     - Required
     - Default
     - Values
   * - regex
     - no
     - "false"
     - boolean

The ``<Group>`` element allows one attribute, `regex` and contains no
subelements. It must contain a string that is either a regular expression
(if `regex` has a "true" value, i.e., "true", "yes", "1") or the name of
a field group (if `regex` has a "false" value, i.e., "false", "no", "0",
or is absent.)

The identification of the ``<Field>`` elements to include in the ``<Analysis>``
matches ``<Group>`` elements declared within ``<Field>`` elements. The match
uses direct string matching (if `regex` is false) or regular expression matching
(if `regex` is true).

<Field>
^^^^^^^^^^
This element describes an oil or gas field and its processes.
``<Field>`` can contain more or more ``<A>``, ``<Aggregator>``, ``<Stream>``,
``<Process>``, or ``<Group>`` elements.

.. list-table:: <Field> Attributes
   :widths: 10 10 10 10
   :header-rows: 1

   * - Attribute
     - Required
     - Default
     - Values
   * - name
     - yes
     - (none)
     - text
   * - enabled
     - no
     - "1"
     - boolean
   * - extend
     - no
     - "0"
     - boolean

<Aggregator>
^^^^^^^^^^^^^^^
This element contains one or more ``<Aggregator>``, ``<Process>``, or ``<A>`` elements.

.. list-table:: <Aggregator> Attributes
   :widths: 10 10 10 10
   :header-rows: 1

   * - Attribute
     - Required
     - Default
     - Values
   * - name
     - yes
     - (none)
     - text
   * - enabled
     - no
     - "1"
     - boolean

<Process>
^^^^^^^^^^^^^^^
The ``<Process>`` element defines the characteristics of a physical process.
It must include a `class` attribute which identifies the Python class that
implements the process. The identified class must be a subclass of `Process`.

``<Process>>`` elements may contain one or more ``<A>``, ``<Produces>``, or
``<Consusmes>`` elements.

.. list-table:: <Process> Attributes
   :widths: 10 10 10 10
   :header-rows: 1

   * - Attribute
     - Required
     - Default
     - Values
   * - class
     - yes
     - (none)
     - text
   * - name
     - no
     - (class name)
     - text
   * - desc
     - no
     - (none)
     - str
   * - enabled
     - no
     - "1"
     - boolean
   * - extend
     - no
     - "0"
     - boolean

<Stream>
^^^^^^^^^^^^^^^
This element contains one or more ``<Component>`` or ``<A>`` elements.

.. list-table:: <Stream> Attributes
   :widths: 10 10 10 10
   :header-rows: 1

   * - Attribute
     - Required
     - Default
     - Values
   * - name
     - yes
     - (none)
     - text
   * - number
     - no
     - (none)
     - int
   * - src
     - yes
     - (none)
     - str
   * - dst
     - yes
     - (none)
     - str
   * - impute
     - no
     - 1
     - bool

The `src` and `dst` attributes must be set to the names of Process subclasses that are the
source and destination, respectively, for the `Stream`. If no `name` is provided, the name
becomes "{src} => {dst}", with the names of the source and destination processes substituted
for `{src}` and `{dst}`. The `impute` attribute defaults to "1" (true); if set to "0" (or
"false" or "no") the `Stream` will not be traversed during the `impute()` processing phase,
which works backwards (upstream) from the `Streams` with exogenously-defined flow rates.

<Component>
^^^^^^^^^^^^^^^^
Component encloses a numerical value defining an exogenous component flow rate,
expressed in mmbtu/day for all components other than electricity, expressed in kWh/day.
(See :obj:`opgee.stream.Stream` for a list of component names.)

.. list-table:: <Component> Attributes
   :widths: 10 10 10 10
   :header-rows: 1

   * - Attribute
     - Required
     - Default
     - Values
   * - name
     - yes
     - (none)
     - text
   * - phase
     - yes
     - "solid", "liquid" or "gas"
     - str

<Produces>
^^^^^^^^^^^^^^^^
Contains a string indicating the generic name for a substance produced by the ``<Process>``.
This is used in bypassing Processes.

<Consumes>
^^^^^^^^^^^^^^^^
Contains a string indicating the generic name for a substance consumed by the ``<Process>``.
This is used in bypassing Processes.


attributes.xml
----------------

<AttrDefs>
^^^^^^^^^^^^^

.. saved for reference link format only
.. This element identifies a :doc:`rewrite set <rewrites-xml>` by name.
.. The rewrite set must be defined in a file identified as an argument
.. to the :py:func:`pygcam.query.runBatchQuery`, on the command-line to
.. the :ref:`query sub-command <query>`, or by setting a value for
.. the config variable ``GCAM.RewriteSetsFile``.

This is the top-level element in the `attributes.xml` file. It accepts
no attributes and contains only ``<ClassAttrs>`` elements.

<ClassAttrs>
^^^^^^^^^^^^^^^^^
This element describes attributes associated with an OPGEE class, whose
name is provide by the `name` attribute. ``<ClassAttrs>`` elements contain
any number of ``<Options>`` and ``<AttrDef>`` elements.

.. list-table:: <ClassAttrs> Attributes
   :widths: 10 10 10 10
   :header-rows: 1

   * - Attribute
     - Required
     - Default
     - Values
   * - name
     - yes
     - (none)
     - text

<Options>
^^^^^^^^^^^^

This element defines a named set of legal values. Both the `name` and
`default` attributes are required. The ``<Options>`` element contains
one or more (more usefully, two or more) ``<Option>`` elements.

.. list-table:: <Options> Attributes
   :widths: 10 10 10 10
   :header-rows: 1

   * - Attribute
     - Required
     - Default
     - Values
   * - name
     - yes
     - (none)
     - text
   * - default
     - yes
     - (none)
     - text

<Option>
^^^^^^^^^^^^

Describes a single option with an ``<Options>`` element. An optional
`desc` (description) attribute can provide a short explanation of the
option. The ``<Option>`` element contains the value for this alternative,
e.g.,

.. code-block:: xml

    <Options name="ecosystem_C_richness" default="Moderate">
      <Option desc="Low carbon richness (semi-arid grasslands)">Low</Option>
      <Option desc="Moderate carbon richness (mixed)">Moderate</Option>
      <Option desc="High carbon richness (forested)">High</Option>
    </Options>

.. list-table:: <Option> Attributes
   :widths: 10 10 10 10
   :header-rows: 1

   * - Attribute
     - Required
     - Default
     - Values
   * - desc
     - no
     - (none)
     - text

<AttrDef>
^^^^^^^^^^^
This element defines a single attribute, including its name, description,
Python type, and unit. This element should provide a default value or
refer to an ``<Options>`` element describing valid values (and a default)
for this attribute.

..
  ``<AttrDef>`` also can include ``<Requires>`` elements indicating other
  attributes upon whose value the "smart default" for this attribute depends.

The ``<AttrDef>`` element supports several types of optional, declarative constraints
in the form of attributes:

* **synchronized** : the value of the ``synchronized`` attribute is the name of
  a "synchronization group"', which can be any string. All the attributes declared to be
  in this group name must have the same value.

* **exclusive** : the value of the ``exclusive`` attribute is the name of a "exclusive group"',
  which can be any string. All the attributes declared to be in this group must be
  binary attributes and only one of them may have a value of 1 (true).

* **GT, GE, LT, LE** : these are numerical constraints requiring that the value of the
  attribute be greater than (GT), greater than or equal (GE), less than (LT), or
  less than or equal (LE) to the value of the attribute. The following are examples
  of numerical constraints in the built-in file "etc/attributes.xml":

  .. code-block:: XML

      <AttrDef name="age" unit="yr" desc="Field age" type="float" GT="0" LT="150">38</AttrDef>
      <AttrDef name="depth" unit="ft" desc="Field depth" type="float" GT="0" LT="25000">7240.0</AttrDef>
      <AttrDef name="oil_prod" unit="bbl_oil/d" desc="Oil production volume" type="float" GT="0">2098.0</AttrDef>
      <AttrDef name="num_prod_wells" desc="Number of producing wells" type="int" GT="0">24</AttrDef>
      <AttrDef name="num_water_inj_wells" desc="Number of water injecting wells" type="int" GE="0">20</AttrDef>
      <AttrDef name="well_diam" unit="in" desc="Well diameter" type="float" GT="0">2.78</AttrDef>


.. list-table:: <AttrDef> Attributes
   :widths: 10 10 10 10
   :header-rows: 1

   * - Attribute
     - Required
     - Default
     - Values
   * - name
     - yes
     - (none)
     - text
   * - desc
     - no
     - (none)
     - text
   * - exclusive
     - no
     - (none)
     - text
   * - synchronized
     - no
     - (none)
     - text
   * - type
     - no
     - str
     - text
   * - unit
     - no
     - (none)
     - text
   * - options
     - no
     - (none)
     - text
   * - GE
     - no
     - (none)
     - number
   * - GT
     - no
     - (none)
     - number
   * - LE
     - no
     - (none)
     - number
   * - LT
     - no
     - (none)
     - number


..
   * - delete
     - no
     - "0"
     - boolean

..
  The ``delete`` attribute is used only by user-defined files. If the value
  of the attribute is "1", "yes", or "true" (case insensitive), and a corresponding
  value exists in the built-in XML structure, the built-in element and all elements
  below it in the hierarchy are deleted before the new element is added.


