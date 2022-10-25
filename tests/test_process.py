import pytest
from opgee import ureg
from opgee.energy import EN_NATURAL_GAS, EN_CRUDE_OIL
from opgee.emissions import EM_FLARING
from opgee.error import OpgeeException
from opgee.process import Process, _get_subclass, Reservoir


class NotProcess(): pass


def test_subclass_lookup_good(test_model):
    assert _get_subclass(Process, 'ProcA')


def test_subclass_lookup_bad_subclass(test_model):
    with pytest.raises(OpgeeException, match=r'Class .* is not a known subclass of .*'):
        _get_subclass(Process, 'NonExistentProcess')


def test_subclass_lookup_bad_parent(test_model):
    with pytest.raises(OpgeeException, match=r'_get_subclass: cls .* must be one of .*'):
        _get_subclass(NotProcess, 'NonExistentProcess')


def test_set_emission_rates(test_model_with_change):
    analysis = test_model_with_change.get_analysis('test')
    field = analysis.get_field('test')
    procA = field.find_process('ProcA')

    rate_co2 = ureg.Quantity(100.0, 'tonne/day')
    rate_ch4 = ureg.Quantity(30.0, 'tonne/day')
    rate_n2o = ureg.Quantity(6.0, 'tonne/day')

    procA.add_emission_rates(EM_FLARING, CO2=rate_co2, CH4=rate_ch4, N2O=rate_n2o)
    df = procA.get_emission_rates(analysis)
    rates = df[EM_FLARING]

    assert (rates.N2O == rate_n2o and rates.CH4 == rate_ch4 and rates.CO2 == rate_co2)


def test_add_energy_rates(test_model_with_change):
    analysis = test_model_with_change.get_analysis('test')
    field = analysis.get_field('test')
    procA = field.find_process('ProcA')

    unit = ureg.Unit('mmbtu/day')
    ng_rate = ureg.Quantity(123.45, unit)
    oil_rate = ureg.Quantity(4321.0, unit)

    procA.add_energy_rates({EN_NATURAL_GAS: ng_rate, EN_CRUDE_OIL: oil_rate})

    rates = procA.get_energy_rates()

    assert (rates[EN_NATURAL_GAS] == ng_rate and rates[EN_CRUDE_OIL] == oil_rate)


@pytest.fixture(scope='module')
def process(test_model):
    analysis = test_model.get_analysis('test')
    field = analysis.get_field('test')
    proc = field.find_process('ProcA')
    return proc


def test_get_reservoir(process):
    assert isinstance(process.get_reservoir(), Reservoir)


@pytest.fixture(scope='module')
def procB(test_model):
    analysis = test_model.get_analysis('test')
    field = analysis.get_field('test')
    proc = field.find_process('ProcB')
    return proc


def test_find_input_streams_dict(procB):
    obj = procB.find_input_streams("crude oil")
    assert isinstance(obj, dict) and len(obj) == 1


def test_find_input_streams_list(procB):
    obj = procB.find_input_streams("crude oil", as_list=True)
    assert isinstance(obj, list) and len(obj) == 1


def test_find_input_stream(procB):
    procB.find_input_stream("crude oil")


def test_find_output_stream(process):
    process.find_output_stream("crude oil")


def test_find_input_stream_error(procB):
    stream_type = 'unknown_stream_type'
    with pytest.raises(OpgeeException, match=f".* no input streams contain '{stream_type}'"):
        procB.find_input_stream(stream_type)


def test_venting_fugitive_rate(test_model):
    analysis = test_model.get_analysis('test')
    field = analysis.get_field('test')
    procA = field.find_process('ProcA')
    rate = procA.venting_fugitive_rate()

    # mean of 1000 random draws from uniform(0.001, .003) should be ~0.002
    assert rate == pytest.approx(0.002, abs=0.0005)


def test_set_intermediate_value(procB):
    value = 123.456
    unit = 'degF'
    q = ureg.Quantity(value, unit)

    iv = procB.iv
    iv.store('temp', q)
    row = iv.get('temp')

    assert row['value'] == q.m and ureg.Unit(row['unit']) == q.u


