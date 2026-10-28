"""NetworkPolicy directions, metadata, and opt-in peer defaults."""

import json

import pytest

from .chart_test_utils import get_manifest
from .conftest import HelmTemplateError
from .universal_chart_test_utils import CHART, render_manifest, render_manifests

MONITORING = [{"namespaceSelector": {"matchLabels": {"team": "monitoring"}}}]


@pytest.mark.parametrize(
    "types", [["Ingress"], ["Egress"], ["Egress", "Ingress"]]
)
def test_policy_types_only_render_selected_directions(helm_runner, types):
    """An excluded direction must not accidentally become isolated."""
    spec = render_manifest(
        helm_runner,
        "NetworkPolicy",
        values={"networkPolicy": {"enabled": True, "policyTypes": types}},
    )["spec"]
    assert spec["policyTypes"] == types
    for direction in ("Ingress", "Egress"):
        assert (direction.lower() in spec) == (direction in types)
        if direction in types:
            assert spec[direction.lower()] == []


@pytest.mark.parametrize(
    "types,configuration,direction",
    [
        (["Ingress"], {"egress": [{}]}, "Egress"),
        (["Ingress"], {"dnsEgress": {"enabled": True}}, "Egress"),
        (["Egress"], {"ingress": [{}]}, "Ingress"),
        (["Egress"], {"applicationIngress": {"enabled": True}}, "Ingress"),
        (
            ["Egress"],
            {"metricsIngress": {"enabled": True, "from": MONITORING}},
            "Ingress",
        ),
    ],
)
@pytest.mark.parametrize("skip_schema", [False, True])
def test_excluded_direction_rejects_rules_and_helpers(
    helm_runner, types, configuration, direction, skip_schema
):
    """Reject conflicting intent even if the caller skips schema validation."""
    policy = {"enabled": True, "policyTypes": types, **configuration}
    with pytest.raises(HelmTemplateError, match=f"must include {direction}"):
        helm_runner.template(
            name=CHART.release,
            chart=str(CHART.chart_dir),
            values_files=[str(CHART.default_values_file)],
            values={"serviceMonitor.enabled": "true"},
            extra_args=["--set-json", f"networkPolicy={json.dumps(policy)}"]
            + (["--skip-schema-validation"] if skip_schema else []),
        )


def test_policy_metadata_does_not_change_pod_selection(helm_runner):
    """Preserve chart labels and keep extra metadata off the pod selector."""
    docs = render_manifests(
        helm_runner,
        values={
            "networkPolicy": {
                "enabled": True,
                "labels": {
                    "team": "platform",
                    "app.kubernetes.io/name": "wrong",
                },
                "annotations": {"example.com/owner": "platform"},
            }
        },
    )
    policy = get_manifest(docs, "NetworkPolicy")
    deployment = get_manifest(docs, "Deployment")
    assert policy["metadata"]["labels"] == {
        **deployment["metadata"]["labels"],
        "team": "platform",
    }
    assert policy["metadata"]["annotations"] == {
        "example.com/owner": "platform"
    }
    assert policy["spec"]["podSelector"] == deployment["spec"]["selector"]


@pytest.mark.parametrize(
    "helper,peer_key,direction,namespace,pod_labels",
    [
        (
            "applicationIngress",
            "from",
            "ingress",
            "ingress-nginx",
            {"app.kubernetes.io/component": "controller"},
        ),
        ("dnsEgress", "to", "egress", "kube-system", {"k8s-app": "kube-dns"}),
    ],
)
def test_helper_defaults_are_replaceable(
    helm_runner, helper, peer_key, direction, namespace, pod_labels
):
    """Custom peers replace defaults without gaining hidden access."""
    expected = [
        {
            "namespaceSelector": {
                "matchLabels": {"kubernetes.io/metadata.name": namespace}
            },
            "podSelector": {"matchLabels": pod_labels},
        }
    ]
    for peers in (None, MONITORING):
        options = {"enabled": True}
        if peers is not None:
            options[peer_key] = peers
        spec = render_manifest(
            helm_runner,
            "NetworkPolicy",
            values={"networkPolicy": {"enabled": True, helper: options}},
        )["spec"]
        assert spec[direction][0][peer_key] == (
            expected if peers is None else peers
        )


@pytest.mark.parametrize("alternate_port", [None, 9090])
@pytest.mark.parametrize("enabled", [False, True])
def test_metrics_ingress_requires_opt_in_and_uses_target(
    helm_runner, alternate_port, enabled
):
    """Enabling ServiceMonitor alone never grants access to scrapers."""
    spec = render_manifest(
        helm_runner,
        "NetworkPolicy",
        values={
            "serviceMonitor": {
                "enabled": True,
                "alternatePort": alternate_port,
            },
            "networkPolicy": {
                "enabled": True,
                "policyTypes": ["Ingress"],
                "metricsIngress": {"enabled": enabled, "from": MONITORING},
            },
        },
    )["spec"]
    assert spec["ingress"] == (
        [
            {
                "from": MONITORING,
                "ports": [
                    {"port": alternate_port or "http", "protocol": "TCP"}
                ],
            }
        ]
        if enabled
        else []
    )


def test_metrics_ingress_requires_service_monitor(helm_runner):
    """Reject a metrics helper with no enabled scrape configuration."""
    with pytest.raises(
        HelmTemplateError, match="requires serviceMonitor.enabled"
    ):
        render_manifest(
            helm_runner,
            "NetworkPolicy",
            values={
                "networkPolicy": {
                    "enabled": True,
                    "metricsIngress": {"enabled": True, "from": MONITORING},
                }
            },
        )


def test_api_access_requires_explicit_native_egress(helm_runner):
    """Grant only the operator-supplied API destination and port."""
    rule = {
        "to": [{"ipBlock": {"cidr": "192.0.2.20/32"}}],
        "ports": [{"port": 443, "protocol": "TCP"}],
    }
    for rules in ([], [rule]):
        spec = render_manifest(
            helm_runner,
            "NetworkPolicy",
            values={
                "networkPolicy": {
                    "enabled": True,
                    "policyTypes": ["Egress"],
                    "egress": rules,
                }
            },
        )["spec"]
        assert spec["egress"] == rules
