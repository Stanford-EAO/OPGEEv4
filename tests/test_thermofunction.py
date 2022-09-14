import pandas as pd
import pytest
from opgee.core import TemperaturePressure
from opgee.stream import Stream
from opgee import ureg


@pytest.fixture(scope="module")
def oil_instance(test_model):
    field = test_model.get_field("test")
    return field.oil


@pytest.fixture(scope="module")
def moil_instance(test_model):
    field = test_model.get_field("test")
    return field.m_oil


# 1 GAS SPECIFIC GRAVITY
def test_gas_specific_gravity(oil_instance):
    gas_SG = oil_instance.gas_specific_gravity
    assert gas_SG == ureg.Quantity(pytest.approx(49.8373178), "percent")


def test_gas_specific_gravity_mo(moil_instance):
    gas_SG = moil_instance.gas_specific_gravity
    assert gas_SG == ureg.Quantity(pytest.approx(49.8373178), "percent")


# 2 OIL SPECIFIC GRAVITY
def test_oil_specific_gravity(oil_instance):
    oil_SG = oil_instance.specific_gravity(oil_instance.API)
    assert oil_SG == ureg.Quantity(pytest.approx(oil_instance.oil_specific_gravity.m), "frac")


def test_oil_specific_gravity_mo(moil_instance):
    oil_SG = moil_instance.specific_gravity(moil_instance.API)
    assert oil_SG == ureg.Quantity(pytest.approx(moil_instance.oil_specific_gravity.m), "frac")


# 3 BUBBLE POINT PRESSURE
def test_bubble_point_pressure(oil_instance):
    stream = Stream("test_stream", test_tp)  #: T=200.0 °F P=1556.0 psia
    oil_SG = oil_instance.oil_specific_gravity
    gas_SG = oil_instance.gas_specific_gravity
    GOR = oil_instance.gas_oil_ratio
    p_bubblepoint = oil_instance.bubble_point_pressure(stream, oil_SG, gas_SG, GOR)
    assert p_bubblepoint == ureg.Quantity(pytest.approx(9439.75353), "psia")


def test_bubble_point_pressure_mo(moil_instance):
    # self.res_tp 200.0 °F 1556.6 psia
    p_bubblepoint = moil_instance.bubble_point_pressure()
    assert p_bubblepoint == ureg.Quantity(pytest.approx(69.8200871), "psia")


# 4 SOLUTION GOR
def test_solution_gas_oil_ratio(oil_instance):
    stream = Stream("test_stream", test_tp)
    oil_SG = oil_instance.oil_specific_gravity
    gas_SG = oil_instance.gas_specific_gravity
    GOR = oil_instance.gas_oil_ratio
    solution_gor = oil_instance.solution_gas_oil_ratio(stream, oil_SG, gas_SG, GOR)
    assert solution_gor == ureg.Quantity(pytest.approx(282.87108), "scf/bbl_oil")


def test_solution_gas_oil_ratio_mo(moil_instance):
    solution_gor = moil_instance.solution_gas_oil_ratio(T=test_tp.T,P=test_tp.P)
    assert solution_gor == ureg.Quantity(pytest.approx(0.0116082838), "scf/bbl_oil")


# 5 RESERVOIR SOLUTION GOR
# TODO only used in test
def test_reservoir_solution_GOR(oil_instance):
    res_GOR = oil_instance.reservoir_solution_GOR()
    assert res_GOR == ureg.Quantity(pytest.approx(283.010274), "scf/bbl_oil")


def test_reservoir_solution_GOR_mo(moil_instance):
    res_GOR = moil_instance.reservoir_solution_GOR()
    assert res_GOR == ureg.Quantity(pytest.approx(0.0116082838), "scf/bbl_oil")


# 6 BUBBLE POINT SOLUTION GOR
def test_bubble_point_solution_GOR(oil_instance):
    GOR = oil_instance.gas_oil_ratio
    gor_bubble = oil_instance.bubble_point_solution_GOR(GOR)
    assert gor_bubble == ureg.Quantity(pytest.approx(2822.361), "scf/bbl_oil")


