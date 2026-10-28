"""Opt-in NetworkPolicy rendering and native rule preservation."""

from __future__ import annotations

import re

import pytest
import yaml

from .chart_test_utils import get_manifest
from .universal_chart_test_utils import CHART, render_manifest, render_manifests

PEERS = [{"namespaceSelector": {"matchLabels": {"purpose": "platform"}}}]


@pytest.mark.parametrize("policy", [{}, {"enabled": False}, None])
def test_disabled_network_policy_preserves_manifests(helm_runner, policy):
    """Defaults, explicit disable, and old releases leave networking alone."""
    baseline = render_manifests(helm_runner)
    assert not any(doc["kind"] == "NetworkPolicy" for doc in baseline)
    assert (
        render_manifests(helm_runner, values={"networkPolicy": policy})
        == baseline
    )


def test_network_policy_selects_only_application_pods(helm_runner):
    """Use the Deployment selector and isolate both directions by default."""
    docs = render_manifests(
        helm_runner,
        values={"networkPolicy.enabled": True, "nameOverride": "custom"},
    )
    policy = get_manifest(docs, "NetworkPolicy")
    deployment = get_manifest(docs, "Deployment")
    assert policy["apiVersion"] == "networking.k8s.io/v1"
    assert policy["metadata"]["name"] == deployment["metadata"]["name"]
    assert policy["metadata"]["labels"] == deployment["metadata"]["labels"]
    assert policy["spec"] == {
        "podSelector": deployment["spec"]["selector"],
        "policyTypes": ["Ingress", "Egress"],
        "ingress": [],
        "egress": [],
    }


@pytest.mark.parametrize("application", [False, True])
@pytest.mark.parametrize("dns", [False, True])
def test_network_policy_helpers_are_independent(helm_runner, application, dns):
    """Helpers preserve peer boundaries and don't enable one another."""
    spec = render_manifest(
        helm_runner,
        "NetworkPolicy",
        values={
            "networkPolicy": {
                "enabled": True,
                "applicationIngress": {"enabled": application, "from": PEERS},
                "dnsEgress": {"enabled": dns, "to": PEERS},
            }
        },
    )["spec"]
    assert spec["ingress"] == (
        [{"from": PEERS, "ports": [{"port": "http", "protocol": "TCP"}]}]
        if application
        else []
    )
    assert spec["egress"] == (
        [
            {
                "to": PEERS,
                "ports": [
                    {"port": 53, "protocol": "UDP"},
                    {"port": 53, "protocol": "TCP"},
                ],
            }
        ]
        if dns
        else []
    )


def test_application_ingress_uses_service_targets(helm_runner):
    """Use target ports, preserve protocols, and exclude separate metrics."""
    spec = render_manifest(
        helm_runner,
        "NetworkPolicy",
        values={
            "networkPolicy.enabled": True,
            "networkPolicy.applicationIngress": {
                "enabled": True,
                "from": PEERS,
            },
            "service.port": 8080,
            "service.extraPorts": [
                {"name": "grpc", "port": 443, "targetPort": 50051},
                {"name": "named", "port": 8081, "targetPort": "admin"},
                {"name": "udp", "port": 8125, "protocol": "UDP"},
                {"name": "sctp", "port": 9000, "protocol": "SCTP"},
                {"name": "null-target", "port": 8000, "targetPort": None},
                {"name": "numeric-string", "port": 8001, "targetPort": "8002"},
            ],
            "serviceMonitor.alternatePort": 9090,
        },
    )["spec"]
    assert spec["ingress"][0]["ports"] == [
        {"port": "http", "protocol": "TCP"},
        {"port": 50051, "protocol": "TCP"},
        {"port": "admin", "protocol": "TCP"},
        {"port": 8125, "protocol": "UDP"},
        {"port": 9000, "protocol": "SCTP"},
        {"port": 8000, "protocol": "TCP"},
        {"port": 8002, "protocol": "TCP"},
    ]


