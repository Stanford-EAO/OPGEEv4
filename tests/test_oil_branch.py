import pytest
from .utils_for_tests import load_test_model

@pytest.fixture(scope="function")
def test_oil_branch(configure_logging_for_tests):
    return load_test_model('test_oil_branch.xml')


def test_run_stab(test_oil_branch):
    analysis = test_oil_branch.get_analysis('test_oil_branch_stab')
    field = analysis.get_field('oil_stabilization')
    field.run(analysis, compute_ci=False)


def test_run_upgrading(test_oil_branch):
    analysis = test_oil_branch.get_analysis('test_oil_branch_upgrading')
    field = analysis.get_field('heavy_oil_upgrading')
    field.run(analysis, compute_ci=False)


def test_run_dilution(test_oil_branch):
    analysis = test_oil_branch.get_analysis('test_oil_branch_diluent')
    field = analysis.get_field('heavy_oil_diluent')
    field.run(analysis, compute_ci=False)


def test_run_bitumen(test_oil_branch):
    analysis = test_oil_branch.get_analysis('test_oil_branch_bitumen')
    field = analysis.get_field('bitumen_dilution')
    field.run(analysis, compute_ci=False)