def test_bad_intermediate_value(procB):
    iv = procB.iv
    with pytest.raises(OpgeeException, match=f"An intermediate value for '.*' was not found"):
        row = iv.get('non-existent')


foo = 1.0
bar = dict(x=1, y=2)
baz = "a string"


@pytest.mark.parametrize(
    "name, value", [('foo', foo), ('bar', bar), ('baz', baz)])
def test_process_data(procB, name, value):
    field = procB.field
    field.save_process_data(foo=foo, bar=bar, baz=baz)

    assert field.get_process_data(name) == value


def test_bad_process_data(procB):
    with pytest.raises(OpgeeException, match='Process data dictionary does not include .*'):
        procB.field.get_process_data("nonexistent-data-key", raiseError=True)


def approx_equal(a, b, abs=10E-8):
    "Check that two Quantities are approximately equal"
    return a.m == pytest.approx(b.m, abs=abs)

# Test gas processing units
def test_VRUCompressor(test_model):
    analysis = test_model.get_analysis('test_gas_processes')
    field = analysis.get_field('test_VRUCompressor')
    field.run(analysis)
    proc = field.find_process('VRUCompressor')
    # ensure total energy flow rates
    total = proc.energy.data.sum()
    expected = ureg.Quantity(0.341449400556889, "mmbtu/day")
    assert approx_equal(total, expected)


def test_VFPartition(test_model):
    analysis = test_model.get_analysis('test_gas_processes')
    field = analysis.get_field('test_VFPartition')
    field.run(analysis)
    proc = field.find_process('VFPartition')
    # ensure total energy flow rates
    total = proc.find_output_stream("methane slip").gas_flow_rates().sum()
    expected = ureg.Quantity(71.03912192600949, "tonne/day")
    assert approx_equal(total, expected)


def test_Flaring(test_model):
    analysis = test_model.get_analysis('test_gas_processes')
    field = analysis.get_field('test_Flaring')
    field.run(analysis)
    proc = field.find_process('Flaring')
    # ensure total energy flow rates
    total = proc.emissions.rates(analysis.gwp).loc["GHG"].sum()
    expected = ureg.Quantity(5298.998755911673, "tonne/day")
    assert approx_equal(total, expected)


def test_Venting(test_model):
    analysis = test_model.get_analysis('test_gas_processes')
    field = analysis.get_field('test_Venting')
    field.run(analysis)
    proc = field.find_process('Venting')
    # ensure total energy flow rates
    total = proc.emissions.rates(analysis.gwp).loc["GHG"].sum()
    expected = ureg.Quantity(1149.7618654739997, "tonne/day")
    assert approx_equal(total, expected)


def test_AcidGasRemoval(test_model):
    analysis = test_model.get_analysis('test_gas_processes')
    field = analysis.get_field('test_AcidGasRemoval')
    field.run(analysis)
    proc = field.find_process('AcidGasRemoval')
    # ensure total energy flow rates
    total = proc.energy.data.sum()
    expected = ureg.Quantity(268.768111460195, "mmbtu/day")
    assert approx_equal(total, expected)


def test_GasDehydration(test_model):
    analysis = test_model.get_analysis('test_gas_processes')
    field = analysis.get_field('test_GasDehydration')
    field.run(analysis)
    proc = field.find_process('GasDehydration')
    # ensure total energy flow rates
    total = proc.energy.data.sum()
    expected = ureg.Quantity(681.6879728269338, "mmbtu/day")
    assert approx_equal(total, expected)


def test_Demethanizer(test_model):
    analysis = test_model.get_analysis('test_gas_processes')
    field = analysis.get_field('test_Demethanizer')
    field.run(analysis)
    proc = field.find_process('Demethanizer')
    # ensure total energy flow rates
    total = proc.energy.data.sum()
    expected = ureg.Quantity(37.91301173818107, "mmbtu/day")
    assert approx_equal(total, expected)