# mo: run-able, but returns 0; should this be same implementation with Oil as well?
#       GOR from input is separator, this is bubble point???
def test_bubble_point_solution_GOR_mo(moil_instance):
    GOR = moil_instance.gas_oil_ratio
    gor_bubble = moil_instance.bubble_point_solution_GOR(GOR)
    assert gor_bubble == ureg.Quantity(pytest.approx(2429.299), "scf/bbl_oil")

test_tp = TemperaturePressure(ureg.Quantity(200.0, "degF"), ureg.Quantity(1556.0, "psia"))


# 7 FORMATION VOLUME FACTOR
def test_formation_volume_factor(oil_instance):
    stream = Stream("test_stream", test_tp)
    oil_SG = oil_instance.oil_specific_gravity
    gas_SG = oil_instance.gas_specific_gravity
    GOR = oil_instance.gas_oil_ratio
    fvf = oil_instance.formation_volume_factor(stream, oil_SG, gas_SG, GOR)
    assert fvf == ureg.Quantity(pytest.approx(1.18694952), "frac")


def test_formation_volume_factor_mo(moil_instance):
    # stream = Stream("test_stream", test_tp)
    # oil_SG = oil_instance.oil_specific_gravity
    # gas_SG = oil_instance.gas_specific_gravity
    # GOR = oil_instance.gas_oil_ratio
    fvf = moil_instance.formation_volume_factor()
    assert fvf == ureg.Quantity(pytest.approx(1.18694952), "frac")


# 8 SAT FORMATION VOLUME FACTOR
def test_saturated_formation_volume_factor(oil_instance):
    stream = Stream("test_stream", test_tp)
    oil_SG = oil_instance.oil_specific_gravity
    gas_SG = oil_instance.gas_specific_gravity
    GOR = oil_instance.gas_oil_ratio
    sat_fvf = oil_instance.saturated_formation_volume_factor(stream, oil_SG, gas_SG, GOR)
    assert sat_fvf == ureg.Quantity(pytest.approx(1.18694952), "frac")


# TODO failed to evaluate liquid molar volume for C3 at T 366 and P 10732379Pa
def test_saturated_formation_volume_factor_mo(moil_instance):
    # stream = Stream("test_stream", test_tp)
    # oil_SG = moil_instance.oil_specific_gravity
    # gas_SG = moil_instance.gas_specific_gravity
    # GOR = moil_instance.gas_oil_ratio
    sat_fvf = moil_instance.saturated_formation_volume_factor()
    print(sat_fvf)
    # assert sat_fvf == ureg.Quantity(pytest.approx(1.19898185), "frac")


# 9 UNSAT FORMATION VOLUME FACTOR
def test_unsat_formation_volume_factor(oil_instance):
    stream = Stream("test_stream", test_tp)
    oil_SG = oil_instance.oil_specific_gravity
    gas_SG = oil_instance.gas_specific_gravity
    GOR = oil_instance.gas_oil_ratio
    unsat_fvf = oil_instance.unsat_formation_volume_factor(stream, oil_SG, gas_SG, GOR)
    assert unsat_fvf == ureg.Quantity(pytest.approx(1.21592072), "frac")


def test_unsat_formation_volume_factor_mo(moil_instance):
    # stream = Stream("test_stream", test_tp)
    # oil_SG = moil_instance.oil_specific_gravity
    # gas_SG = moil_instance.gas_specific_gravity
    # GOR = moil_instance.gas_oil_ratio
    unsat_fvf = moil_instance.unsat_formation_volume_factor()
    assert unsat_fvf == ureg.Quantity(pytest.approx(1.22745738), "frac")


# 10 ISOTHERMAL COMPRESSIBILITY X
def test_isothermal_compressibility_X(oil_instance):
    stream = Stream("test_stream", test_tp)
    oil_SG = oil_instance.oil_specific_gravity
    gas_SG = oil_instance.gas_specific_gravity
    GOR = oil_instance.gas_oil_ratio
    iso_compress_x = oil_instance.isothermal_compressibility_X(stream, oil_SG, gas_SG, GOR)
    assert iso_compress_x == ureg.Quantity(0.0, "pa**-1")


