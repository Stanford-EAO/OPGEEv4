import pytest
from lxml import etree as ET
from opgee import ureg
from opgee.analysis import Analysis
from opgee.attributes import ClassAttrs, AttributeMixin, AttrDefs
from opgee.core import instantiate_subelts
from opgee.error import OpgeeException, AttributeError
from opgee.model import Model


@pytest.fixture
def attr_classes():
    xml = ET.XML("""
<AttrDefs>
  <ClassAttrs name="Analysis">
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

    <AttrDef name="GWP_horizon" options="GWP_time_horizon" type="int" unit="years"/>
    <AttrDef name="GWP_version" options="GWP_version" type="str"/>
    <AttrDef name="functional_unit" options="functional_unit" type="str"/>
  </ClassAttrs>
  
  <ClassAttrs name="Model">
    <!-- Maximum number of iterations for process loops -->
    <AttrDef name="maximum_iterations" type="int">10</AttrDef>

    <!-- Change threshold for iteration loops. Requires a Process to set a change variable. -->
    <AttrDef name="maximum_change" type="float">0.001</AttrDef>
  </ClassAttrs>
</AttrDefs>
""")
    AttrDefs.load_attr_defs(xml)
    attr_class_dict = instantiate_subelts(xml, ClassAttrs, as_dict=True)
    return attr_class_dict


@pytest.fixture
def attr_dict_1():
    xml = ET.XML("""
<Model>
	<A name="maximum_iterations">20</A>
</Model>
""")
    attr_dict = Model.instantiate_attrs(xml)
    return attr_dict


@pytest.fixture
def attr_dict_2(attr_classes):
    xml = ET.XML("""
<Analysis>
  <A name="GWP_horizon">20</A>
  <A name="GWP_version">AR4</A>    
</Analysis>
""")
    attr_dict = Analysis.instantiate_attrs(xml)
    return attr_dict


@pytest.mark.parametrize(
    "attr_name, value", [("maximum_iterations", 20),  # test numerical value override
                         ("maximum_change", 0.001),  # test numerical default adopted
                         ]
)
def test_model_defaults(attr_classes, attr_dict_1, attr_name, value):
    assert attr_dict_1[attr_name].value == value


@pytest.mark.parametrize(
    "attr_name, value", [("GWP_horizon", ureg.Quantity(20.0, 'year')),  # test units and numerical override
                         ("GWP_version", "AR4"),  # test character value override
                         ("functional_unit", "oil"),  # test character default adopted
                         ]
)
def test_analysis_defaults(attr_classes, attr_dict_2, attr_name, value):
    assert attr_dict_2[attr_name].value == value


class AttributeHolder(AttributeMixin):
    def __init__(self, attr_dict):
        self.attr_dict = attr_dict


def test_exceptions(attr_classes, attr_dict_1):
    obj = AttributeHolder(attr_dict_1)
    name = 'unknown'
    with pytest.raises(OpgeeException, match=f".*Attribute '{name}' not found in*"):
        obj.attr(name)


def test_string_rep(attr_classes):
    name = 'functional_unit'
    adef = attr_classes['Analysis'].attribute(name)
    s = str(adef)
    assert s == f"<AttrDef name='{name}' type='{adef.pytype}' default='{adef.default}' options='{adef.option_set}'>"


def test_unknown_attribute(attr_classes):
    name = 'unknown-attribute'
    with pytest.raises(AttributeError, match=f"Attribute definition for '{name}' was not found"):
        attr_classes['Model'].attribute(name)
