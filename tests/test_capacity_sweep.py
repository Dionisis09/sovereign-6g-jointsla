"""The capacity extension must preserve the workload and identify known curve shapes."""
import numpy as np
import pytest
from catalyst.reused import digest
from dynamic_placement.config import Config
from dynamic_placement.workload import generate_workload
from dynamic_placement.scenario_model import extend_capacity, traffic_hash_payload
from dynamic_placement.capacity_sweep import fit_knee


def test_ten_node_prefixes_and_paired_workload():
    base = generate_workload(Config(slots=2), 7)
    ten = extend_capacity(base, 5)
    for count in (6, 7, 8, 9):
        extended = extend_capacity(base, count-5)
        assert extended.scenario.nodes == ten.scenario.nodes[:count]
        assert np.array_equal(extended.scenario.network_latency_ms, ten.scenario.network_latency_ms[:count, :count])
        assert digest(traffic_hash_payload(extended)) == digest(traffic_hash_payload(base))


def test_known_knee_is_recovered():
    x = np.arange(5, 11)
    y = 80-10*(x-5)+8*np.maximum(0, x-8)
    fit = fit_knee(x, y)
    assert fit["knee_node"] == 8 and fit["detected"]
    assert fit["slope_before"] == pytest.approx(-10)
    assert fit["slope_after"] == pytest.approx(-2)


@pytest.mark.parametrize("y", [np.repeat(20., 6), np.array([50., 45., 40., 35., 30., 25.])])
def test_flat_or_linear_curve_has_no_knee(y):
    assert fit_knee(np.arange(5, 11), y)["knee_node"] is None


def test_invalid_curve():
    with pytest.raises(ValueError):
        fit_knee([5, 7, 6, 8], [50, 40, 30, 20])