def test_isothermal_compressibility_X_mo(moil_instance):
    iso_compress_x = moil_instance.isothermal_compressibility_X()
    assert iso_compress_x == ureg.Quantity(4.296622906167477e-06, "pa**-1")


# 11 ISOTHERMAL COMPRESSIBILITY
def test_isothermal_compressibility(oil_instance):
    oil_SG = oil_instance.oil_specific_gravity
    iso_compress = oil_instance.isothermal_compressibility(oil_SG)
    assert iso_compress == ureg.Quantity(pytest.approx(3.0528295800365155e-6), "pa**-1")


# 12 OIL DENSITY
def test_oil_density(oil_instance):
    stream = Stream("test_stream", test_tp)
    oil_SG = oil_instance.oil_specific_gravity
    gas_SG = oil_instance.gas_specific_gravity
    GOR = oil_instance.gas_oil_ratio
    density = oil_instance.density(stream, oil_SG, gas_SG, GOR)
    assert density == ureg.Quantity(pytest.approx(46.8997952), "lb/ft**3")


def test_oil_density_mo(moil_instance):
    density = moil_instance.density()
    assert density == ureg.Quantity(pytest.approx(24.1560053), "lb/ft**3")


# 13 OIL VOLUME FLOW RATE
def test_oil_volume_flow_rate(oil_instance):
    stream = Stream("test_stream", test_tp)
    stream.set_flow_rate("oil", "liquid", 276.534764) #: flow rate unit:ton/day
    oil_SG = oil_instance.oil_specific_gravity
    gas_SG = oil_instance.gas_specific_gravity
    GOR = oil_instance.gas_oil_ratio
    volume_flow_rate = oil_instance.volume_flow_rate(stream, oil_SG, gas_SG, GOR)
    assert volume_flow_rate == ureg.Quantity(pytest.approx(2315.23726), "bbl_oil/day")


def test_oil_volume_flow_rate_mo(moil_instance):
    volume_flow_rate = moil_instance.volume_flow_rate(total_flow = 276.534764)
    assert volume_flow_rate == ureg.Quantity(pytest.approx(3073.314063), "bbl_oil/day")


# 14 OIL MASS ENERGY DENSITY
def test_oil_mass_energy_density(oil_instance):
    mass_energy_density = oil_instance.oil_LHV_mass
    assert mass_energy_density == ureg.Quantity(pytest.approx(18279.816), "btu/lb")


def test_oil_mass_energy_density_mo(moil_instance):
    mass_energy_density = moil_instance.oil_LHV_mass
    assert mass_energy_density == ureg.Quantity(pytest.approx(19144.420), "btu/lb")


# 15 OIL VOLUME ENERGY DENSITY
def test_oil_volume_energy_density(oil_instance):
    stream = Stream("test_stream", test_tp)
    oil_SG = oil_instance.oil_specific_gravity
    gas_SG = oil_instance.gas_specific_gravity
    GOR = oil_instance.gas_oil_ratio
    volume_energy_density = oil_instance.volume_energy_density(stream, oil_SG, gas_SG, GOR)
    assert volume_energy_density == ureg.Quantity(pytest.approx(4.8147356), "mmBtu/bbl_oil")


def test_oil_volume_energy_density_mo(moil_instance):
    volume_energy_density = moil_instance.volume_energy_density()
    assert volume_energy_density == ureg.Quantity(pytest.approx(1.94644606), "mmBtu/bbl_oil")


# 16 OIL ENERGY FLOW RATE
def test_oil_energy_flow_rate(oil_instance):
    stream = Stream("test_stream", test_tp)
    stream.set_flow_rate("oil", "liquid", 273.831958)
    energy_flow_rate = oil_instance.energy_flow_rate(stream)
    assert energy_flow_rate == ureg.Quantity(pytest.approx(11035.4544), "mmbtu/day")


def test_oil_energy_flow_rate_mo(moil_instance):
    energy_flow_rate = moil_instance.energy_flow_rate(total_flow=273.831958)
    assert energy_flow_rate == ureg.Quantity(pytest.approx(10484.2422), "mmbtu/day")


