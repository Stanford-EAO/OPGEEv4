import pytest
from opgee.core import TemperaturePressure
from opgee.stream import Stream
from opgee import ureg
from opgee.combine_streams import combine_streams, combine_streams_thm
from thermosteam import Chemical, Chemicals, MultiStream
import thermosteam as tmo
from opgee.table_manager import TableManager

test_tp1 = TemperaturePressure(ureg.Quantity(90, "degF"), ureg.Quantity(500, "psia"))

test_tp2 = TemperaturePressure(ureg.Quantity(60, "degF"), ureg.Quantity(165, "psia"))


def test_combine_streams():

    s0 = Stream("test_stream1", test_tp1)
    s0.set_flow_rate("CO2", "gas", 2770.14636)

    s = Stream("test_stream2", test_tp2)
    s.set_flow_rate("N2", "gas", 525.318807)
    s.set_flow_rate("CO2", "gas", 5594.456607)
    s.set_flow_rate("C1", "gas", 354.916584)
    s.set_flow_rate("C2", "gas", 74.644754)
    s.set_flow_rate("C3", "gas", 49.183948)
    s.set_flow_rate("C4", "gas", 38.116475)

    sc = combine_streams([s, s0], API=ureg.Quantity(70, 'frac'))  # API arbitrary inputted
    total_flow = sc.total_flow_rate()
    assert total_flow == ureg.Quantity(pytest.approx(9406.78, rel=1e-2), "t/d")


df = TableManager().get_table("general-chemicals")
chemicals = Chemicals({name: Chemical(name) for name in df.index}, cache=True)
tmo.settings.set_thermo(chemicals, cache=True)

s1 = MultiStream(ID="s1",
                 g=[("CO2", 2770.14636)],
                 units="t/d",
                 T=test_tp1.T.to("K").m,  #: K
                 P=test_tp1.P.to("Pa").m)  #: Pa

s2 = MultiStream(ID="s2",
                 g=[("N2", 525.318807),
                    ("CO2", 5594.456607),
                    ("CH4", 354.916584),
                    ("C2", 74.644754),
                    ("C3", 49.183948),
                    ("C4", 38.116475)],
                 units="t/d",
                 T=test_tp2.T.to("K").m,  #: K
                 P=test_tp2.P.to("Pa").m)  #: Pa


def test_combine_streams_thm():
    s_sum = combine_streams_thm([s1,s2])
    total_flow = ureg.Quantity(s_sum.get_flow('t/d').sum(), 't/d')
    assert total_flow == ureg.Quantity(pytest.approx(9483.849, rel=1e-2), "t/d")
