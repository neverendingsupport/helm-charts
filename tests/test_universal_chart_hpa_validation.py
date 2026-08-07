"""HorizontalPodAutoscaler validation tests for universal-chart."""

from __future__ import annotations

from typing import Any

import pytest

from .chart_test_utils import render_chart
from .conftest import HelmTemplateError
from .universal_chart_test_utils import CHART, render_manifest

CPU_UTILIZATION_METRIC = {
    "type": "Resource",
    "resource": {
        "name": "cpu",
        "target": {"type": "Utilization", "averageUtilization": 80},
    },
}


@pytest.mark.parametrize(
    ("values", "message"),
    [
        pytest.param(
            {
                "autoscaling": {
                    "horizontal": {
                        "enabled": True,
                        "metrics": [],
                        "prometheusScalingRules": [],
                    }
                }
            },
            "requires at least one metric",
            id="enabled-without-metrics",
        ),
        pytest.param(
            {
                "autoscaling": {
                    "horizontal": {
                        "enabled": True,
                        "minReplicas": 5,
                        "maxReplicas": 2,
                        "metrics": [
                            {
                                "type": "External",
                                "external": {
                                    "metric": {"name": "queue_depth"},
                                    "target": {
                                        "type": "Value",
                                        "value": "10",
                                    },
                                },
                            }
                        ],
                    }
                }
            },
            "minReplicas",
            id="minimum-exceeds-maximum",
        ),
        pytest.param(
            {
                "autoscaling": {
                    "horizontal": {
                        "enabled": True,
                        "metrics": [CPU_UTILIZATION_METRIC],
                    }
                }
            },
            "requires resources.requests.cpu",
            id="native-cpu-utilization-without-request",
        ),
        pytest.param(
            {
                "autoscaling": {
                    "horizontal": {
                        "enabled": True,
                        "metrics": [
                            {
                                "type": "ContainerResource",
                                "containerResource": {
                                    "name": "memory",
                                    "container": "universal-chart",
                                    "target": {
                                        "type": "Utilization",
                                        "averageUtilization": 70,
                                    },
                                },
                            }
                        ],
                    }
                }
            },
            "requires resources.requests.memory",
            id="container-utilization-without-request",
        ),
    ],
)
def test_horizontal_rejects_cross_field_misconfiguration(
    helm_runner,
    values: dict[str, Any],
    message: str,
) -> None:
    """Fail before creating an inert or invalid HPA."""

    with pytest.raises(HelmTemplateError, match=message):
        render_chart(helm_runner, CHART, values=values)


def test_legacy_utilization_renders_without_declared_requests(
    helm_runner,
) -> None:
    """Keep releases that predate autoscaling.horizontal renderable."""

    hpa = render_manifest(
        helm_runner,
        "HorizontalPodAutoscaler",
        values={"autoscaling": {"enabled": True, "maxReplicas": 6}},
    )

    assert hpa["spec"]["metrics"] == [CPU_UTILIZATION_METRIC]


def test_horizontal_accepts_request_from_extra_container_props(
    helm_runner,
) -> None:
    """Validate utilization against the resources rendered on the container."""

    rendered = render_chart(
        helm_runner,
        CHART,
        values={
            "extraContainerProps": {"resources": {"requests": {"cpu": "100m"}}},
            "autoscaling": {
                "horizontal": {
                    "enabled": True,
                    "metrics": [CPU_UTILIZATION_METRIC],
                }
            },
        },
    )

    assert "kind: HorizontalPodAutoscaler" in rendered


def test_horizontal_uses_extra_container_resource_precedence(
    helm_runner,
) -> None:
    """Reject a request hidden by the explicit extra-container override."""

    with pytest.raises(
        HelmTemplateError,
        match=r"requires resources\.requests\.cpu",
    ):
        render_chart(
            helm_runner,
            CHART,
            values={
                "resources": {"requests": {"cpu": "100m"}},
                "extraContainerProps": {
                    "resources": {"requests": {"memory": "128Mi"}}
                },
                "autoscaling": {
                    "horizontal": {
                        "enabled": True,
                        "metrics": [CPU_UTILIZATION_METRIC],
                    }
                },
            },
        )