# 17 OIL HEAT CAPACITY
def test_oil_heat_capacity(oil_instance):
    temp = ureg.Quantity(127.5, "degF")
    API = oil_instance.API
    heat_capacity = oil_instance.specific_heat(API, temp)
    assert heat_capacity == ureg.Quantity(pytest.approx(0.48734862), "btu/lb/degF")


def test_oil_heat_capacity_mo(moil_instance):
    temp = ureg.Quantity(127.5, "degF")
    heat_capacity = moil_instance.specific_heat(moil_instance, temp)
    print(heat_capacity)
    assert heat_capacity == ureg.Quantity(pytest.approx(0.561397723), "btu/lb/degF")

# 18 LIQUID FUEL COMP
def test_liquid_fuel_comp(oil_instance):
    API = ureg.Quantity(10, "degAPI")
    liquid_fuel_comp = oil_instance.liquid_fuel_composition(API)
    assert liquid_fuel_comp["C"] == ureg.Quantity(pytest.approx(71.432), "mol/kg")


def test_liquid_fuel_comp_mo(moil_instance):
    API = ureg.Quantity(10, "degAPI")
    liquid_fuel_comp = moil_instance.liquid_fuel_composition(API)
    assert liquid_fuel_comp["C"] == ureg.Quantity(pytest.approx(71.432), "mol/kg")


@pytest.fixture
def gas_instance(test_model):
    field = test_model.get_field("test")
    return field.gas


@pytest.fixture
def stream():
    s = Stream("test_stream", test_tp)
    s.set_flow_rate("N2", "gas", 4.90497)
    s.set_flow_rate("CO2", "gas", 0.889247)
    s.set_flow_rate("C1", "gas", 87.59032)
    s.set_flow_rate("C2", "gas", 9.75715)
    s.set_flow_rate("C3", "gas", 4.37353)
    s.set_flow_rate("C4", "gas", 2.52654)
    return s


def test_total_molar_flow_rate(gas_instance, stream):
    total_molar_flow_rate = gas_instance.total_molar_flow_rate(stream)
    assert total_molar_flow_rate == ureg.Quantity(pytest.approx(6122349.16), "mol/day")


def test_molar_flow_rate(gas_instance, stream):
    molar_flow_rate = gas_instance.molar_flow_rate(stream, "C1")
    assert molar_flow_rate == ureg.Quantity(pytest.approx(5459905.78), "mol/day")


def test_component_molar_fraction_N2(gas_instance, stream):
    component_molar_fraction = gas_instance.component_molar_fraction("N2", stream)
    assert component_molar_fraction == ureg.Quantity(pytest.approx(0.0285991048), "frac")


def test_component_molar_fraction_C1(gas_instance, stream):
    component_molar_fraction = gas_instance.component_molar_fraction("C1", stream)
    assert component_molar_fraction == ureg.Quantity(pytest.approx(0.891799149), "frac")


def test_component_mass_fraction(gas_instance, stream):
    molar_fracs = pd.Series([0.004, 0.9666, 0.02, 0.01],
                            index=["N2", "C1", "C2", "C3"], dtype="pint[mol/mol]")
    mass_fracs = gas_instance.component_mass_fractions(molar_fracs)
    assert mass_fracs["C1"] == ureg.Quantity(pytest.approx(0.9307131413113588))


def test_specific_gravity(gas_instance, stream):
    specific_gravity = gas_instance.specific_gravity(stream)
    assert specific_gravity == ureg.Quantity(pytest.approx(0.62300076), "frac")


def test_ratio_of_specific_heat(gas_instance, stream):
    ratio_of_specific_heat = gas_instance.ratio_of_specific_heat(stream)
    assert ratio_of_specific_heat == ureg.Quantity(pytest.approx(1.28972962), "frac")


def test_gas_heat_capacity(gas_instance, stream):
    heat_capacity = gas_instance.heat_capacity(stream)
    assert heat_capacity == ureg.Quantity(pytest.approx(132557.175), "btu/degF/day")


def test_uncorrected_pseudocritical_temperature(gas_instance, stream):
    pseudocritical_temp = gas_instance.uncorrected_pseudocritical_temperature_and_pressure(stream)["temperature"]
    assert pseudocritical_temp == ureg.Quantity(pytest.approx(361.164867), "rankine")


