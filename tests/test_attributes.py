import pytest
from lxml import etree as ET
from pint import Quantity
from opgee import ureg
from opgee.attributes import ClassAttrs, AttributeMixin
from opgee.core import instantiate_subelts
from opgee.error import OpgeeException
from opgee.model import Model

@pytest.fixture
def attr_classes():
    xml = ET.XML("""
<AttrDefs>
  <ClassAttrs name="Model">
    <Options name="GWP_time_horizon" default="100">
      <Option>20</Option>
      <Option>100</Option>
    </Options>
    <Options name="GWP_version" default="AR5">
      <Option>AR4</Option>
      <Option>AR5</Option>
      <Option>AR5_CCF</Option>
    </Options>
    <Options name="functional_unit" default="oil">
      <Option>oil</Option>
      <Option>gas</Option>
    </Options>
    <Options name="energy_basis" default="LHV">
      <Option>LHV</Option>
      <Option>HHV</Option>
    </Options>

    <AttrDef name="GWP_years" options="GWP_time_horizon" type="int" unit="years"/>
    <AttrDef name="GWP_version" options="GWP_version" type="str"/>
    <AttrDef name="functional_unit" options="functional_unit" type="str"/>
    <AttrDef name="energy_basis" options="energy_basis" type="str"/>

    <!-- Maximum number of iterations for process loops -->
    <AttrDef name="maximum_iterations" type="int">10</AttrDef>

    <!-- Change threshold for iteration loops. Requires a Process to set a change variable. -->
    <AttrDef name="maximum_change" type="float">0.001</AttrDef>
  </ClassAttrs>
</AttrDefs>
""")
    attr_class_dict = instantiate_subelts(xml, ClassAttrs, as_dict=True)
    return attr_class_dict

@pytest.fixture
def attr_dict_1():
    xml = ET.XML("""
<Model>
	<A name="GWP_years">20</A>
	<A name="GWP_version">AR4</A>
	<A name="maximum_iterations">20</A>
</Model>
""")
    attr_dict = Model.instantiate_attrs(xml)
    return attr_dict

@pytest.mark.parametrize(
    "attr_name, value", [("GWP_years", Quantity(20, 'year')),   # test units and numerical override
                         ("GWP_version", "AR4"),        # test character value override
                         ("energy_basis", "LHV"),       # test character default adopted
                         ("maximum_iterations", 20),    # test numerical value override
                         ("maximum_change", 0.001),     # test numerical default adopted
                         ]
)
def test_defaults(attr_classes, attr_dict_1, attr_name, value):
    assert attr_dict_1[attr_name].value == value

class AttributeHolder(AttributeMixin):
    def __init__(self, attr_dict):
        self.attr_dict = attr_dict

def test_exceptions(attr_classes, attr_dict_1):
    obj = AttributeHolder(attr_dict_1)
    name = 'unknown'
    with pytest.raises(OpgeeException, match=f".*Attribute '{name}' not found in*"):
        obj.attr(name, raiseError=True)