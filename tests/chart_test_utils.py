"""Shared helpers for chart-based pytest suites."""

from __future__ import annotations

import difflib
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping

import yaml

if TYPE_CHECKING:  # pragma: no cover - import only for typing
    from pytest_helm_charts.giantswarm.helm import HelmRunner

REPO_ROOT = Path(__file__).resolve().parents[1]
CHARTS_DIR = REPO_ROOT / "charts"
FIXTURES_ROOT = REPO_ROOT / "tests" / "fixtures"


@dataclass(frozen=True)
class ChartContext:
    """Metadata about a chart under test."""

    chart_name: str
    release_name: str | None = None

    @property
    def chart_dir(self) -> Path:
        """Return the path to the chart directory under test."""
        return CHARTS_DIR / self.chart_name

    @property
    def fixtures_dir(self) -> Path:
        """Return the path to this chart's test fixtures directory."""
        return FIXTURES_ROOT / self.chart_name

    @property
    def default_values_file(self) -> Path:
        """Return the default values file used in most tests."""
        return self.fixtures_dir / "minimal-values.yaml"

    @property
    def release(self) -> str:
        """Return the Helm release name used when rendering."""
        return self.release_name or self.chart_name


def _merge_nested(target: dict[str, Any], dotted_key: str, value: Any) -> None:
    """Insert a dotted key into the target mapping as nested dictionaries."""

    parts = dotted_key.split(".")
    current: dict[str, Any] = target

    for segment in parts[:-1]:
        existing = current.get(segment)
        if isinstance(existing, dict):
            current = existing
        else:
            nested: dict[str, Any] = {}
            current[segment] = nested
            current = nested

    last = parts[-1]
    existing = current.get(last)
    if isinstance(existing, dict) and isinstance(value, Mapping):
        merged = existing.copy()
        merged.update(value)
        current[last] = merged
    else:
        current[last] = value


def _prepare_values(values: Mapping[str, Any]) -> dict[str, Any]:
    """Expand dotted keys into nested mappings before writing to disk."""

    prepared: dict[str, Any] = {}
    for key, value in values.items():
        if "." in key:
            _merge_nested(prepared, key, value)
        elif (
            key in prepared
            and isinstance(prepared[key], dict)
            and isinstance(value, Mapping)
        ):
            merged = prepared[key].copy()
            merged.update(value)
            prepared[key] = merged
        else:
            prepared[key] = value
    return prepared


def render_chart(
    helm_runner: "HelmRunner",
    chart: ChartContext,
    *,
    values_files: Iterable[Path] | None = None,
    values: Mapping[str, Any] | None = None,
) -> str:
    """Render the requested chart and return the YAML output."""

    temp_values_file: Path | None = None
    try:
        files = list(values_files or (chart.default_values_file,))

        if values:
            prepared_values = _prepare_values(dict(values))
            with tempfile.NamedTemporaryFile(
                "w", suffix=".yaml", delete=False
            ) as handle:
                yaml.safe_dump(prepared_values, handle)
                temp_values_file = Path(handle.name)
            files.append(temp_values_file)

        str_files = [str(path) for path in files]
        return helm_runner.template(
            name=chart.release,
            chart=str(chart.chart_dir),
            values_files=str_files,
        )
    finally:
        if temp_values_file:
            temp_values_file.unlink(missing_ok=True)


_SOURCE_RE = re.compile(r"^# Source: (?P<source>\S+)$", re.MULTILINE)


def _normalize_document(chunk: str) -> str:
    """Canonicalize a document for comparison.

    Trailing whitespace is stripped from each line because the
    ``trailing-whitespace`` pre-commit hook strips it from golden files,
    so it can never survive on disk. Some (notably vendored) chart
    templates emit lines like ``nodeSelector: `` with a trailing space,
    which would otherwise make a byte-exact match impossible. Indentation
    and content remain byte-sensitive.
    """

    return "\n".join(line.rstrip() for line in chunk.splitlines())


def _document_key(chunk: str) -> tuple[str | None, str | None, str | None]:
    """Derive the identity key for a rendered manifest document."""

    source_match = _SOURCE_RE.search(chunk)
    source = source_match.group("source") if source_match else None
    try:
        document = yaml.safe_load(chunk)
    except yaml.YAMLError as exc:
        raise AssertionError(
            f"Unparseable manifest document (source={source}): {exc}"
        ) from exc
    if not isinstance(document, dict):
        # Comment-only or empty documents carry no manifest.
        return (source, None, None)
    kind = document.get("kind")
    metadata = document.get("metadata") or {}
    name = metadata.get("name") if isinstance(metadata, Mapping) else None
    return (source, kind, name)


