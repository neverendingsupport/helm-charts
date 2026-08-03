"""PodDisruptionBudget tests for the universal chart."""

from __future__ import annotations

from typing import Any

import pytest

from .chart_test_utils import get_manifest, load_manifests, render_chart
from .conftest import HelmTemplateError
from .universal_chart_test_utils import CHART


def _pdb_values(
    *,
    replica_count: int = 2,
    autoscaling_min: int | None = None,
    min_available: int | str | None = None,
    max_unavailable: int | str | None = None,
    allow_zero: bool = False,
) -> dict[str, Any]:
    """Build chart values for a focused PDB test."""

    budget: dict[str, object] = {"enabled": True}
    if min_available is not None:
        budget["minAvailable"] = min_available
    if max_unavailable is not None:
        budget["maxUnavailable"] = max_unavailable
    if allow_zero:
        budget["allowZeroDisruptions"] = True

    values: dict[str, Any] = {
        "replicaCount": replica_count,
        "podDisruptionBudget": budget,
    }
    if autoscaling_min is not None:
        values["autoscaling"] = {
            "enabled": True,
            "minReplicas": autoscaling_min,
        }
        values["resources"] = {"requests": {"cpu": "100m"}}
    return values


def test_pod_disruption_budget_renders_when_enabled(helm_runner) -> None:
    """Ensure a PodDisruptionBudget is rendered with selector labels."""

    values = _pdb_values(min_available="50%")
    values["podDisruptionBudget"]["annotations"] = {
        "argocd.argoproj.io/sync-wave": "10"
    }
    rendered = render_chart(helm_runner, CHART, values=values)
    pdb = get_manifest(load_manifests(rendered), "PodDisruptionBudget")

    assert pdb["metadata"]["name"] == CHART.release
    assert pdb["metadata"]["annotations"] == {
        "argocd.argoproj.io/sync-wave": "10"
    }
    assert pdb["spec"]["minAvailable"] == "50%"
    assert "maxUnavailable" not in pdb["spec"]
    assert pdb["spec"]["selector"]["matchLabels"] == {
        "app.kubernetes.io/name": CHART.release,
        "app.kubernetes.io/instance": CHART.release,
    }


def test_pod_disruption_budget_renders_max_unavailable(helm_runner) -> None:
    """Ensure an integer maxUnavailable budget renders."""

    values = _pdb_values(max_unavailable=1)
    values["podDisruptionBudget"]["unhealthyPodEvictionPolicy"] = "AlwaysAllow"
    rendered = render_chart(helm_runner, CHART, values=values)
    pdb = get_manifest(load_manifests(rendered), "PodDisruptionBudget")

    assert pdb["spec"]["maxUnavailable"] == 1
    assert "minAvailable" not in pdb["spec"]
    assert pdb["spec"]["unhealthyPodEvictionPolicy"] == "AlwaysAllow"


@pytest.mark.parametrize(
    "values",
    [
        pytest.param(
            _pdb_values(min_available=1, max_unavailable="25%"),
            id="both-limits",
        ),
        pytest.param(_pdb_values(), id="neither-limit"),
    ],
)
def test_pod_disruption_budget_requires_exactly_one_limit(
    helm_runner,
    values,
) -> None:
    """Ensure the budget has exactly one availability limit."""

    with pytest.raises(
        HelmTemplateError,
        match="exactly one of minAvailable or maxUnavailable",
    ):
        render_chart(helm_runner, CHART, values=values)


@pytest.mark.parametrize(
    ("values", "error"),
    [
        pytest.param(
            _pdb_values(min_available=3),
            "effective replica minimum is 2",
            id="static-minimum-exceeds-replicas",
        ),
        pytest.param(
            _pdb_values(
                replica_count=5,
                autoscaling_min=2,
                min_available=3,
            ),
            "effective replica minimum is 2",
            id="minimum-exceeds-hpa-floor",
        ),
        pytest.param(
            _pdb_values(
                min_available=3,
                allow_zero=True,
            ),
            "effective replica minimum is 2",
            id="escape-hatch-does-not-allow-impossible-minimum",
        ),
        pytest.param(
            _pdb_values(min_available="101%"),
            "must be between 0% and 100%",
            id="minimum-percentage-exceeds-100",
        ),
        pytest.param(
            _pdb_values(max_unavailable="101%"),
            "must be between 0% and 100%",
            id="maximum-percentage-exceeds-100",
        ),
    ],
)
def test_pod_disruption_budget_rejects_impossible_limits(
    helm_runner,
    values,
    error,
) -> None:
    """Ensure impossible replica requirements fail before installation."""

    with pytest.raises(HelmTemplateError, match=error):
        render_chart(helm_runner, CHART, values=values)


@pytest.mark.parametrize(
    "values",
    [
        pytest.param(
            _pdb_values(min_available="half"),
            id="minimum-is-not-a-percent",
        ),
        pytest.param(
            _pdb_values(max_unavailable="25"),
            id="maximum-string-omits-percent-sign",
        ),
    ],
)
def test_pod_disruption_budget_rejects_malformed_percentages(
    helm_runner,
    values,
) -> None:
    """Ensure string limits use Kubernetes percentage syntax."""

    with pytest.raises(HelmTemplateError, match="does not match pattern"):
        render_chart(helm_runner, CHART, values=values)