@pytest.mark.parametrize(
    "direction,peer_key", [("ingress", "from"), ("egress", "to")]
)
def test_native_rules_survive_with_helpers(helm_runner, direction, peer_key):
    """Preserve native peer logic, CIDRs, ranges, and explicit allow-all."""
    rules = [
        {
            peer_key: [
                {
                    "namespaceSelector": {},
                    "podSelector": {
                        "matchExpressions": [
                            {"key": "app", "operator": "In", "values": ["api"]},
                            {"key": "blocked", "operator": "DoesNotExist"},
                        ]
                    },
                },
                {"podSelector": {}},
                {
                    "ipBlock": {
                        "cidr": "2001:db8::/32",
                        "except": ["2001:db8:1::/48"],
                    }
                },
            ],
            "ports": [
                {"port": 8000, "endPort": 8100},
                {"port": 53, "endPort": 53, "protocol": "UDP"},
                {"port": "grpc"},
                {"protocol": "SCTP"},
            ],
        },
        {peer_key: [], "ports": []},
        {},
    ]
    policy = render_manifest(
        helm_runner,
        "NetworkPolicy",
        values={
            "networkPolicy": {
                "enabled": True,
                "applicationIngress": {"enabled": True, "from": PEERS},
                "dnsEgress": {"enabled": True, "to": PEERS},
                direction: rules,
            }
        },
    )
    assert policy["spec"][direction][1:] == rules


def test_network_policy_guide_example_matches_fixture():
    """Keep the copyable example and golden-tested input together."""
    guide = (CHART.chart_dir / "docs/network-policy.md").read_text()
    example = re.findall(r"```yaml\n(.*?)```", guide, re.DOTALL)[0]
    fixture = CHART.fixtures_dir / "network-policy-values.yaml"
    assert yaml.safe_load(example) == yaml.safe_load(fixture.read_text())


@pytest.mark.parametrize(
    "expression",
    [
        {"key": "app", "operator": "In", "values": ["api"]},
        {"key": "app", "operator": "NotIn", "values": ["api"]},
        {"key": "app", "operator": "Exists", "values": []},
        {"key": "app", "operator": "DoesNotExist"},
    ],
)
def test_network_policy_accepts_selector_operators(helm_runner, expression):
    """Accept each native operator with its valid values combination."""
    rule = {"from": [{"podSelector": {"matchExpressions": [expression]}}]}
    policy = render_manifest(
        helm_runner,
        "NetworkPolicy",
        values={"networkPolicy": {"enabled": True, "ingress": [rule]}},
    )
    assert policy["spec"]["ingress"] == [rule]


@pytest.mark.parametrize("port", [1, 65535, "a", "1a", "a-b", "a" * 15])
def test_network_policy_accepts_port_boundaries(helm_runner, port):
    """Keep the edges of the numeric and named port ranges available."""
    rule = {"ports": [{"port": port}]}
    policy = render_manifest(
        helm_runner,
        "NetworkPolicy",
        values={"networkPolicy": {"enabled": True, "egress": [rule]}},
    )
    assert policy["spec"]["egress"] == [rule]


@pytest.mark.parametrize(
    "target", ["8002", "0x10", "010", "1e3", "admin", "null", "~", "0"]
)
def test_network_policy_matches_legacy_service_scalar(helm_runner, target):
    """Preserve the Service's existing YAML interpretation of string targets."""
    docs = render_manifests(
        helm_runner,
        values={
            "networkPolicy.enabled": True,
            "networkPolicy.applicationIngress": {
                "enabled": True,
                "from": PEERS,
            },
            "service.extraPorts": [
                {"name": "extra", "port": 8081, "targetPort": target}
            ],
        },
    )
    service_port = get_manifest(docs, "Service")["spec"]["ports"][1]
    service_target = service_port["targetPort"] or service_port["port"]
    policy_target = get_manifest(docs, "NetworkPolicy")["spec"]["ingress"][0][
        "ports"
    ][1]["port"]
    assert policy_target == service_target
    assert type(policy_target) is type(service_target)