def test_PreMembraneChiller(test_model):
    analysis = test_model.get_analysis('test_gas_processes')
    field = analysis.get_field('test_PreMembraneChiller')
    field.run(analysis)
    proc = field.find_process('PreMembraneChiller')
    # ensure total energy flow rates
    total = proc.energy.data.sum()
    expected = ureg.Quantity(907.0197708571166, "mmbtu/day")
    assert approx_equal(total, expected)


def test_PreMembraneCompressor(test_model):
    analysis = test_model.get_analysis('test_gas_processes')
    field = analysis.get_field('test_PreMembraneCompressor')
    field.run(analysis)
    proc = field.find_process('PreMembraneCompressor')
    # ensure total energy flow rates
    assert proc.energy.data.sum() == ureg.Quantity(0.0, "mmbtu/day")


def test_CO2Membrane(test_model):
    analysis = test_model.get_analysis('test_gas_processes')
    field = analysis.get_field('test_CO2Membrane')
    field.run(analysis)
    proc = field.find_process('CO2Membrane')
    # ensure total energy flow rates
    total = proc.energy.data.sum()
    expected = ureg.Quantity(4048.7718266075976, "mmbtu/day")
    assert approx_equal(total, expected)


def test_CO2ReinjectionCompressor(test_model):
    analysis = test_model.get_analysis('test_gas_processes')
    field = analysis.get_field('test_CO2ReinjectionCompressor')
    field.run(analysis)
    proc = field.find_process('CO2ReinjectionCompressor')
    # ensure total energy flow rates
    total = proc.energy.data.sum()
    expected = ureg.Quantity(7164.538831055389, "mmbtu/day")
    assert approx_equal(total, expected)


def test_CO2InjectionWell(test_model):
    analysis = test_model.get_analysis('test_gas_processes')
    field = analysis.get_field('test_CO2InjectionWell')
    field.run(analysis)
    proc = field.find_process('CO2InjectionWell')
    # ensure total energy flow rates
    assert proc.emissions.rates(analysis.gwp).loc["GHG"].sum() == ureg.Quantity(0.259990500904288, "tonne/day")


def test_RyanHolmes(test_model):
    analysis = test_model.get_analysis('test_gas_processes')
    field = analysis.get_field('test_RyanHolmes')
    field.run(analysis)
    proc = field.find_process('RyanHolmes')
    # ensure total energy flow rates
    total = proc.energy.data.sum()
    expected = ureg.Quantity(416.0247918820408, "mmbtu/day")
    assert approx_equal(total, expected)


def test_SourGasCompressor(test_model):
    analysis = test_model.get_analysis('test_gas_processes')
    field = analysis.get_field('test_SourGasCompressor')
    field.run(analysis)
    proc = field.find_process('SourGasCompressor')
    # ensure total energy flow rates
    total = proc.energy.data.sum()
    expected = ureg.Quantity(245.10194671727402, "mmbtu/day")
    assert approx_equal(total, expected)



def test_SourGasInjection(test_model):
    analysis = test_model.get_analysis('test_gas_processes')
    field = analysis.get_field('test_SourGasInjection')
    field.run(analysis)
    proc = field.find_process('SourGasInjection')
    # ensure total energy flow rates
    total = proc.emissions.rates(analysis.gwp).loc["GHG"].sum()
    expected = ureg.Quantity(2.8431898600000003, "tonne/day")
    assert approx_equal(total, expected)


def test_GasReinjectionCompressor(test_model):
    analysis = test_model.get_analysis('test_gas_processes')
    field = analysis.get_field('test_GasReinjectionCompressor')
    field.run(analysis)
    proc = field.find_process('GasReinjectionCompressor')
    # ensure total energy flow rates
    total = proc.energy.data.sum()
    expected = ureg.Quantity(64286.0886714168, "mmbtu/day")
    assert approx_equal(total, expected)


def test_N2Flooding(test_model):
    analysis = test_model.get_analysis('test_gas_processes')
    field = analysis.get_field('test_N2Flooding')
    field.run(analysis)
    proc = field.find_process('GasPartition')
    # ensure total energy flow rates
    assert proc.find_output_stream("gas for gas reinjection compressor").gas_flow_rates().sum() == \
           ureg.Quantity(25127.68891663532, "tonne/day")
    assert proc.find_output_stream("gas").gas_flow_rates().sum() == ureg.Quantity(758.78647, "tonne/day")


