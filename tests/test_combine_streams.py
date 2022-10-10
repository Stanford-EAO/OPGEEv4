import pytest
from opgee.core import TemperaturePressure
from opgee.stream import Stream
from opgee import ureg
from opgee.combine_streams import combine_streams, combine_thm_streams
from thermosteam import Chemical, Chemicals, MultiStream
import thermosteam as tmo
from opgee.table_manager import TableManager

test_tp1 = TemperaturePressure(ureg.Quantity(90, "degF"), ureg.Quantity(500, "psia"))

test_tp2 = TemperaturePressure(ureg.Quantity(60, "degF"), ureg.Quantity(165, "psia"))

def test_combine_streams():
    s = Stream("test_stream2", test_tp2)
    s.set_flow_rate("N2", "gas", 525.318807)
    s.set_flow_rate("CO2", "gas", 5594.456607)
    s.set_flow_rate("C1", "gas", 354.916584)
    s.set_flow_rate("C2", "gas", 74.644754)
    s.set_flow_rate("C3", "gas", 49.183948)
    s.set_flow_rate("C4", "gas", 38.116475)

    s0 = Stream("test_stream1", test_tp1)
    s0.set_flow_rate("CO2", "gas", 2770.14636)

    sc = combine_streams([s, s0], API=ureg.Quantity(32, 'frac'))
    total_flow = sc.total_flow_rate()
    assert total_flow == ureg.Quantity(pytest.approx(9406.78, rel=1e-2), "t/d")

df = TableManager().get_table("composite-oil")
chemicals = Chemicals({name: Chemical(name) for name in df.index}, cache=True)
tmo.settings.set_thermo(chemicals, cache=True)

s1 = MultiStream(ID="s1",
         g=[("CO2",2770.14636)],
         T=90,
         P=500)

s2 = MultiStream(ID="s2",
        g=[("N2",525.318807),
         ("CO2",5594.456607),
         ("CH4",354.916584),
         ("C2",74.644754),
         ("C3",49.183948),
         ("i-C4",38.116475)],
         T=60,
         P=165)


def test_combine_thm_streams():
    s_sum = combine_thm_streams([s1,s2])
    total_flow = ureg.Quantity(s_sum.get_flow('t/d').sum(), 't/d')
    assert total_flow == ureg.Quantity(pytest.approx(9483.849, rel=1e-2), "t/d")