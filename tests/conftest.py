"""Shared pytest fixtures for chart testing."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterable, Set
from urllib.parse import urlparse

import pytest

try:  # pragma: no cover - plugin available in CI
    from pytest_helm_charts.giantswarm.helm import HelmRunner, HelmTemplateError
except ModuleNotFoundError:  # pragma: no cover - fallback for local dev
    from tests._vendor.pytest_helm_charts.giantswarm.helm import (
        HelmRunner,
        HelmTemplateError,
    )

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

HELM_BINARY = shutil.which("helm")
REQUIRES_HELM = "Helm binary is required to render charts."


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register custom command-line options for pytest."""
    parser.addoption(
        "--skip-helm-network",
        action="store_true",
        default=False,
        help=(
            "Disable Helm network operations in tests "
            "(no repo add/update or dependency build)."
        ),
    )


def _iter_charts_with_manifests() -> Iterable[Path]:
    """Yield chart directories that contain a Chart.yaml file."""

    repo_root = Path(__file__).resolve().parents[1]
    charts_root = repo_root / "charts"
    if not charts_root.is_dir():
        return []

    return (
        chart_dir
        for chart_dir in charts_root.iterdir()
        if (chart_dir / "Chart.yaml").is_file()
    )


def _prefetch_dependencies(config: pytest.Config) -> None:
    """Build chart dependencies once before xdist workers launch."""

    if getattr(config, "workerinput", None) is not None:
        # Worker processes fetch dependencies lazily via helm_runner.
        return

    if config.getoption("--skip-helm-network"):
        logger.info(
            "Skipping Helm dep prefetch due to --skip-helm-network option."
        )
        return

    if HELM_BINARY is None:
        logger.info("Helm not found; skipping dependency prefetch.")
        return

    runner = DependencyBuildingHelmRunner(
        helm_binary_path=HELM_BINARY,
        network_allowed=True,
    )

    for chart_dir in _iter_charts_with_manifests():
        logger.info("Pre-fetching Helm dependencies for %s", chart_dir)
        runner._ensure_dependencies_built(str(chart_dir))


def pytest_configure(config: pytest.Config) -> None:
    """Run repo/dependency setup before tests dispatch to workers."""

    _prefetch_dependencies(config)


