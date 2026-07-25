"""Pod scheduling and termination tests for universal-chart."""

from __future__ import annotations

import pytest

from .chart_test_utils import render_chart
from .conftest import HelmTemplateError
from .universal_chart_test_utils import CHART, render_manifest


@pytest.mark.parametrize(
    ("value", "topology_key"),
    [
        pytest.param(
            {"spread_azs": True},
            "karpenter.sh/zone",
            id="availability-zone",
        ),
        pytest.param(
            {"spread_spot": True},
            "karpenter.sh/capacity-type",
            id="capacity-type",
        ),
    ],
)
def test_spread_toggle_appends_topology_constraint(
    helm_runner,
    value: dict[str, bool],
    topology_key: str,
) -> None:
    """Add the requested topology spread constraint."""

    deployment = render_manifest(
        helm_runner,
        "Deployment",
        values=value,
    )
    constraints = deployment["spec"]["template"]["spec"].get(
        "topologySpreadConstraints",
        [],
    )

    assert any(item.get("topologyKey") == topology_key for item in constraints)


def test_spread_topology_defaults_do_not_include_extra_spreads(
    helm_runner,
) -> None:
    """Keep optional topology constraints disabled by default."""

    deployment = render_manifest(helm_runner, "Deployment")
    constraints = deployment["spec"]["template"]["spec"].get(
        "topologySpreadConstraints",
        [],
    )

    assert all(
        item.get("topologyKey")
        not in {"karpenter.sh/zone", "karpenter.sh/capacity-type"}
        for item in constraints
    )


def test_termination_grace_period_is_omitted_when_null(helm_runner) -> None:
    """Omit terminationGracePeriodSeconds when it is null."""

    deployment = render_manifest(helm_runner, "Deployment")
    pod_spec = deployment["spec"]["template"]["spec"]

    assert "terminationGracePeriodSeconds" not in pod_spec


@pytest.mark.parametrize("seconds", [0, 1, 120])
def test_termination_grace_period_renders(
    helm_runner,
    seconds: int,
) -> None:
    """Render valid termination grace periods, including zero."""

    deployment = render_manifest(
        helm_runner,
        "Deployment",
        values={"terminationGracePeriodSeconds": seconds},
    )

    assert (
        deployment["spec"]["template"]["spec"]["terminationGracePeriodSeconds"]
        == seconds
    )


def test_termination_grace_period_rejects_out_of_range(helm_runner) -> None:
    """Reject termination grace periods above the schema maximum."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={"terminationGracePeriodSeconds": 1000},
        )


def test_spread_values_reject_invalid_booleans(helm_runner) -> None:
    """Reject non-boolean values for either spread option."""

    for key in ("spread_azs", "spread_spot"):
        with pytest.raises(HelmTemplateError):
            render_chart(helm_runner, CHART, values={key: "hero"})