def index_documents(
    rendered: str,
) -> dict[tuple[str | None, str | None, str | None], str]:
    """Split Helm output into raw documents keyed by identity.

    Documents are keyed by (source template, kind, metadata.name) so
    comparisons do not depend on the order Helm renders templates in.
    The values are the document text with per-line trailing whitespace
    normalized (see ``_normalize_document``); indentation and content
    stay byte-sensitive.
    """

    documents: dict[tuple[str | None, str | None, str | None], str] = {}
    for chunk in re.split(r"^---$", rendered, flags=re.MULTILINE):
        # Normalize first so trailing whitespace cannot affect the
        # identity key (e.g. an anchored match on the "# Source:" line).
        chunk = _normalize_document(chunk).strip()
        if not chunk:
            continue
        key = _document_key(chunk)
        if key[1] is None and key[2] is None:
            # No manifest content (e.g. a bare "# Source:" comment).
            continue
        if key in documents:
            raise AssertionError(
                f"Duplicate manifest identity {_describe_key(key)}"
            )
        documents[key] = chunk
    return documents


def _describe_key(key: tuple[str | None, str | None, str | None]) -> str:
    """Render a document identity key for failure messages."""

    source, kind, name = key
    return f"{kind or '<no kind>'}/{name or '<no name>'} (source={source})"


def _sortable_key(
    key: tuple[str | None, str | None, str | None],
) -> tuple[str, str, str]:
    return tuple(part or "" for part in key)  # type: ignore[return-value]


def assert_matches_golden(rendered: str, golden_file: Path) -> None:
    """Compare rendered output to a stored golden manifest.

    The comparison is order-independent: documents are matched by
    (source template, kind, name) identity, then compared byte-for-byte.
    Failures report missing/unexpected documents and a unified diff for
    each changed document instead of one positional diff of the full
    output.
    """

    expected = index_documents(golden_file.read_text())
    actual = index_documents(rendered)

    errors: list[str] = []
    for key in sorted(expected.keys() - actual.keys(), key=_sortable_key):
        errors.append(f"missing document: {_describe_key(key)}")
    for key in sorted(actual.keys() - expected.keys(), key=_sortable_key):
        errors.append(f"unexpected document: {_describe_key(key)}")
    for key in sorted(expected.keys() & actual.keys(), key=_sortable_key):
        if expected[key] == actual[key]:
            continue
        diff = "\n".join(
            difflib.unified_diff(
                expected[key].splitlines(),
                actual[key].splitlines(),
                fromfile=f"golden {_describe_key(key)}",
                tofile=f"rendered {_describe_key(key)}",
                lineterm="",
            )
        )
        errors.append(f"changed document: {_describe_key(key)}\n{diff}")

    if errors:
        raise AssertionError(
            f"Rendered output does not match {golden_file}:\n"
            + "\n".join(errors)
        )


def load_manifests(rendered: str) -> list[dict[str, Any]]:
    """Convert Helm output into a list of manifest dictionaries."""

    documents = yaml.safe_load_all(rendered)
    return [doc for doc in documents if doc]


def _manifest_name(manifest: Mapping[str, Any]) -> str | None:
    """Return metadata.name for a manifest, if present."""

    metadata = manifest.get("metadata") or {}
    if isinstance(metadata, Mapping):
        return metadata.get("name")
    return None


def get_manifest(
    manifests: list[dict[str, Any]], kind: str, name: str | None = None
) -> dict[str, Any]:
    """Return the single manifest matching the kind (and optional name).

    Raises when no manifest matches, or when the kind alone is ambiguous
    (multiple matches) and no name was given.
    """

    matches = [m for m in manifests if m.get("kind") == kind]
    if name is not None:
        matches = [m for m in matches if _manifest_name(m) == name]

    wanted = f"{kind} named {name!r}" if name is not None else kind
    if not matches:
        raise AssertionError(f"Manifest kind {wanted} not found")
    if len(matches) > 1:
        names = sorted(str(_manifest_name(m)) for m in matches)
        raise AssertionError(
            f"Multiple {kind} manifests found ({', '.join(names)}); "
            "pass name= to disambiguate"
        )
    return matches[0]


def manifests_by_name(
    manifests: list[dict[str, Any]], kind: str
) -> dict[str, dict[str, Any]]:
    """Return all manifests of the kind, keyed by metadata.name."""

    result: dict[str, dict[str, Any]] = {}
    for manifest in manifests:
        if manifest.get("kind") != kind:
            continue
        name = _manifest_name(manifest)
        if name is None:
            raise AssertionError(f"{kind} manifest without metadata.name")
        if name in result:
            raise AssertionError(f"Duplicate {kind} manifest named {name!r}")
        result[name] = manifest
    return result


def get_primary_container(manifests: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the first container spec from the deployment manifest."""

    deployment = get_manifest(manifests, "Deployment")
    return deployment["spec"]["template"]["spec"]["containers"][0]


__all__ = [
    "ChartContext",
    "assert_matches_golden",
    "get_manifest",
    "get_primary_container",
    "index_documents",
    "load_manifests",
    "manifests_by_name",
    "render_chart",
]
