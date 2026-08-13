#!/usr/bin/env python3
"""Install this local skill repository into the Codex skills directory."""

from __future__ import annotations

import argparse
import ctypes
import errno
import os
import re
import shutil
import stat
import sys
import tempfile
import uuid
from pathlib import Path


IGNORE_NAMES = {
    ".git",
    ".DS_Store",
    "__pycache__",
}

SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


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
            raw_value = line.split(":", 1)[1].strip()
            if raw_value[:1] in ("\"", "'") or raw_value[-1:] in ("\"", "'"):
                if len(raw_value) < 2 or raw_value[-1] != raw_value[0]:
                    raise ValueError(f"Skill name has mismatched quotes in {root / 'SKILL.md'}")
                value = raw_value[1:-1]
            else:
                value = raw_value
            if not SKILL_NAME_PATTERN.fullmatch(value):
                raise ValueError(
                    "Skill name must contain only lowercase letters, digits, and single hyphens: "
                    f"{value!r}"
                )
            return value
    raise ValueError(f"Could not find skill name in {root / 'SKILL.md'}")


def default_dest() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser() / "skills"
    return Path.home() / ".codex" / "skills"


def ignore_patterns(_: str, names: list[str]) -> set[str]:
    return {name for name in names if name in IGNORE_NAMES or name.endswith(".pyc")}


def _is_ignored_source_name(name: str) -> bool:
    return name in IGNORE_NAMES or name.endswith(".pyc")


def validate_source_tree(root: Path) -> None:
    """Require an ordinary, self-contained source tree before installation."""

    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"Install source must be a real directory: {root}")

    for directory, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        directory_path = Path(directory)
        accepted_directories: list[str] = []
        for name in directory_names:
            if _is_ignored_source_name(name):
                continue
            path = directory_path / name
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise ValueError(f"Install source must not contain symlinks: {path}")
            if not stat.S_ISDIR(metadata.st_mode):
                raise ValueError(f"Install source contains an unsupported path type: {path}")
            accepted_directories.append(name)
        directory_names[:] = accepted_directories

        for name in file_names:
            if _is_ignored_source_name(name):
                continue
            path = directory_path / name
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise ValueError(f"Install source must not contain symlinks: {path}")
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(f"Install source contains an unsupported path type: {path}")


def validate_destination(destination: Path) -> None:
    """Reject non-directory or symlink components in the destination chain."""

    absolute_destination = Path(os.path.abspath(os.fspath(destination.expanduser())))
    current = Path(absolute_destination.anchor)
    for part in absolute_destination.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            break
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"Install destination path must not contain a symlink: {current}")
        if not stat.S_ISDIR(metadata.st_mode):
            raise FileExistsError(f"Install destination path component is not a directory: {current}")


def install_target(destination: Path, name: str) -> Path:
    """Return the validated direct-child install target."""

    if not SKILL_NAME_PATTERN.fullmatch(name):
        raise ValueError(f"Unsafe skill name: {name!r}")
    absolute_destination = Path(os.path.abspath(os.fspath(destination.expanduser())))
    validate_destination(absolute_destination)
    target = absolute_destination / name
    if target.parent != absolute_destination or target.resolve(strict=False).parent != absolute_destination.resolve(strict=False):
        raise ValueError(f"Install target must be a direct child of the destination: {target}")
    return target


def validate_source_separation(root: Path, target: Path) -> None:
    """Require source and target trees to be disjoint."""

    resolved_root = root.resolve(strict=True)
    resolved_target = target.resolve(strict=False)
    if resolved_target == resolved_root:
        raise ValueError(f"Install target must be separate from the source skill directory: {target}")

    try:
        resolved_target.relative_to(resolved_root)
    except ValueError:
        pass
    else:
        raise ValueError(f"Install target must not be inside the source skill directory: {target}")

    try:
        resolved_root.relative_to(resolved_target)
    except ValueError:
        return
    raise ValueError(f"Install target must not contain the source skill directory: {target}")


def validate_target(target: Path, *, force: bool) -> str:
    if target.is_symlink():
        raise ValueError(f"Install target must not be a symlink: {target}")
    if not target.exists():
        return "create"
    if not target.is_dir():
        raise FileExistsError(f"Install target exists and is not a directory: {target}")
    if not force:
        raise FileExistsError(f"Install target already exists. Re-run with --force to replace it: {target}")
    return "replace"


