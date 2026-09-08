"""Reject malformed NetworkPolicy values before reaching Kubernetes."""

import pytest

from .chart_test_utils import render_chart
from .conftest import HelmTemplateError
from .universal_chart_test_utils import CHART


@pytest.mark.parametrize(
    "policy",
    [
        {"enabled": "true"},
        {"enabled": 1},
        {"unknown": True},
        {"applicationIngress": {"enabled": True}},
        {"dnsEgress": {"enabled": True}},
        {"dnsEgress": {"enabled": "false"}},
        {"applicationIngress": {"from": [{}]}},
        {"dnsEgress": {"to": [{"namespace": "kube-system"}]}},
        {"ingress": [{"to": [{"podSelector": {}}]}]},
        {"egress": [{"from": [{"podSelector": {}}]}]},
        {"ingress": "allow"},
    ],
)
def test_network_policy_schema_rejects_bad_configuration(helm_runner, policy):
    """Reject wrong types, typos, empty peers, and missing helper peers."""
    with pytest.raises(HelmTemplateError):
        render_chart(helm_runner, CHART, values={"networkPolicy": policy})


@pytest.mark.parametrize(
    "direction,peer_key", [("ingress", "from"), ("egress", "to")]
)
@pytest.mark.parametrize(
    "peer",
    [
        {},
        {"ipBlock": {"cidr": "192.0.2.0/24"}, "podSelector": {}},
        {"ipBlock": {"cidr": "192.0.2.0/24"}, "namespaceSelector": {}},
        {"ipBlock": {}},
        {"ipBlock": {"cidr": ""}},
        {"ipBlock": {"cidr": "192.0.2.0/24", "except": "192.0.2.1/32"}},
        {"podSelector": {"matchLabels": {"app": 123}}},
        {"podSelector": {"matchLabel": {"app": "api"}}},
        {
            "podSelector": {
                "matchExpressions": [{"key": "app", "operator": "In"}]
            }
        },
        {
            "podSelector": {
                "matchExpressions": [{"key": "app", "operator": "Equals"}]
            }
        },
        {
            "podSelector": {
                "matchExpressions": [
                    {"key": "app", "operator": "NotIn", "values": []}
                ]
            }
        },
        {
            "podSelector": {
                "matchExpressions": [
                    {"key": "app", "operator": "Exists", "values": ["api"]}
                ]
            }
        },
    ],
)
def test_network_policy_schema_rejects_bad_peers(
    helm_runner, direction, peer_key, peer
):
    """Reject incompatible peer types and selector expressions."""
    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={
                "networkPolicy": {
                    "enabled": True,
                    direction: [{peer_key: [peer]}],
                }
            },
        )


@pytest.mark.parametrize("direction", ["ingress", "egress"])
@pytest.mark.parametrize(
    "port",
    [
        {"port": 0},
        {"port": 65536},
        {"port": "443"},
        {"port": ""},
        {"port": "UPPER"},
        {"port": "two--hyphens"},
        {"port": "name-is-too-long"},
        {"port": 443, "protocol": "ICMP"},
        {"port": "http", "endPort": 9000},
        {"endPort": 9000},
        {"port": 8000, "endPort": 65536},
        {"port": 8000, "endPort": 0},
        {"targetPort": 8000},
    ],
)
def test_network_policy_schema_rejects_bad_ports(helm_runner, direction, port):
    """Reject invalid numbers, names, protocols, and range combinations."""
    with pytest.raises(HelmTemplateError):
        render_chart(
            helm_runner,
            CHART,
            values={
                "networkPolicy": {
                    "enabled": True,
                    direction: [{"ports": [port]}],
                }
            },
        )


@pytest.mark.parametrize("direction", ["ingress", "egress"])
def test_network_policy_rejects_reversed_port_range(helm_runner, direction):
    """Helm handles the cross-field comparison that JSON Schema cannot."""
    with pytest.raises(
        HelmTemplateError, match="endPort must be greater than or equal to port"
    ):
        render_chart(
            helm_runner,
            CHART,
            values={
                "networkPolicy": {
                    "enabled": True,
                    direction: [{"ports": [{"port": 9000, "endPort": 8000}]}],
                }
            },
        )


@pytest.mark.parametrize(
    "helper,peers", [("applicationIngress", "from"), ("dnsEgress", "to")]
)
@pytest.mark.parametrize("null_peers", [False, True])
def test_network_policy_helpers_fail_closed_without_schema(
    helm_runner, helper, peers, null_peers
):
    """An empty helper list must not become unrestricted traffic."""
    values = {
        "networkPolicy.enabled": "true",
        f"networkPolicy.{helper}.enabled": "true",
    }
    if null_peers:
        values[f"networkPolicy.{helper}.{peers}"] = "null"
    with pytest.raises(
        HelmTemplateError, match="must contain at least one peer"
    ):
        helm_runner.template(
            name=CHART.release,
            chart=str(CHART.chart_dir),
            values_files=[str(CHART.default_values_file)],
            values=values,
            extra_args=["--skip-schema-validation"],
        )