def test_uncorrected_pseudocritical_pressure(gas_instance, stream):
    pseudocritical_press = gas_instance.uncorrected_pseudocritical_temperature_and_pressure(stream)["pressure"]
    assert pseudocritical_press == ureg.Quantity(pytest.approx(669.895774), "psia")


def test_corrected_pseudocritical_temperature(gas_instance, stream):
    corr_pseudocritical_temp = gas_instance.corrected_pseudocritical_temperature(stream)
    assert corr_pseudocritical_temp == ureg.Quantity(pytest.approx(361.164867), "rankine")


def test_corrected_pseudocritical_pressure(gas_instance, stream):
    corr_pseudocritical_press = gas_instance.corrected_pseudocritical_pressure(stream)
    assert corr_pseudocritical_press == ureg.Quantity(pytest.approx(669.895774), "psia")


def test_reduced_temperature(gas_instance, stream):
    reduced_temperature = gas_instance.reduced_temperature(stream)
    assert reduced_temperature == ureg.Quantity(pytest.approx(1.82650656), "frac")


def test_reduced_pressure(gas_instance, stream):
    reduced_press = gas_instance.reduced_pressure(stream)
    assert reduced_press == ureg.Quantity(pytest.approx(2.32274939), "frac")


def test_Z_factor(gas_instance, stream):
    reduced_temp = gas_instance.reduced_temperature(stream)
    reduced_press = gas_instance.reduced_pressure(stream)
    z_factor = gas_instance.Z_factor(reduced_temp, reduced_press)
    assert z_factor == ureg.Quantity(pytest.approx(0.913575608), "frac")


def test_volume_factor(gas_instance, stream):
    vol_factor = gas_instance.volume_factor(stream)
    assert vol_factor == ureg.Quantity(pytest.approx(0.0109559824, abs=0.0005), "frac")


def test_gas_density(gas_instance, stream):
    density = gas_instance.density(stream)
    assert density == ureg.Quantity(pytest.approx(0.069296467), "tonne/m**3")


def test_gas_viscosity(gas_instance, stream):
    viscosity = gas_instance.viscosity(stream)
    assert viscosity == ureg.Quantity(pytest.approx(0.0172091105), "centipoise")


def test_molar_weight(gas_instance, stream):
    mol_weight = gas_instance.molar_weight(stream)
    assert mol_weight == ureg.Quantity(pytest.approx(17.97378), "g/mol")


def test_molar_weight_from_molar_fracs(gas_instance, stream):
    molar_fracs = pd.Series([0.004, 0.9666, 0.02, 0.01],
                            index=["N2", "C1", "C2", "C3"], dtype="pint[mol/mol]")
    mol_weight = gas_instance.molar_weight_from_molar_fracs(molar_fracs)
    assert mol_weight == ureg.Quantity(pytest.approx(16.6610324), "g/mol")


def test_gas_volume_flow_rate(gas_instance, stream):
    vol_flow_rate = gas_instance.volume_flow_rate(stream)
    assert vol_flow_rate == ureg.Quantity(pytest.approx(1587.9851), "m**3/day")


def test_gas_volume_flow_rate_STP(gas_instance):
    s = Stream("test_stream", test_tp)
    s.set_flow_rate("N2", "gas", 1.0638)
    s.set_flow_rate("C1", "gas", 147.1241)
    s.set_flow_rate("C2", "gas", 5.7095)
    s.set_flow_rate("C3", "gas", 4.1863)
    vol_flow_rate_STP = gas_instance.tot_volume_flow_rate_STP(s)
    assert vol_flow_rate_STP == ureg.Quantity(pytest.approx(7.94253339), "mmscf/day")


def test_gas_mass_energy_density(gas_instance, stream):
    mass_energy_density = gas_instance.mass_energy_density(stream)
    assert mass_energy_density == ureg.Quantity(pytest.approx(46.9246768), "MJ/kg")


