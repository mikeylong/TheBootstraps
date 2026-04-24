#!/usr/bin/env python3
"""Install this local skill repository into the Codex skills directory."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


IGNORE_NAMES = {
    ".git",
    ".DS_Store",
    "__pycache__",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install this skill into the Codex skills directory.")
    parser.add_argument(
        "--dest",
        help="Skills directory to install into. Defaults to $CODEX_HOME/skills or ~/.codex/skills.",
    )
    parser.add_argument("--force", action="store_true", help="Replace an existing installed copy.")
    parser.add_argument("--dry-run", action="store_true", help="Print the install target without copying files.")
    return parser.parse_args()


def skill_root() -> Path:
    root = Path(__file__).resolve().parents[1]
    if not (root / "SKILL.md").is_file():
        raise FileNotFoundError(f"Could not find SKILL.md at expected skill root: {root}")
    return root


def skill_name(root: Path) -> str:
    for line in (root / "SKILL.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    raise ValueError(f"Could not find skill name in {root / 'SKILL.md'}")


def default_dest() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser() / "skills"
    return Path.home() / ".codex" / "skills"


def ignore_patterns(_: str, names: list[str]) -> set[str]:
    return {name for name in names if name in IGNORE_NAMES or name.endswith(".pyc")}


def install(root: Path, target: Path, *, force: bool, dry_run: bool) -> None:
    if dry_run:
        print(f"Would install {root} -> {target}")
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not force:
            raise FileExistsError(f"Install target already exists. Re-run with --force to replace it: {target}")
        shutil.rmtree(target)

    shutil.copytree(root, target, ignore=ignore_patterns)
    print(f"Installed {root.name} -> {target}")


def main() -> int:
    args = parse_args()
    root = skill_root()
    target = (Path(args.dest).expanduser() if args.dest else default_dest()) / skill_name(root)
    install(root, target, force=args.force, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
