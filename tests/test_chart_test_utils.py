"""Unit tests for the shared chart test helpers (no Helm required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from .chart_test_utils import (
    assert_matches_golden,
    get_manifest,
    index_documents,
    manifests_by_name,
)

SERVICE_DOC = """\
# Source: demo/templates/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: demo
spec:
  ports:
    - port: 80
"""

METRICS_SERVICE_DOC = """\
# Source: demo/templates/servicemonitor.yaml
apiVersion: v1
kind: Service
metadata:
  name: demo-metrics
spec:
  ports:
    - port: 9090
"""

DEPLOYMENT_DOC = """\
# Source: demo/templates/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: demo
spec:
  replicas: 1
"""


def _render(*docs: str) -> str:
    return "".join(f"---\n{doc}" for doc in docs)


def _write_golden(tmp_path: Path, content: str) -> Path:
    golden = tmp_path / "case-values.golden.yaml"
    golden.write_text(content)
    return golden


class TestIndexDocuments:
    """Behaviour of the (source, kind, name) document index."""

    def test_keys_documents_by_source_kind_and_name(self) -> None:
        """Each document is keyed by its identity triple."""
        documents = index_documents(_render(SERVICE_DOC, DEPLOYMENT_DOC))

        assert set(documents) == {
            ("demo/templates/service.yaml", "Service", "demo"),
            ("demo/templates/deployment.yaml", "Deployment", "demo"),
        }

    def test_skips_empty_and_comment_only_documents(self) -> None:
        """Blank documents and bare comments carry no manifest."""
        rendered = "---\n\n---\n# Source: demo/templates/empty.yaml\n"
        rendered += _render(SERVICE_DOC)

        assert len(index_documents(rendered)) == 1

    def test_rejects_duplicate_identities(self) -> None:
        """Two documents with the same identity indicate a chart bug."""
        with pytest.raises(AssertionError, match="Duplicate"):
            index_documents(_render(SERVICE_DOC, SERVICE_DOC))


class TestAssertMatchesGolden:
    """Order-independent byte comparison against golden files."""

    def test_identical_output_passes(self, tmp_path: Path) -> None:
        """Byte-identical render matches its golden file."""
        golden = _write_golden(tmp_path, _render(SERVICE_DOC, DEPLOYMENT_DOC))

        assert_matches_golden(_render(SERVICE_DOC, DEPLOYMENT_DOC), golden)

    def test_reordered_documents_pass(self, tmp_path: Path) -> None:
        """Document order does not affect the comparison."""
        golden = _write_golden(tmp_path, _render(SERVICE_DOC, DEPLOYMENT_DOC))

        assert_matches_golden(_render(DEPLOYMENT_DOC, SERVICE_DOC), golden)

    def test_changed_document_fails_with_diff(self, tmp_path: Path) -> None:
        """A changed document reports a unified diff for that document."""
        golden = _write_golden(tmp_path, _render(SERVICE_DOC))
        changed = SERVICE_DOC.replace("port: 80", "port: 8080")

        with pytest.raises(AssertionError) as excinfo:
            assert_matches_golden(_render(changed), golden)

        message = str(excinfo.value)
        assert "changed document: Service/demo" in message
        assert "-    - port: 80" in message
        assert "+    - port: 8080" in message

    def test_missing_and_unexpected_documents_fail(
        self, tmp_path: Path
    ) -> None:
        """Removed and added documents are reported by identity."""
        golden = _write_golden(tmp_path, _render(SERVICE_DOC, DEPLOYMENT_DOC))

        with pytest.raises(AssertionError) as excinfo:
            assert_matches_golden(
                _render(SERVICE_DOC, METRICS_SERVICE_DOC), golden
            )

        message = str(excinfo.value)
        assert "missing document: Deployment/demo" in message
        assert "unexpected document: Service/demo-metrics" in message

    def test_indentation_changes_within_document_fail(
        self, tmp_path: Path
    ) -> None:
        """Indentation stays byte-sensitive in the comparison."""
        golden = _write_golden(tmp_path, _render(SERVICE_DOC))
        reformatted = SERVICE_DOC.replace("    - port: 80", "  - port: 80")

        with pytest.raises(AssertionError, match="changed document"):
            assert_matches_golden(_render(reformatted), golden)

    def test_trailing_whitespace_is_tolerated(self, tmp_path: Path) -> None:
        """Trailing whitespace cannot survive on disk, so it is ignored.

        The trailing-whitespace pre-commit hook strips it from golden
        files, but some chart templates emit lines like ``nodeSelector: ``
        with a trailing space.
        """
        golden = _write_golden(tmp_path, _render(SERVICE_DOC))
        with_trailing = SERVICE_DOC.replace("spec:", "spec:   ")

        assert_matches_golden(_render(with_trailing), golden)


def _manifest(kind: str, name: str) -> dict:
    return {"kind": kind, "metadata": {"name": name}}


class TestGetManifest:
    """Strict kind/name manifest lookup."""

    def test_returns_single_match_by_kind(self) -> None:
        """A unique kind match is returned directly."""
        manifests = [_manifest("Service", "demo")]

        assert get_manifest(manifests, "Service")["metadata"]["name"] == "demo"

    def test_returns_match_by_kind_and_name(self) -> None:
        """name= selects between multiple manifests of one kind."""
        manifests = [
            _manifest("Service", "demo"),
            _manifest("Service", "demo-metrics"),
        ]

        manifest = get_manifest(manifests, "Service", name="demo-metrics")
        assert manifest["metadata"]["name"] == "demo-metrics"

    def test_missing_kind_raises(self) -> None:
        """No match raises with the kind in the message."""
        with pytest.raises(AssertionError, match="Service"):
            get_manifest([], "Service")

    def test_missing_name_raises(self) -> None:
        """No match for the requested name raises."""
        manifests = [_manifest("Service", "demo")]

        with pytest.raises(AssertionError, match="not found"):
            get_manifest(manifests, "Service", name="other")

    def test_ambiguous_kind_raises(self) -> None:
        """Multiple matches without name= raise instead of guessing."""
        manifests = [
            _manifest("Service", "demo"),
            _manifest("Service", "demo-metrics"),
        ]

        with pytest.raises(AssertionError, match="pass name="):
            get_manifest(manifests, "Service")


class TestManifestsByName:
    """Kind-filtered map of manifests keyed by name."""

    def test_returns_map_keyed_by_name(self) -> None:
        """All manifests of the kind are returned, keyed by name."""
        manifests = [
            _manifest("Service", "demo"),
            _manifest("Service", "demo-metrics"),
            _manifest("Deployment", "demo"),
        ]

        services = manifests_by_name(manifests, "Service")
        assert set(services) == {"demo", "demo-metrics"}

    def test_duplicate_names_raise(self) -> None:
        """Duplicate names for one kind indicate a chart bug."""
        manifests = [
            _manifest("Service", "demo"),
            _manifest("Service", "demo"),
        ]

        with pytest.raises(AssertionError, match="Duplicate"):
            manifests_by_name(manifests, "Service")