def test_CO2Flooding_CO2_reinjection(test_model_with_change):
    analysis = test_model_with_change.get_analysis('test_gas_processes')
    field = analysis.get_field('test_CO2Flooding')
    field.save_process_data(CO2_reinjection_mass_rate=ureg.Quantity(8364.59303, "tonne/day"))
    field.run(analysis)
    proc = field.find_process('GasPartition')
    # ensure total energy flow rates
    total = proc.find_output_stream("gas for gas reinjection compressor").gas_flow_rates().sum()
    expected = ureg.Quantity(1399.5948519637434, "tonne/day")
    assert approx_equal(total, expected)

    assert proc.find_output_stream("gas").gas_flow_rates().sum() == ureg.Quantity(24885.555110000005, "tonne/day")


def test_CO2Flooding_non_zero(test_model_with_change):
    analysis = test_model_with_change.get_analysis('test_gas_processes')
    field = analysis.get_field('test_CO2Flooding')
    field.save_process_data(CO2_reinjection_mass_rate=ureg.Quantity(100000, "tonne/day"))
    field.run(analysis)
    proc = field.find_process('GasPartition')
    # ensure total energy flow rates
    assert proc.find_output_stream("gas for gas reinjection compressor").gas_flow_rates().sum() == \
           ureg.Quantity(0, "tonne/day")
    assert proc.find_output_stream("gas").gas_flow_rates().sum() == ureg.Quantity(24885.555110000005, "tonne/day")


def test_NGFlooding_onsite(test_model):
    analysis = test_model.get_analysis('test_gas_processes')
    field = analysis.get_field('test_NGFlooding_onsite_gas')
    field.run(analysis)
    proc = field.find_process('GasPartition')
    # ensure total energy flow rates
    assert proc.find_output_stream("gas for gas reinjection compressor").gas_flow_rates().sum() == \
           ureg.Quantity(3824.449990753103, "tonne/day")
    assert proc.find_output_stream("gas").gas_flow_rates().sum() == ureg.Quantity(22187.2424492469, "tonne/day")


def test_CO2Flooding_sour_gas_reinjection(test_model_with_change):
    analysis = test_model_with_change.get_analysis('test_gas_processes')
    field = analysis.get_field('test_CO2Flooding')
    field.save_process_data(sour_gas_reinjection_mass_rate=ureg.Quantity(8387.50113, "tonne/day"))
    field.run(analysis)
    proc = field.find_process('GasPartition')

    # ensure total energy flow rates
    s = proc.find_output_stream("gas for gas reinjection compressor")
    total = s.gas_flow_rates().sum()
    expected = ureg.Quantity(1375.9995089637432, "tonne/day")
    assert approx_equal(total, expected)

    assert proc.find_output_stream("gas").gas_flow_rates().sum() == ureg.Quantity(24885.555110000005, "tonne/day")


def test_NGFlooding_offset(test_model):
    analysis = test_model.get_analysis('test_gas_processes')
    field = analysis.get_field('test_NGFlooding_offset_gas')
    field.run(analysis)
    proc = field.find_process('GasPartition')
    # ensure total energy flow rates
    assert proc.find_output_stream("gas for gas reinjection compressor").gas_flow_rates().sum() == \
           ureg.Quantity(382444.9990753103, "tonne/day")
    assert proc.find_output_stream("gas").gas_flow_rates().sum() == ureg.Quantity(0, "tonne/day")


def test_GasLifting(test_model):
    analysis = test_model.get_analysis('test_gas_processes')
    field = analysis.get_field('test_GasLifting')
    field.run(analysis)
    proc = field.find_process('GasPartition')
    # ensure total energy flow rates
    assert proc.find_output_stream("lifting gas").gas_flow_rates().sum() == \
           ureg.Quantity(176.35032820055403, "tonne/day")
    assert proc.find_output_stream("gas").gas_flow_rates().sum() == ureg.Quantity(1486.1372117994458, "tonne/day")



