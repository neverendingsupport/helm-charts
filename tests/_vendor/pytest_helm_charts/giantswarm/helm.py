"""Fallback Helm helpers used when pytest-helm-charts is unavailable."""
from __future__ import annotations

import shutil
import subprocess
from typing import Mapping, Sequence


class HelmTemplateError(RuntimeError):
    """Raised when the Helm CLI returns a non-zero exit status."""

    def __init__(self, command: Sequence[str], stderr: str) -> None:
        """Initialise the error with the Helm command and stderr text."""
        self.command = list(command)
        self.stderr = stderr
        super().__init__(command, stderr)

    def __str__(self) -> str:
        """Return a human-readable error message for the failure."""
        message = " ".join(self.command)
        if self.stderr:
            return f"{message} failed: {self.stderr}"
        return f"{message} failed"


class HelmRunner:
    """Thin wrapper around the Helm CLI for templating charts."""

    def __init__(self, helm_binary_path: str | None = None) -> None:
        """Create a runner with an optional Helm binary override."""
        binary = helm_binary_path or shutil.which("helm")
        if binary is None:
            raise FileNotFoundError(
                "Helm binary was not found in PATH.",
            )
        self.helm_binary_path: str = binary

    def template(
        self,
        *,
        name: str,
        chart: str,
        namespace: str | None = None,
        values_files: Sequence[str] | None = None,
        values: Mapping[str, str] | None = None,
        show_only: Sequence[str] | None = None,
        extra_args: Sequence[str] | None = None,
    ) -> str:
        """Render a chart and return the raw YAML output."""

        command: list[str] = [
            self.helm_binary_path,
            "template",
            name,
            chart,
        ]
        if namespace:
            command.extend(["--namespace", namespace])
        for values_file in values_files or ():
            command.extend(["--values", str(values_file)])
        for key, value in (values or {}).items():
            command.extend(["--set", f"{key}={value}"])
        for template_path in show_only or ():
            command.extend(["--show-only", template_path])
        if extra_args:
            command.extend(extra_args)

        result = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            raise HelmTemplateError(command, result.stderr.strip())
        return result.stdout


__all__ = ["HelmRunner", "HelmTemplateError"]
