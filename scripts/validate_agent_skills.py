#!/usr/bin/env python3
"""Validate the repo's Agent Skills layout."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = ROOT / ".agents" / "skills"
EXPECTED_LINKS = {
    ROOT / ".claude" / "skills": SKILLS_ROOT,
    ROOT / ".github" / "skills": SKILLS_ROOT,
    ROOT / "skills": SKILLS_ROOT,
}
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
FIELD_RE = {
    "name": re.compile(r"(?m)^name:\s*(.+?)\s*$"),
    "description": re.compile(r"(?m)^description:\s*(.+?)\s*$"),
}
SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
RELATIVE_PATH_RE = re.compile(r"`((?:assets|references|scripts)/[^`\n]+)`")


def strip_yaml_string(raw: str) -> str:
    """Trim matching quote characters from a YAML scalar string."""

    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def validate_symlink(
    path: Path, expected_target: Path, errors: list[str]
) -> None:
    """Validate a compatibility symlink against the canonical skills path."""

    if not path.exists() and not path.is_symlink():
        errors.append(f"missing compatibility link: {path.relative_to(ROOT)}")
        return
    if not path.is_symlink():
        errors.append(f"expected symlink: {path.relative_to(ROOT)}")
        return
    if path.resolve() != expected_target.resolve():
        errors.append(
            f"wrong symlink target: {path.relative_to(ROOT)} -> "
            f"{path.resolve()}"
        )


def parse_frontmatter(
    skill_file: Path, errors: list[str]
) -> tuple[str, str] | None:
    """Extract required frontmatter fields from a skill file."""

    content = skill_file.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(content)
    if not match:
        errors.append(
            f"{skill_file.relative_to(ROOT)}: missing YAML frontmatter"
        )
        return None

    frontmatter = match.group(1)
    fields: dict[str, str] = {}
    for field, pattern in FIELD_RE.items():
        field_match = pattern.search(frontmatter)
        if not field_match:
            errors.append(f"{skill_file.relative_to(ROOT)}: missing `{field}`")
            continue
        fields[field] = strip_yaml_string(field_match.group(1))

    if len(fields) != len(FIELD_RE):
        return None

    if not fields["name"]:
        errors.append(f"{skill_file.relative_to(ROOT)}: empty `name`")
    if not fields["description"]:
        errors.append(f"{skill_file.relative_to(ROOT)}: empty `description`")

    return fields["name"], fields["description"]


def validate_skill(skill_dir: Path, errors: list[str]) -> None:
    """Validate one skill directory and its referenced assets."""

    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        errors.append(f"{skill_dir.relative_to(ROOT)}: missing SKILL.md")
        return

    parsed = parse_frontmatter(skill_file, errors)
    if parsed is None:
        return

    name, _description = parsed
    if not SKILL_NAME_RE.fullmatch(name):
        errors.append(
            f"{skill_file.relative_to(ROOT)}: invalid skill name `{name}`"
        )
    if name != skill_dir.name:
        errors.append(
            f"{skill_file.relative_to(ROOT)}: `name` must match directory "
            f"`{skill_dir.name}`"
        )

    content = skill_file.read_text(encoding="utf-8")
    if "`skills/" in content:
        errors.append(
            f"{skill_file.relative_to(ROOT)}: replace legacy `skills/` paths "
            "with relative paths"
        )

    for relative_path in RELATIVE_PATH_RE.findall(content):
        if not (skill_dir / relative_path).exists():
            errors.append(
                f"{skill_file.relative_to(ROOT)}: missing referenced path "
                f"`{relative_path}`"
            )


def main() -> int:
    """Validate the repository's skill layout and compatibility links."""

    errors: list[str] = []

    if not SKILLS_ROOT.is_dir():
        errors.append("missing canonical skills directory: .agents/skills")
    else:
        skill_dirs = sorted(
            path
            for path in SKILLS_ROOT.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        )
        if not skill_dirs:
            errors.append("no skills found under .agents/skills")
        for skill_dir in skill_dirs:
            validate_skill(skill_dir, errors)

    for link_path, expected_target in EXPECTED_LINKS.items():
        validate_symlink(link_path, expected_target, errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Agent skills validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