@pytest.mark.parametrize(
    "values",
    [
        pytest.param(
            _pdb_values(replica_count=1, min_available=1),
            id="single-replica-minimum",
        ),
        pytest.param(
            _pdb_values(min_available=2),
            id="minimum-equals-static-replicas",
        ),
        pytest.param(
            _pdb_values(
                replica_count=5,
                autoscaling_min=2,
                min_available=2,
            ),
            id="minimum-equals-hpa-floor",
        ),
        pytest.param(
            _pdb_values(min_available="75%"),
            id="rounded-percentage-requires-every-replica",
        ),
        pytest.param(
            _pdb_values(min_available="100%"),
            id="minimum-is-100-percent",
        ),
        pytest.param(
            _pdb_values(max_unavailable=0),
            id="maximum-is-zero",
        ),
        pytest.param(
            _pdb_values(max_unavailable="0%"),
            id="maximum-is-zero-percent",
        ),
    ],
)
def test_pod_disruption_budget_rejects_zero_disruptions_without_opt_in(
    helm_runner,
    values,
) -> None:
    """Ensure a drain-blocking budget requires an explicit opt-in."""

    with pytest.raises(
        HelmTemplateError,
        match="allowZeroDisruptions=true",
    ):
        render_chart(helm_runner, CHART, values=values)


@pytest.mark.parametrize(
    ("values", "expected_field", "expected_value"),
    [
        pytest.param(
            _pdb_values(replica_count=1, max_unavailable=1),
            "maxUnavailable",
            1,
            id="single-replica-allows-one-disruption",
        ),
        pytest.param(
            _pdb_values(min_available=0),
            "minAvailable",
            0,
            id="zero-minimum-allows-disruptions",
        ),
        pytest.param(
            _pdb_values(min_available=2, allow_zero=True),
            "minAvailable",
            2,
            id="static-equality-with-opt-in",
        ),
        pytest.param(
            _pdb_values(
                replica_count=5,
                autoscaling_min=2,
                min_available=2,
                allow_zero=True,
            ),
            "minAvailable",
            2,
            id="hpa-equality-with-opt-in",
        ),
        pytest.param(
            _pdb_values(min_available="75%", allow_zero=True),
            "minAvailable",
            "75%",
            id="rounded-percentage-with-opt-in",
        ),
        pytest.param(
            _pdb_values(min_available="100%", allow_zero=True),
            "minAvailable",
            "100%",
            id="100-percent-minimum-with-opt-in",
        ),
        pytest.param(
            _pdb_values(max_unavailable=0, allow_zero=True),
            "maxUnavailable",
            0,
            id="zero-maximum-with-opt-in",
        ),
        pytest.param(
            _pdb_values(max_unavailable="0%", allow_zero=True),
            "maxUnavailable",
            "0%",
            id="zero-percent-maximum-with-opt-in",
        ),
    ],
)
def test_pod_disruption_budget_allows_safe_and_explicit_limits(
    helm_runner,
    values,
    expected_field,
    expected_value,
) -> None:
    """Ensure safe limits and acknowledged zero-disruption limits render."""

    rendered = render_chart(helm_runner, CHART, values=values)
    pdb = get_manifest(load_manifests(rendered), "PodDisruptionBudget")

    assert pdb["spec"][expected_field] == expected_value


def test_pod_disruption_budget_uses_autoscaling_min_replicas(
    helm_runner,
) -> None:
    """Ensure autoscaling.minReplicas gates the PDB when autoscaling is on."""

    values = _pdb_values(
        replica_count=1,
        autoscaling_min=2,
        min_available=1,
    )
    rendered = render_chart(helm_runner, CHART, values=values)
    pdb = get_manifest(load_manifests(rendered), "PodDisruptionBudget")

    assert pdb["spec"]["minAvailable"] == 1


def test_pod_disruption_budget_uses_horizontal_min_replicas(
    helm_runner,
) -> None:
    """Use the preferred horizontal minimum for disruption validation."""

    values = {
        "replicaCount": 1,
        "podDisruptionBudget": {
            "enabled": True,
            "minAvailable": 2,
            "allowZeroDisruptions": True,
        },
        "autoscaling": {
            "minReplicas": 1,
            "horizontal": {
                "enabled": True,
                "minReplicas": 2,
                "metrics": [
                    {
                        "type": "External",
                        "external": {
                            "metric": {"name": "queue_depth"},
                            "target": {"type": "Value", "value": "10"},
                        },
                    }
                ],
            },
        },
    }
    rendered = render_chart(helm_runner, CHART, values=values)
    pdb = get_manifest(load_manifests(rendered), "PodDisruptionBudget")

    assert pdb["spec"]["minAvailable"] == 2


def test_pod_disruption_budget_is_not_rendered_when_disabled(
    helm_runner,
) -> None:
    """Ensure the PodDisruptionBudget is omitted when disabled."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={"podDisruptionBudget": {"enabled": False}},
    )
    manifests = load_manifests(rendered)

    assert all(
        manifest.get("kind") != "PodDisruptionBudget" for manifest in manifests
    )
