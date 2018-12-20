from unittest import mock
import pytest
from nesta.packages.geographies.uk_geography_lookup import get_gss_codes
from nesta.packages.geographies.uk_geography_lookup import get_children
from nesta.packages.geographies.uk_geography_lookup import _get_children

@pytest.fixture
def pars_for_get_children():
    return dict(base="dummy", geocodes="dummy", max_attempts=3)

@pytest.fixture
def side_effect_for_get_children():
    return ([1, 2], [2, 3], ["A", 3], ["5", 4], [])

def test_get_gss_codes():
    codes = get_gss_codes(test=True)
    assert len(codes) > 100

def test_get_children():
    x = _get_children("E04", "E08000001")
    assert len(x) > 0

@mock.patch("nesta.packages.geographies.uk_geography_lookup._get_children")
def test_get_children_max_out(mocked, pars_for_get_children):
    mocked.side_effect = ([], [], [], [], [])
    get_children(**pars_for_get_children)    
    assert mocked.call_count == pars_for_get_children["max_attempts"] + 1


@mock.patch("nesta.packages.geographies.uk_geography_lookup._get_children")
def test_get_children_totals(mocked, pars_for_get_children, side_effect_for_get_children):
    mocked.side_effect = side_effect_for_get_children
    children = get_children(**pars_for_get_children)
    assert len(children) == sum(len(x) for x in side_effect_for_get_children)