def directory_identity(path: Path) -> tuple[int, int]:
    """Return the device/inode identity of a real directory."""

    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise FileExistsError(f"Install target changed after preflight: {path}")
    return metadata.st_dev, metadata.st_ino


def rename_directory_noreplace(source: Path, target: Path) -> None:
    """Atomically publish a directory while refusing any existing target."""

    encoded_source = os.fsencode(source)
    encoded_target = os.fsencode(target)
    library = ctypes.CDLL(None, use_errno=True)

    if sys.platform == "darwin":
        renamex_np = library.renamex_np
        renamex_np.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
        renamex_np.restype = ctypes.c_int
        result = renamex_np(encoded_source, encoded_target, 0x00000004)  # RENAME_EXCL
    elif sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        renameat2 = library.renameat2
        renameat2.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        renameat2.restype = ctypes.c_int
        result = renameat2(-100, encoded_source, -100, encoded_target, 0x00000001)
    elif os.name == "nt":
        try:
            os.rename(source, target)
        except FileExistsError:
            raise FileExistsError(f"Install target appeared after preflight: {target}") from None
        return
    else:
        raise RuntimeError(
            "This platform does not expose an atomic no-replace directory rename; "
            "refusing an unsafe install create"
        )

    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in (errno.EEXIST, errno.ENOTEMPTY):
        raise FileExistsError(f"Install target appeared after preflight: {target}")
    raise OSError(error_number, os.strerror(error_number), os.fspath(target))


def replace_directory(
    staged_target: Path,
    target: Path,
    *,
    action: str,
    expected_identity: tuple[int, int] | None,
) -> None:
    if action == "create":
        if os.path.lexists(target):
            raise FileExistsError(f"Install target appeared after preflight: {target}")
        rename_directory_noreplace(staged_target, target)
        return

    if action != "replace":
        raise ValueError(f"Unsupported install action: {action}")
    if expected_identity is None or directory_identity(target) != expected_identity:
        raise FileExistsError(f"Install target changed after preflight: {target}")

    backup = target.parent / f".{target.name}.backup-{uuid.uuid4().hex}"
    try:
        target.rename(backup)
        if directory_identity(backup) != expected_identity:
            raise FileExistsError(f"Install target changed during replacement: {target}")
        staged_target.rename(target)
    except BaseException:
        if not os.path.lexists(backup):
            raise
        if os.path.lexists(target):
            raise RuntimeError(
                f"Install failed after backup; recovery copy remains at {backup}"
            )
        try:
            backup.rename(target)
        except BaseException as restore_error:
            raise RuntimeError(
                f"Install failed and the previous copy could not be restored from {backup}"
            ) from restore_error
        raise

    try:
        shutil.rmtree(backup)
    except OSError as cleanup_error:
        print(f"Warning: installed successfully but could not remove backup {backup}: {cleanup_error}", file=sys.stderr)


def install(root: Path, target: Path, *, force: bool, dry_run: bool) -> None:
    validate_source_tree(root)
    validate_source_separation(root, target)
    validate_destination(target.parent)
    action = validate_target(target, force=force)
    expected_identity = directory_identity(target) if action == "replace" else None

    if dry_run:
        print(f"Would {action} {root} -> {target}")
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=f".{target.name}.install-", dir=target.parent))
    staged_target = temp_root / target.name
    try:
        shutil.copytree(root, staged_target, ignore=ignore_patterns, symlinks=True)
        validate_source_tree(staged_target)
        validate_destination(target.parent)
        if validate_target(target, force=force) != action:
            raise FileExistsError(f"Install target changed after preflight: {target}")
        if action == "replace" and directory_identity(target) != expected_identity:
            raise FileExistsError(f"Install target changed after preflight: {target}")
        replace_directory(
            staged_target,
            target,
            action=action,
            expected_identity=expected_identity,
        )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    print(f"Installed {root.name} -> {target}")


def main() -> int:
    args = parse_args()
    root = skill_root()
    try:
        destination = Path(args.dest).expanduser() if args.dest else default_dest()
        target = install_target(destination, skill_name(root))
        install(root, target, force=args.force, dry_run=args.dry_run)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