class DependencyBuildingHelmRunner(HelmRunner):
    """HelmRunner that auto-adds repos and builds dependencies."""

    def __init__(
        self,
        *,
        helm_binary_path: str,
        network_allowed: bool = True,
    ) -> None:
        """Initialise the runner with Helm and network settings."""
        super().__init__(helm_binary_path=helm_binary_path)
        self._helm_binary_path = helm_binary_path
        self._network_allowed = network_allowed

        self._built_charts: Set[str] = set()
        self._known_repos_by_url: Dict[str, str] = {}
        self._repos_loaded: bool = False
        self._repos_updated_this_session: bool = False

    # -------------------------------
    # Repo discovery & auto-add
    # -------------------------------
    def _load_known_repos(self) -> None:
        """Populate repo map from `helm repo list` once."""
        if self._repos_loaded:
            return

        logger.debug("Loading Helm repos with `helm repo list`.")
        cmd = [self._helm_binary_path, "repo", "list", "--output", "json"]
        result = subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:
            logger.warning(
                "Failed to list repos (cmd=%s, exit=%d): %s",
                " ".join(cmd),
                result.returncode,
                result.stderr.strip(),
            )
            self._repos_loaded = True
            return

        try:
            data = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            logger.warning(
                "Unable to parse helm repo list JSON; stdout:\n%s",
                result.stdout,
            )
            self._repos_loaded = True
            return

        for entry in data:
            url = entry.get("url")
            name = entry.get("name")
            if url and name:
                self._known_repos_by_url[url] = name
                logger.debug("Repo found: %s -> %s", name, url)

        self._repos_loaded = True

    @staticmethod
    def _make_repo_name_from_url(url: str) -> str:
        """Generate an auto name from the URL."""
        parsed = urlparse(url)
        if parsed.netloc:
            bits = [p for p in parsed.path.split("/") if p]
            tail = bits[-1] if bits else parsed.netloc
            base = tail.split(".")[0]
        else:
            base = "repo"
        return f"auto-{base}"

    def _ensure_repositories_for_chart(self, chart_path: str) -> None:
        """Ensure dependencies' repos from Chart.yaml are configured."""
        if not self._network_allowed:
            logger.info(
                "Skipping repo setup for %s due to --skip-helm-network.",
                chart_path,
            )
            return

        chart_dir = Path(chart_path)
        chart_yaml = chart_dir / "Chart.yaml"

        if not chart_yaml.is_file():
            logger.debug("No Chart.yaml at %s; skipping.", chart_yaml)
            return

        try:
            import yaml  # type: ignore[import]
        except ImportError:
            logger.warning(
                "PyYAML missing; can't auto-add repos for %s",
                chart_yaml,
            )
            return

        try:
            data = yaml.safe_load(chart_yaml.read_text()) or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Bad Chart.yaml at %s: %s",
                chart_yaml,
                exc,
            )
            return

        dependencies = data.get("dependencies") or []
        if not dependencies:
            logger.debug(
                "Chart %s has no dependencies.",
                chart_yaml,
            )
            return

        self._load_known_repos()
        repos_to_add: Dict[str, str] = {}

        for dep in dependencies:
            repo_url = dep.get("repository")
            if not repo_url:
                continue

            if repo_url in self._known_repos_by_url:
                logger.debug(
                    "Repo exists already: %s (%s)",
                    repo_url,
                    self._known_repos_by_url[repo_url],
                )
                continue

            base_name = self._make_repo_name_from_url(repo_url)
            existing = set(self._known_repos_by_url.values()) | set(
                repos_to_add.values()
            )

            name = base_name
            n = 1
            while name in existing:
                n += 1
                name = f"{base_name}-{n}"

            repos_to_add[repo_url] = name

        if not repos_to_add:
            logger.debug(
                "All repos present for chart %s.",
                chart_yaml,
            )
            return

        for repo_url, name in repos_to_add.items():
            logger.info(
                "Adding repo '%s' for URL %s (auto-added).",
                name,
                repo_url,
            )
            cmd = [self._helm_binary_path, "repo", "add", name, repo_url]
            result = subprocess.run(
                cmd,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            if result.stdout:
                logger.debug(
                    "`helm repo add` stdout for %s:\n%s",
                    name,
                    result.stdout,
                )
            if result.stderr:
                logger.debug(
                    "`helm repo add` stderr for %s:\n%s",
                    name,
                    result.stderr,
                )

            if result.returncode != 0:
                logger.error(
                    "Failed repo add %s (%s): %s",
                    name,
                    repo_url,
                    result.stderr.strip(),
                )
                raise HelmTemplateError(cmd, result.stderr.strip())

            self._known_repos_by_url[repo_url] = name

        if not self._repos_updated_this_session:
            logger.info("Running `helm repo update`.")
            update_cmd = [self._helm_binary_path, "repo", "update"]
            update_result = subprocess.run(
                update_cmd,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            if update_result.stdout:
                logger.debug(
                    "`helm repo update` stdout:\n%s",
                    update_result.stdout.strip(),
                )
            if update_result.stderr:
                logger.debug(
                    "`helm repo update` stderr:\n%s",
                    update_result.stderr.strip(),
                )
            if update_result.returncode != 0:
                raise HelmTemplateError(
                    update_cmd,
                    update_result.stderr.strip(),
                )

            self._repos_updated_this_session = True

    # -------------------------------
    # Dependency build
    # -------------------------------
    def _ensure_dependencies_built(self, chart: str) -> None:
        """Run `helm dependency build` once per chart path."""
        chart_path = str(Path(chart).resolve())

        if not self._network_allowed:
            logger.info(
                "Skipping dep build for %s due to --skip-helm-network.",
                chart_path,
            )
            return

        if chart_path in self._built_charts:
            logger.debug(
                "Dependency build already done for %s.",
                chart_path,
            )
            return

        self._ensure_repositories_for_chart(chart_path)

        logger.info(
            "Building dependencies for chart: %s",
            chart_path,
        )
        cmd = [self._helm_binary_path, "dependency", "build", chart_path]
        result = subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.stdout:
            logger.debug(
                "`helm dependency build` stdout:\n%s",
                result.stdout.strip(),
            )
        if result.stderr:
            logger.debug(
                "`helm dependency build` stderr:\n%s",
                result.stderr.strip(),
            )

        if result.returncode != 0:
            raise HelmTemplateError(cmd, result.stderr.strip())

        self._built_charts.add(chart_path)
        logger.info(
            "Dependency build complete for %s",
            chart_path,
        )

    # -------------------------------
    # Template override
    # -------------------------------
    def template(
        self,
        *,
        name: str,
        chart: str,
        namespace: str | None = None,
        values_files=None,
        values=None,
        show_only=None,
        extra_args=None,
    ) -> str:
        """Render chart."""
        self._ensure_dependencies_built(chart)

        logger.debug(
            "Rendering %s (release=%s ns=%s).",
            chart,
            name,
            namespace,
        )

        return super().template(
            name=name,
            chart=chart,
            namespace=namespace,
            values_files=values_files,
            values=values,
            show_only=show_only,
            extra_args=extra_args,
        )


@pytest.fixture(scope="session")
def helm_network_allowed(
    request: pytest.FixtureRequest,
) -> bool:
    """Return whether network operations are permitted."""
    skip = bool(request.config.getoption("--skip-helm-network"))
    return not skip


@pytest.fixture(scope="session")
def helm_runner(
    helm_network_allowed: bool,
) -> DependencyBuildingHelmRunner:
    """Return a configured Helm runner."""
    helm_binary = HELM_BINARY
    if helm_binary is None:
        pytest.skip(REQUIRES_HELM)
    assert helm_binary is not None
    return DependencyBuildingHelmRunner(
        helm_binary_path=helm_binary,
        network_allowed=helm_network_allowed,
    )