@pytest.mark.parametrize(
    "values",
    [
        pytest.param(
            {
                "autoscaling": {
                    "enabled": True,
                    "hpaScalingRules": [
                        {
                            "name": "myapp_queue_depth",
                            "target": {"averageValue": "100"},
                        }
                    ],
                }
            },
            id="scaling-rule-missing-expr",
        ),
        pytest.param(
            {
                "autoscaling": {
                    "enabled": True,
                    "hpaScalingRules": [
                        {
                            "name": "myapp-queue-depth",
                            "expr": "vector(1)",
                            "target": {"averageValue": "100"},
                        }
                    ],
                }
            },
            id="invalid-metric-name",
        ),
        pytest.param(
            {
                "autoscaling": {
                    "enabled": True,
                    "hpaScalingRules": [
                        {
                            "name": "myapp_queue_depth",
                            "expr": "vector(1)",
                            "labels": {"queue": 1},
                            "target": {"averageValue": "100"},
                        }
                    ],
                }
            },
            id="scaling-rule-label-is-not-string",
        ),
        pytest.param(
            {
                "autoscaling": {
                    "enabled": True,
                    "hpaScalingRules": [
                        {
                            "name": "myapp_queue_depth",
                            "expr": "vector(1)",
                            "target": {
                                "type": "Utilization",
                                "averageValue": "100",
                            },
                        }
                    ],
                }
            },
            id="invalid-target-type",
        ),
        pytest.param(
            {
                "autoscaling": {
                    "horizontal": {
                        "annotations": {
                            "argocd.argoproj.io/sync-wave": 10,
                        }
                    }
                }
            },
            id="horizontal-annotation-is-not-string",
        ),
        pytest.param(
            {
                "autoscaling": {
                    "horizontal": {
                        "behavior": {
                            "scaleUp": {
                                "policies": [
                                    {
                                        "type": "Percent",
                                        "value": 100,
                                        "periodSeconds": 0,
                                    }
                                ]
                            }
                        }
                    }
                }
            },
            id="horizontal-behavior-period-out-of-range",
        ),
        pytest.param(
            {
                "autoscaling": {
                    "horizontal": {
                        "metrics": [
                            {
                                "type": "Resource",
                                "external": {
                                    "metric": {"name": "queue_depth"},
                                    "target": {
                                        "type": "Value",
                                        "value": "10",
                                    },
                                },
                            }
                        ]
                    }
                }
            },
            id="metric-discriminator-does-not-match-source",
        ),
        pytest.param(
            {
                "autoscaling": {
                    "horizontal": {
                        "metrics": [
                            {
                                "type": "External",
                                "external": {
                                    "metric": {"name": "queue_depth"},
                                    "target": {
                                        "type": "AverageValue",
                                        "averageValue": "not-a-quantity",
                                    },
                                },
                            }
                        ]
                    }
                }
            },
            id="native-metric-target-is-not-a-quantity",
        ),
        pytest.param(
            {
                "autoscaling": {
                    "horizontal": {
                        "behavior": {"scaleUp": {"tolerance": "not-a-quantity"}}
                    }
                }
            },
            id="behavior-tolerance-is-not-a-quantity",
        ),
        pytest.param(
            {
                "autoscaling": {
                    "hpaScalingRules": [
                        {
                            "name": "myapp_queue_depth",
                            "expr": "vector(1)",
                            "target": {"averageValue": "not-a-quantity"},
                        }
                    ]
                }
            },
            id="legacy-prometheus-target-is-not-a-quantity",
        ),
    ],
)
def test_hpa_schema_rejects_invalid_values(
    helm_runner,
    values: dict[str, Any],
) -> None:
    """Reject malformed HPA values before template rendering."""

    with pytest.raises(HelmTemplateError):
        render_chart(helm_runner, CHART, values=values)
