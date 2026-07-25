"""Pod scheduling and termination tests for universal-chart."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from .chart_test_utils import render_chart
from .conftest import HelmTemplateError
from .universal_chart_test_utils import CHART, render_manifest


def _topology_constraints(
    helm_runner,
    values: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    """Render topology spread constraints from the Deployment."""

    deployment = render_manifest(
        helm_runner,
        "Deployment",
        values=values,
    )
    return deployment["spec"]["template"]["spec"].get(
        "topologySpreadConstraints",
        [],
    )


@pytest.mark.parametrize(
    ("value", "topology_key"),
    [
        pytest.param(
            {"spread_azs": True},
            "topology.kubernetes.io/zone",
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
    """Keep legacy spread toggles working without duplicate constraints."""

    constraints = _topology_constraints(helm_runner, value)

    assert any(item.get("topologyKey") == topology_key for item in constraints)
    assert (
        sum(item.get("topologyKey") == topology_key for item in constraints)
        == 1
    )


def test_spread_azs_does_not_emit_karpenter_zone(helm_runner) -> None:
    """Use the standard Kubernetes zone label for the legacy shortcut."""

    constraints = _topology_constraints(
        helm_runner,
        {"spread_azs": True},
    )

    assert all(
        item.get("topologyKey") != "karpenter.sh/zone" for item in constraints
    )


def test_spread_topology_defaults_do_not_include_extra_spreads(
    helm_runner,
) -> None:
    """Keep optional topology constraints disabled by default."""

    constraints = _topology_constraints(helm_runner)

    assert all(
        item.get("topologyKey")
        not in {"karpenter.sh/zone", "karpenter.sh/capacity-type"}
        for item in constraints
    )


@pytest.mark.parametrize("replica_count", [1, 3])
@pytest.mark.parametrize(
    ("mode", "when_unsatisfiable"),
    [
        pytest.param("preferred", "ScheduleAnyway", id="preferred"),
        pytest.param("strict", "DoNotSchedule", id="strict"),
    ],
)
def test_availability_preset_spreads_across_zones_and_nodes(
    helm_runner,
    replica_count: int,
    mode: str,
    when_unsatisfiable: str,
) -> None:
    """Render valid availability constraints for any replica count."""

    constraints = _topology_constraints(
        helm_runner,
        {
            "replicaCount": replica_count,
            "availability": {"enabled": True, "mode": mode},
        },
    )
    managed = {
        item["topologyKey"]: item
        for item in constraints
        if item["topologyKey"]
        in {"topology.kubernetes.io/zone", "kubernetes.io/hostname"}
    }

    assert set(managed) == {
        "topology.kubernetes.io/zone",
        "kubernetes.io/hostname",
    }
    for constraint in managed.values():
        assert constraint["maxSkew"] == 1
        assert constraint["whenUnsatisfiable"] == when_unsatisfiable
        assert constraint["labelSelector"] == {
            "matchLabels": {
                "app.kubernetes.io/instance": CHART.release,
                "app.kubernetes.io/name": "universal-chart",
            }
        }


def test_availability_preset_preserves_unmanaged_custom_constraint(
    helm_runner,
) -> None:
    """Keep custom topology keys and replace preset-owned duplicates."""

    constraints = _topology_constraints(
        helm_runner,
        {
            "availability": {"enabled": True, "mode": "strict"},
            "topologySpreadConstraints": [
                {
                    "maxSkew": 2,
                    "topologyKey": "topology.kubernetes.io/zone",
                    "whenUnsatisfiable": "ScheduleAnyway",
                },
                {
                    "maxSkew": 2,
                    "topologyKey": "kubernetes.io/hostname",
                    "whenUnsatisfiable": "ScheduleAnyway",
                },
                {
                    "maxSkew": 1,
                    "topologyKey": "rack.example.com/name",
                    "whenUnsatisfiable": "ScheduleAnyway",
                },
            ],
        },
    )
    by_key = {item["topologyKey"]: item for item in constraints}

    assert len(constraints) == 3
    assert by_key["topology.kubernetes.io/zone"]["whenUnsatisfiable"] == (
        "DoNotSchedule"
    )
    assert by_key["kubernetes.io/hostname"]["whenUnsatisfiable"] == (
        "DoNotSchedule"
    )
    assert by_key["rack.example.com/name"]["labelSelector"] == {
        "matchLabels": {
            "app.kubernetes.io/instance": CHART.release,
            "app.kubernetes.io/name": "universal-chart",
        }
    }


def test_custom_constraints_remain_authoritative_without_preset(
    helm_runner,
) -> None:
    """Preserve raw scheduling behavior when the preset is disabled."""

    custom_constraint = {
        "maxSkew": 3,
        "topologyKey": "topology.kubernetes.io/zone",
        "whenUnsatisfiable": "DoNotSchedule",
        "labelSelector": {"matchLabels": {"workload": "custom"}},
    }
    constraints = _topology_constraints(
        helm_runner,
        {"topologySpreadConstraints": [custom_constraint]},
    )

    assert constraints == [custom_constraint]


def test_availability_preset_preserves_custom_affinity(helm_runner) -> None:
    """Keep raw affinity rules alongside the availability preset."""

    affinity = {
        "nodeAffinity": {
            "preferredDuringSchedulingIgnoredDuringExecution": [
                {
                    "weight": 50,
                    "preference": {
                        "matchExpressions": [
                            {
                                "key": "node.example.com/pool",
                                "operator": "In",
                                "values": ["application"],
                            }
                        ]
                    },
                }
            ]
        }
    }
    deployment = render_manifest(
        helm_runner,
        "Deployment",
        values={
            "availability": {"enabled": True},
            "affinity": affinity,
        },
    )

    assert deployment["spec"]["template"]["spec"]["affinity"] == affinity


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


@pytest.mark.parametrize(
    "availability",
    [
        pytest.param(
            {"enabled": "hero", "mode": "preferred"},
            id="enabled-is-not-boolean",
        ),
        pytest.param(
            {"enabled": True, "mode": "sometimes"},
            id="mode-is-not-supported",
        ),
        pytest.param(
            {"enabled": True, "mode": "preferred", "extra": True},
            id="unknown-property",
        ),
    ],
)
def test_availability_rejects_invalid_values(
    helm_runner,
    availability: dict[str, object],
) -> None:
    """Reject malformed availability preset values."""

    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={"availability": availability},
        )