def test_gas_mass_energy_density_from_molar_fracs(gas_instance, stream):
    molar_fracs = pd.Series([0.004, 0.9666, 0.02, 0.01],
                            index=["N2", "C1", "C2", "C3"], dtype="pint[mol/mol]")
    mass_energy_density = gas_instance.mass_energy_density_from_molar_fracs(molar_fracs)
    assert mass_energy_density == ureg.Quantity(pytest.approx(49.7703477), "MJ/kg")


def test_combustion_enthalpy(gas_instance, stream):
    molar_fracs = pd.Series([9.2878, 2.4624, 0.0035, 0.2399],
                            index=["N2", "O2", "CO2", "H2O"], dtype="pint[mol/mol]")
    temperature = ureg.Quantity(80.33, "degF")
    enthalpy = gas_instance.combustion_enthalpy(molar_fracs, temperature)
    assert enthalpy["H2O"] == ureg.Quantity(pytest.approx(0.0), "joule/mole")


def test_volume_energy_density(gas_instance, stream):
    volume_energy_density = gas_instance.volume_energy_density(stream)
    assert volume_energy_density == ureg.Quantity(pytest.approx(959.532995), "btu/ft**3")


def test_energy_flow_rate(gas_instance, stream):
    energy_flow_rate = gas_instance.energy_flow_rate(stream)
    assert energy_flow_rate == ureg.Quantity(pytest.approx(4894.21783), "mmBtu/day")


@pytest.fixture
def water_instance(test_model):
    field = test_model.get_field("test")
    return field.water


def test_water_density(water_instance):
    density = water_instance.density()
    assert density == ureg.Quantity(pytest.approx(1004.12839, rel=1e-5), "kg/m**3")


def test_water_volume_rate(water_instance):
    stream = Stream("water stream", test_tp)
    stream.set_flow_rate("H2O", "liquid", 1962.61672)
    volume_flow_rate = water_instance.volume_flow_rate(stream)
    assert volume_flow_rate == ureg.Quantity(pytest.approx(12293.734, rel=1e-5), "bbl_water/day")


def test_water_specific_heat(water_instance):
    temperature = ureg.Quantity(200, "degF")
    specific_heat = water_instance.specific_heat(temperature)
    assert specific_heat == ureg.Quantity(pytest.approx(0.450496339), "btu/lb/degF")


def test_water_heat_capacity(water_instance):
    stream = Stream("water stream", test_tp)
    stream.set_flow_rate("H2O", "liquid", 1962.61672)
    heat_capacity = water_instance.heat_capacity(stream)
    assert heat_capacity == ureg.Quantity(pytest.approx(1949220.72), "btu/degF/day")


def test_water_saturated_temperature(water_instance):
    Psat = ureg.Quantity(1122.00, "psia")
    Tsat = water_instance.saturated_temperature(Psat)
    assert Tsat.to("degC") == ureg.Quantity(pytest.approx(292.660571), "degC")


def test_water_enthalpy_PT(water_instance):
    press = ureg.Quantity(13.7895, "bar")
    temp = ureg.Quantity(60.0, "degC")
    mass_rate = ureg.Quantity(3.94E7, "kg/day")
    enthalpy = water_instance.enthalpy_PT(press, temp, mass_rate)
    assert enthalpy == ureg.Quantity(pytest.approx(9940445.92), "MJ/day")


def test_steam_enthalpy(water_instance):
    press = ureg.Quantity(77.359177, "bar")
    steam_quality = ureg.Quantity(0.7, "frac")
    mass_rate = ureg.Quantity(5.52E7, "kg/day")
    enthalpy = water_instance.steam_enthalpy(press, steam_quality, mass_rate)
    assert enthalpy == ureg.Quantity(pytest.approx(1.28341315e+08), "MJ/day")


def test_check_balance():
    from opgee.processes.steam_generation import SteamGeneration
    from opgee.error import BalanceError

    proc = SteamGeneration("test_proc")
    input = ureg.Quantity(100.0, "tonne/day")
    output1 = ureg.Quantity(100.0001, "tonne/day")
    output2 = ureg.Quantity(110, "tonne/day")

    proc.check_balance(input, output1, "test1")

    with pytest.raises(BalanceError, match="test2 is not balanced in test_proc"):
        proc.check_balance(input, output2, "test2")
