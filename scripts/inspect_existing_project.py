#!/usr/bin/env python3
"""Inspect an existing project and preserve its agentic artifacts externally."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SCHEMA_VERSION = "1"
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_CONTEXT_BYTES = 2 * 1024 * 1024

SKIPPED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "coverage",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
}

AGENTIC_FILENAMES = {
    "agents.md",
    "agent.md",
    "claude.md",
    "codex.md",
    "gemini.md",
    "current.md",
    "context.md",
    "context_map.md",
    "contextmap.md",
    "decisions.md",
    "design.md",
    "handoff.md",
    "plan.md",
    "skill.md",
    ".cursorrules",
    ".mcp.json",
    "mcp.json",
    "copilot-instructions.md",
}

ORIENTATION_FILENAMES = {
    "readme.md",
    "contributing.md",
    "architecture.md",
    "security.md",
    "governance.md",
}

MANIFEST_FILENAMES = {
    "package.json",
    "pyproject.toml",
    "cargo.toml",
    "go.mod",
    "requirements.txt",
    "gemfile",
    "composer.json",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "makefile",
}

CI_FILENAMES = {
    ".gitlab-ci.yml",
    ".gitlab-ci.yaml",
    "jenkinsfile",
    "azure-pipelines.yml",
    "azure-pipelines.yaml",
}

SENSITIVE_PATH_NAMES = {
    ".env",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "credentials",
    "credentials.json",
    "secrets.json",
    "id_rsa",
    "id_ed25519",
}

URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
SENSITIVE_CONTENT_PATTERNS = (
    re.compile(rb"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
    re.compile(
        rb"(?im)^\s*[\"']?[A-Z0-9_.-]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)"
        rb"[A-Z0-9_.-]*[\"']?\s*[:=]\s*[\"']?[^\s#,\"'}]+"
    ),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(rb"\bxox(?:a|b|p|r|s)-[A-Za-z0-9-]{16,}\b"),
    re.compile(rb"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(rb"(?i)\bauthorization\s*:\s*(?:bearer|basic)\s+\S+"),
    re.compile(rb"(?i)https?://[^\s/@:]+:[^\s/@]+@"),
)

SENSITIVE_QUERY_NAMES = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "code",
    "credential",
    "key",
    "password",
    "secret",
    "signature",
    "sig",
    "token",
}
SENSITIVE_QUERY_MARKERS = (
    "auth",
    "code",
    "credential",
    "key",
    "password",
    "secret",
    "signature",
    "token",
)


@dataclass(frozen=True)
class SourceEntry:
    """One source-tree entry captured without following symlinks."""

    path: Path
    relative_path: str
    kind: str
    mode: int
    size: int
    mtime_ns: int
    device: int
    inode: int
    link_target: str | None = None

    def snapshot_record(self) -> tuple[object, ...]:
        return (
            self.relative_path,
            self.kind,
            self.mode,
            self.size,
            self.mtime_ns,
            self.device,
            self.inode,
            self.link_target,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect an existing project, preserve agentic artifacts outside it, "
            "and emit a connected-context request report."
        )
    )
    parser.add_argument("target", help="Existing repository or explicit monorepo scope to inspect.")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        dest="output_format",
        help="Report format. Defaults to json.",
    )
    parser.add_argument(
        "--archive-dir",
        help="Opt in to a new preservation archive outside the source.",
    )
    return parser.parse_args()


def entry_kind(metadata: os.stat_result) -> str:
    if stat.S_ISDIR(metadata.st_mode):
        return "directory"
    if stat.S_ISREG(metadata.st_mode):
        return "file"
    if stat.S_ISLNK(metadata.st_mode):
        return "symlink"
    return "special"


def validate_source(raw_target: str) -> Path:
    requested = Path(os.path.abspath(os.fspath(Path(raw_target).expanduser())))
    try:
        metadata = requested.lstat()
    except FileNotFoundError as error:
        raise FileNotFoundError(f"Inspection target does not exist: {requested}") from error
    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError(f"Inspection target must not be a symlink: {requested}")
    if not stat.S_ISDIR(metadata.st_mode):
        raise NotADirectoryError(f"Inspection target is not a directory: {requested}")
    resolved = requested.resolve(strict=True)
    if resolved == Path(resolved.anchor):
        raise ValueError("Refusing to inspect a filesystem root")
    return resolved


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def choose_archive_path(source: Path, requested: str | None) -> Path:
    if requested is None:
        raise ValueError("Archive creation requires an explicit --archive-dir")
    raw_archive = Path(os.path.abspath(os.fspath(Path(requested).expanduser())))
    try:
        parent_metadata = raw_archive.parent.lstat()
    except FileNotFoundError as error:
        raise FileNotFoundError(
            f"Archive parent must already exist: {raw_archive.parent}"
        ) from error
    if stat.S_ISLNK(parent_metadata.st_mode):
        raise ValueError(f"Archive parent must not be a symlink: {raw_archive.parent}")
    if not stat.S_ISDIR(parent_metadata.st_mode):
        raise NotADirectoryError(f"Archive parent is not a directory: {raw_archive.parent}")
    archive = raw_archive.parent.resolve(strict=True) / raw_archive.name

    if os.path.lexists(archive):
        raise FileExistsError(f"Archive destination already exists: {archive}")
    resolved_archive = archive.resolve(strict=False)
    if (
        resolved_archive == source
        or _is_relative_to(resolved_archive, source)
        or _is_relative_to(source, resolved_archive)
    ):
        raise ValueError(f"Archive and source must be disjoint: {resolved_archive}")
    if not resolved_archive.parent.is_dir():
        raise FileNotFoundError(f"Archive parent must already exist: {resolved_archive.parent}")
    return resolved_archive


def walk_source(source: Path) -> tuple[list[SourceEntry], list[dict[str, str]]]:
    entries: list[SourceEntry] = []
    exclusions: list[dict[str, str]] = []

    root_metadata = source.lstat()
    entries.append(
        SourceEntry(
            path=source,
            relative_path=".",
            kind="directory",
            mode=stat.S_IMODE(root_metadata.st_mode),
            size=root_metadata.st_size,
            mtime_ns=root_metadata.st_mtime_ns,
            device=root_metadata.st_dev,
            inode=root_metadata.st_ino,
        )
    )

    def visit(directory_descriptor: int, directory: Path, relative_directory: str) -> None:
        try:
            children = sorted(os.scandir(directory_descriptor), key=lambda child: child.name)
        except OSError as error:
            raise OSError(f"Could not inspect directory {directory}: {error.strerror}") from error

        for child in children:
            relative = child.name if relative_directory == "." else f"{relative_directory}/{child.name}"
            child_path = directory / child.name
            try:
                metadata = child.stat(follow_symlinks=False)
            except OSError as error:
                raise OSError(f"Could not inspect path {child_path}: {error.strerror}") from error
            kind = entry_kind(metadata)
            link_target = None
            if kind == "symlink":
                try:
                    link_target = os.readlink(child_path)
                except OSError as error:
                    raise OSError(f"Could not read symlink {child_path}: {error.strerror}") from error
            entry = SourceEntry(
                path=child_path,
                relative_path=relative,
                kind=kind,
                mode=stat.S_IMODE(metadata.st_mode),
                size=metadata.st_size,
                mtime_ns=metadata.st_mtime_ns,
                device=metadata.st_dev,
                inode=metadata.st_ino,
                link_target=link_target,
            )
            entries.append(entry)

            if kind != "directory":
                continue
            if child.name.casefold() in SKIPPED_DIRECTORIES:
                exclusions.append(
                    {
                        "path": relative,
                        "reason": "excluded generated, dependency, cache, or VCS internals",
                    }
                )
                continue
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            try:
                child_descriptor = os.open(child.name, flags, dir_fd=directory_descriptor)
            except OSError as error:
                raise RuntimeError(
                    f"Source directory changed or became unsafe during inspection: {child_path}"
                ) from error
            try:
                current_metadata = os.fstat(child_descriptor)
                if (
                    not stat.S_ISDIR(current_metadata.st_mode)
                    or current_metadata.st_dev != metadata.st_dev
                    or current_metadata.st_ino != metadata.st_ino
                ):
                    raise RuntimeError(f"Source path changed during inspection: {child_path}")
                visit(child_descriptor, child_path, relative)
            finally:
                os.close(child_descriptor)

    root_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    root_descriptor = os.open(source, root_flags)
    try:
        opened_root = os.fstat(root_descriptor)
        if (
            opened_root.st_dev != root_metadata.st_dev
            or opened_root.st_ino != root_metadata.st_ino
        ):
            raise RuntimeError(f"Source root changed during inspection: {source}")
        visit(root_descriptor, source, ".")
    finally:
        os.close(root_descriptor)
    entries.sort(key=lambda item: item.relative_path)
    exclusions.sort(key=lambda item: item["path"])
    return entries, exclusions


def snapshot_digest(entries: Iterable[SourceEntry]) -> str:
    records = [entry.snapshot_record() for entry in entries]
    encoded = json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def is_agentic_path(relative_path: str) -> bool:
    parts = relative_path.split("/")
    lowered = [part.casefold() for part in parts]
    filename = lowered[-1]
    if filename in AGENTIC_FILENAMES:
        return True
    if lowered[0] in {".agents", ".codex", ".claude", ".cursor", ".windsurf"}:
        return True
    if lowered[0] == "agents":
        return True
    if lowered[0] in {"plans", "prompts", "specs"}:
        return True
    if lowered[0] == "docs" and any(part in {"adr", "adrs", "decisions"} for part in lowered[1:]):
        return True
    if lowered[0] == ".github" and (
        filename == "copilot-instructions.md"
        or any(part in {"instructions", "prompts"} for part in lowered[1:-1])
    ):
        return True
    if filename in {"design-tokens.schema.json", "component-rules.json"}:
        return True
    return False


def is_orientation_source(relative_path: str) -> bool:
    lowered = relative_path.casefold().split("/")
    filename = lowered[-1]
    if is_agentic_path(relative_path) or filename in ORIENTATION_FILENAMES:
        return True
    return lowered[0] == "docs" and any(
        part in {"architecture", "adr", "adrs", "decisions", "governance"}
        for part in lowered[1:-1]
    )


def is_manifest(relative_path: str) -> bool:
    return relative_path.split("/")[-1].casefold() in MANIFEST_FILENAMES


def is_ci_path(relative_path: str) -> bool:
    lowered = relative_path.casefold()
    filename = lowered.split("/")[-1]
    return (
        lowered.startswith(".github/workflows/")
        or lowered == ".circleci/config.yml"
        or lowered == ".circleci/config.yaml"
        or filename in CI_FILENAMES
    )


def is_sensitive_path(relative_path: str) -> bool:
    lowered = relative_path.casefold().split("/")
    filename = lowered[-1]
    return (
        filename in SENSITIVE_PATH_NAMES
        or filename.startswith(".env.")
        or "credential" in filename
        or "private-key" in filename
        or "private_key" in filename
        or ("secret" in filename and filename not in {"secret.example", "secrets.example"})
    )


def contains_sensitive_content(data: bytes) -> bool:
    if any(pattern.search(data) is not None for pattern in SENSITIVE_CONTENT_PATTERNS):
        return True
    if b"\x00" in data:
        return False
    text = data.decode("utf-8", errors="replace")
    return any(sensitive_locator(match.group(0)) for match in URL_PATTERN.finditer(text))


def sensitive_locator(raw_locator: str) -> bool:
    parsed = urlsplit(raw_locator.rstrip(".,;:!?)]}>"))
    if parsed.username is not None or parsed.password is not None:
        return True
    return any(
        any(marker in name.casefold() for marker in SENSITIVE_QUERY_MARKERS)
        for name, _ in parse_qsl(parsed.query, keep_blank_values=True)
    )


def source_root_for_entry(entry: SourceEntry) -> Path:
    root = entry.path
    for _ in Path(entry.relative_path).parts:
        root = root.parent
    return root


def read_stable_file(entry: SourceEntry, *, byte_limit: int) -> bytes:
    if entry.kind != "file":
        raise ValueError(f"Cannot read non-file source entry: {entry.relative_path}")
    if entry.size > byte_limit:
        raise OverflowError(f"File exceeds the inspection byte limit: {entry.relative_path}")
    root = source_root_for_entry(entry)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    directory_descriptor = os.open(root, directory_flags)
    parts = Path(entry.relative_path).parts
    try:
        for part in parts[:-1]:
            next_descriptor = os.open(part, directory_flags, dir_fd=directory_descriptor)
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        descriptor = os.open(parts[-1], descriptor_flags, dir_fd=directory_descriptor)
    except OSError as error:
        os.close(directory_descriptor)
        raise OSError(
            f"Could not read source artifact without following links {entry.relative_path}: "
            f"{error.strerror}"
        ) from error
    try:
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_dev != entry.device
                or opened.st_ino != entry.inode
                or opened.st_size != entry.size
                or opened.st_mtime_ns != entry.mtime_ns
            ):
                raise RuntimeError(
                    f"Source artifact changed during inspection: {entry.relative_path}"
                )
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, min(1024 * 1024, byte_limit + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > byte_limit:
                    raise OverflowError(
                        f"File exceeds the inspection byte limit: {entry.relative_path}"
                    )
            finished = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if (
            finished.st_dev != opened.st_dev
            or finished.st_ino != opened.st_ino
            or finished.st_size != opened.st_size
            or finished.st_mtime_ns != opened.st_mtime_ns
        ):
            raise RuntimeError(f"Source artifact changed while being read: {entry.relative_path}")
        current = os.stat(parts[-1], dir_fd=directory_descriptor, follow_symlinks=False)
    finally:
        os.close(directory_descriptor)
    if (
        not stat.S_ISREG(current.st_mode)
        or current.st_dev != entry.device
        or current.st_ino != entry.inode
        or current.st_size != entry.size
        or current.st_mtime_ns != entry.mtime_ns
    ):
        raise RuntimeError(f"Source artifact changed after inspection: {entry.relative_path}")
    return b"".join(chunks)


def sanitize_url(raw_url: str) -> str:
    trimmed = raw_url.rstrip(".,;:!?)]}>")
    parsed = urlsplit(trimmed)
    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port is not None else ""
    netloc = f"{hostname}{port}"
    safe_query = [
        (name, value)
        for name, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not any(marker in name.casefold() for marker in SENSITIVE_QUERY_MARKERS)
    ]
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            netloc,
            parsed.path,
            urlencode(safe_query, doseq=True),
            "",
        )
    )


def sanitize_remote_locator(raw_locator: str) -> str:
    """Remove credentials from a Git remote before recording it."""

    if raw_locator.startswith("git@github.com:"):
        return f"https://github.com/{raw_locator.split(':', 1)[1]}"
    if raw_locator.startswith(("http://", "https://")):
        return sanitize_url(raw_locator)
    if "://" in raw_locator:
        parsed = urlsplit(raw_locator)
        hostname = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port is not None else ""
        safe_query = [
            (name, value)
            for name, value in parse_qsl(parsed.query, keep_blank_values=True)
            if name.casefold() not in SENSITIVE_QUERY_NAMES
        ]
        return urlunsplit(
            (parsed.scheme.casefold(), f"{hostname}{port}", parsed.path, urlencode(safe_query), "")
        )
    prefix, separator, suffix = raw_locator.partition("@")
    if separator and ":" in prefix:
        return f"[redacted]@{suffix}"
    return raw_locator


def extract_urls(data: bytes) -> list[str]:
    if b"\x00" in data:
        return []
    text = data.decode("utf-8", errors="replace")
    urls = {sanitize_url(match.group(0)) for match in URL_PATTERN.finditer(text)}
    return sorted(url for url in urls if url.startswith(("http://", "https://")))


def write_private_file(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def path_identity(path: Path) -> tuple[int, int]:
    metadata = path.lstat()
    if not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"Expected owned directory but found another path type: {path}")
    return metadata.st_dev, metadata.st_ino


def verify_owned_directory(path: Path, expected_identity: tuple[int, int]) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise RuntimeError(f"Owned directory disappeared before use: {path}") from error
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or (metadata.st_dev, metadata.st_ino) != expected_identity
    ):
        raise RuntimeError(f"Refusing operation after owned directory identity changed: {path}")


def remove_owned_tree(path: Path, expected_identity: tuple[int, int]) -> None:
    """Remove only the directory instance created by this process."""

    if not os.path.lexists(path):
        return
    parent_descriptor = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        metadata = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or (metadata.st_dev, metadata.st_ino) != expected_identity
        ):
            raise RuntimeError(
                f"Refusing cleanup after owned directory identity changed: {path}"
            )
        shutil.rmtree(path.name, dir_fd=parent_descriptor)
    finally:
        os.close(parent_descriptor)


def remove_owned_empty_directory(path: Path, expected_identity: tuple[int, int]) -> None:
    if not os.path.lexists(path):
        return
    parent_descriptor = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        metadata = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or (metadata.st_dev, metadata.st_ino) != expected_identity
        ):
            raise RuntimeError(
                f"Refusing cleanup after owned directory identity changed: {path}"
            )
        os.rmdir(path.name, dir_fd=parent_descriptor)
    finally:
        os.close(parent_descriptor)


def collect_git_metadata(source: Path) -> dict[str, Any]:
    if not os.path.lexists(source / ".git"):
        return {"detected": False}
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"

    def run_git(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "git",
                "--no-optional-locks",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "credential.helper=",
                "-C",
                str(source),
                *arguments,
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=environment,
        )

    head_result = run_git("rev-parse", "HEAD")
    status_result = run_git("status", "--porcelain=v1", "--untracked-files=normal")
    remote_result = run_git("remote", "-v")
    if head_result.returncode != 0:
        return {"detected": True, "status": "unavailable"}
    remotes: list[dict[str, str]] = []
    if remote_result.returncode == 0:
        seen: set[tuple[str, str, str]] = set()
        for line in remote_result.stdout.splitlines():
            fields = line.split()
            if len(fields) < 3:
                continue
            name, raw_locator, operation = fields[0], fields[1], fields[2].strip("()")
            locator = sanitize_remote_locator(raw_locator)
            key = (name, locator, operation)
            if key not in seen:
                seen.add(key)
                remotes.append({"name": name, "locator": locator, "operation": operation})
    return {
        "detected": True,
        "status": "available",
        "head": head_result.stdout.strip(),
        "dirty": status_result.returncode == 0 and bool(status_result.stdout.strip()),
        "remotes": sorted(remotes, key=lambda item: (item["name"], item["operation"], item["locator"])),
    }


def archive_artifacts(
    source: Path,
    archive: Path,
    artifacts: list[SourceEntry],
    git_metadata: dict[str, Any],
    source_digest: str,
) -> tuple[Path, tuple[int, int], list[dict[str, Any]], str]:
    stage = archive.parent / f".{archive.name}.stage-{uuid.uuid4().hex}"
    os.mkdir(stage, 0o700)
    stage_identity = path_identity(stage)
    final_created = False
    archive_identity: tuple[int, int] | None = None
    artifact_records: list[dict[str, Any]] = []
    try:
        staged_artifacts = stage / "artifacts"
        staged_artifacts.mkdir(mode=0o700)
        for entry in artifacts:
            record: dict[str, Any] = {"path": entry.relative_path, "kind": entry.kind}
            if entry.kind == "directory":
                destination = staged_artifacts / entry.relative_path
                destination.mkdir(parents=True, exist_ok=True)
                record.update({"status": "recorded", "archive_path": destination.relative_to(stage).as_posix()})
            elif entry.kind == "symlink":
                if entry.link_target is not None and sensitive_locator(entry.link_target):
                    record.update(
                        {
                            "status": "excluded",
                            "reason": "suspected secret or credential link target",
                            "link_target": "[redacted-sensitive-target]",
                        }
                    )
                else:
                    record.update({"status": "recorded", "link_target": entry.link_target})
            elif entry.kind != "file":
                record.update({"status": "excluded", "reason": "unsupported source path type"})
            elif is_sensitive_path(entry.relative_path):
                record.update({"status": "excluded", "reason": "suspected secret or credential path"})
            elif entry.size > MAX_ARTIFACT_BYTES:
                record.update({"status": "excluded", "reason": "artifact exceeds safe archive byte limit"})
            else:
                data = read_stable_file(entry, byte_limit=MAX_ARTIFACT_BYTES)
                if contains_sensitive_content(data):
                    record.update({"status": "excluded", "reason": "suspected secret or credential content"})
                else:
                    destination = staged_artifacts / entry.relative_path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    write_private_file(destination, data)
                    os.chmod(destination, entry.mode)
                    digest = hashlib.sha256(data).hexdigest()
                    record.update(
                        {
                            "status": "copied",
                            "archive_path": destination.relative_to(stage).as_posix(),
                            "sha256": digest,
                            "size": len(data),
                        }
                    )
            artifact_records.append(record)

        artifact_records.sort(key=lambda item: item["path"])
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "source": str(source),
            "archive": str(archive),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "git": git_metadata,
            "source_snapshot": {"status": "unchanged", "digest": source_digest},
            "artifacts": artifact_records,
        }
        manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        manifest_path = stage / "manifest.json"
        write_private_file(manifest_path, manifest_bytes)

        for record in artifact_records:
            if record["status"] != "copied":
                continue
            copied = stage / record["archive_path"]
            copied_data = copied.read_bytes()
            if len(copied_data) != record["size"] or hashlib.sha256(copied_data).hexdigest() != record["sha256"]:
                raise RuntimeError(f"Archive verification failed for {record['path']}")
        fsync_directory(staged_artifacts)
        fsync_directory(stage)

        os.mkdir(archive, 0o700)
        final_created = True
        archive_identity = path_identity(archive)
        verify_owned_directory(stage, stage_identity)
        verify_owned_directory(archive, archive_identity)
        stage_descriptor = os.open(stage, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        archive_descriptor = os.open(archive, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.rename(
                "artifacts",
                "artifacts",
                src_dir_fd=stage_descriptor,
                dst_dir_fd=archive_descriptor,
            )
            os.rename(
                "manifest.json",
                "manifest.json",
                src_dir_fd=stage_descriptor,
                dst_dir_fd=archive_descriptor,
            )
            os.fsync(archive_descriptor)
        finally:
            os.close(archive_descriptor)
            os.close(stage_descriptor)
        verify_owned_directory(archive, archive_identity)
        fsync_directory(archive)
        remove_owned_empty_directory(stage, stage_identity)
        fsync_directory(archive.parent)
        manifest_digest = hashlib.sha256((archive / "manifest.json").read_bytes()).hexdigest()
        return archive, archive_identity, artifact_records, manifest_digest
    except BaseException:
        if final_created and archive_identity is not None:
            remove_owned_tree(archive, archive_identity)
        remove_owned_tree(stage, stage_identity)
        raise


def inventory_artifacts(artifacts: list[SourceEntry]) -> list[dict[str, Any]]:
    """Describe preservation candidates without creating an archive."""

    records: list[dict[str, Any]] = []
    for entry in artifacts:
        record: dict[str, Any] = {
            "path": entry.relative_path,
            "kind": entry.kind,
            "status": "discovered",
            "size": entry.size,
            "mode": f"{entry.mode:04o}",
            "mtime_ns": entry.mtime_ns,
        }
        if entry.kind == "symlink":
            if entry.link_target is not None and sensitive_locator(entry.link_target):
                record.update(
                    {
                        "status": "excluded",
                        "reason": "suspected secret or credential link target",
                        "link_target": "[redacted-sensitive-target]",
                    }
                )
            else:
                record["link_target"] = entry.link_target
        if entry.kind == "file" and is_sensitive_path(entry.relative_path):
            record.update(
                {
                    "status": "excluded",
                    "reason": "suspected secret or credential path",
                }
            )
        records.append(record)
    return sorted(records, key=lambda item: item["path"])


def collect_contexts(
    entries: list[SourceEntry],
    artifact_records: list[dict[str, Any]],
    git_metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    artifact_status = {record["path"]: record["status"] for record in artifact_records}
    by_url: dict[str, set[str]] = {}
    for entry in entries:
        if entry.kind != "file" or not is_orientation_source(entry.relative_path):
            continue
        if artifact_status.get(entry.relative_path) == "excluded" or is_sensitive_path(entry.relative_path):
            continue
        if entry.size > MAX_CONTEXT_BYTES:
            continue
        data = read_stable_file(entry, byte_limit=MAX_CONTEXT_BYTES)
        if contains_sensitive_content(data):
            continue
        for url in extract_urls(data):
            by_url.setdefault(url, set()).add(entry.relative_path)

    for remote in git_metadata.get("remotes", []):
        locator = remote.get("locator", "")
        if locator.startswith(("http://", "https://")):
            normalized = sanitize_url(locator)
            by_url.setdefault(normalized, set()).add(".git/config")

    contexts: list[dict[str, Any]] = []
    for url in sorted(by_url):
        context_id = f"CTX-{hashlib.sha256(url.encode('utf-8')).hexdigest()[:12]}"
        contexts.append(
            {
                "id": context_id,
                "url": url,
                "source_paths": sorted(by_url[url]),
                "requiredness": "pending_review",
                "access_status": "pending",
                "authority": "unconfirmed",
                "freshness": "unconfirmed",
                "governs": "unresolved pending source review",
                "relevance": "Referenced by selected repository evidence",
                "expected_owner": "unconfirmed",
                "freshness_signal": "unconfirmed",
                "acquisition_evidence": None,
                "required_disposition": (
                    "acquired, explicitly unavailable, or user-waived after relevance review"
                ),
                "request_status": "requested",
            }
        )
    return contexts


def build_report(source: Path, archive: Path | None) -> dict[str, Any]:
    before_entries, traversal_exclusions = walk_source(source)
    before_digest = snapshot_digest(before_entries)
    git_metadata = collect_git_metadata(source)
    post_git_entries, post_git_exclusions = walk_source(source)
    post_git_digest = snapshot_digest(post_git_entries)
    if post_git_digest != before_digest or post_git_exclusions != traversal_exclusions:
        raise RuntimeError("Source changed while repository metadata was being inspected")
    artifacts = [
        entry
        for entry in post_git_entries
        if entry.relative_path != "." and is_agentic_path(entry.relative_path)
    ]

    published_archive: Path | None = None
    published_archive_identity: tuple[int, int] | None = None
    try:
        manifest_digest: str | None = None
        if archive is None:
            artifact_records = inventory_artifacts(artifacts)
        else:
            (
                published_archive,
                published_archive_identity,
                artifact_records,
                manifest_digest,
            ) = archive_artifacts(
                source,
                archive,
                artifacts,
                git_metadata,
                before_digest,
            )
        after_entries, after_exclusions = walk_source(source)
        after_digest = snapshot_digest(after_entries)
        if before_digest != after_digest:
            raise RuntimeError("Source changed during inspection; archive was not retained")
        if traversal_exclusions != after_exclusions:
            raise RuntimeError("Source traversal changed during inspection; archive was not retained")

        contexts = collect_contexts(after_entries, artifact_records, git_metadata)
        final_entries, final_exclusions = walk_source(source)
        final_digest = snapshot_digest(final_entries)
        if final_digest != before_digest or final_exclusions != traversal_exclusions:
            raise RuntimeError("Source changed while connected contexts were being indexed")

        manifests = [
            {"path": entry.relative_path}
            for entry in final_entries
            if entry.kind == "file" and is_manifest(entry.relative_path)
        ]
        ci = [
            {"path": entry.relative_path}
            for entry in final_entries
            if entry.kind == "file" and is_ci_path(entry.relative_path)
        ]
        boundaries = [
            {"path": entry.path.parent.relative_to(source).as_posix() or "."}
            for entry in final_entries
            if entry.relative_path != ".git" and entry.path.name == ".git"
        ]
        blocking_ids = [context["id"] for context in contexts]
        gate_reasons = [
            "Connected contexts must be reviewed, acquired, explicitly unavailable, or user-waived before recommendation.",
            "Repository authority and active-scope confirmation remain required before recommendation.",
        ]
        if published_archive is None:
            gate_reasons.insert(
                0,
                "A verified preservation archive created with explicit --archive-dir is required before recommendation.",
            )
        evidence_sources = []
        for entry in final_entries:
            if entry.kind != "file":
                continue
            roles = []
            if is_orientation_source(entry.relative_path):
                roles.append("orientation_or_agentic")
            if is_manifest(entry.relative_path):
                roles.append("runtime_manifest")
            if is_ci_path(entry.relative_path):
                roles.append("ci")
            if roles:
                evidence_sources.append({"path": entry.relative_path, "roles": roles})
        top_level_entries = [
            {"path": entry.relative_path, "kind": entry.kind}
            for entry in final_entries
            if entry.relative_path != "." and "/" not in entry.relative_path
        ]
        return {
            "schema_version": SCHEMA_VERSION,
            "target": str(source),
            "source": {"resolved": str(source), "git": git_metadata},
            "inventory": {
                "status": "complete",
                "entries_digest": final_digest,
                "entry_count": len(final_entries),
                "exclusions": final_exclusions,
                "errors": [],
            },
            "artifacts": artifact_records,
            "evidence_sources": sorted(evidence_sources, key=lambda item: item["path"]),
            "connected_contexts": contexts,
            "project_signals": {
                "manifests": sorted(manifests, key=lambda item: item["path"]),
                "ci": sorted(ci, key=lambda item: item["path"]),
                "nested_repository_boundaries": sorted(boundaries, key=lambda item: item["path"]),
                "top_level_entries": sorted(top_level_entries, key=lambda item: item["path"]),
            },
            "archive": (
                {
                    "status": "verified",
                    "path": str(published_archive),
                    "manifest": str(published_archive / "manifest.json"),
                    "manifest_sha256": manifest_digest,
                    "separation_verified": True,
                }
                if published_archive is not None
                else {
                    "status": "not_requested",
                    "path": None,
                    "manifest": None,
                    "manifest_sha256": None,
                    "separation_verified": None,
                }
            ),
            "source_mutation_check": {
                "status": "metadata_unchanged",
                "method": "stable path/type/mode/size/mtime/device/inode comparison",
                "before_digest": before_digest,
                "after_digest": final_digest,
                "changed_paths": [],
            },
            "recommendation_gate": {
                "status": "blocked",
                "blocking_context_ids": blocking_ids,
                "reasons": gate_reasons,
            },
            "recommendations": None,
        }
    except BaseException:
        if published_archive is not None and published_archive_identity is not None:
            remove_owned_tree(published_archive, published_archive_identity)
        raise


def markdown_report(report: dict[str, Any]) -> str:
    archive = report["archive"]
    archive_label = (
        f"`{archive['path']}` ({archive['status']})"
        if archive["path"] is not None
        else "not requested; rerun with explicit `--archive-dir` before recommendation"
    )
    lines = [
        "# Existing Project Inspection",
        "",
        f"- **Target:** `{report['target']}`",
        f"- **Archive:** {archive_label}",
        f"- **Source mutation check:** {report['source_mutation_check']['status']}",
        "",
        "## Agentic Artifacts",
        "",
    ]
    artifacts = report["artifacts"]
    if artifacts:
        lines.extend(
            f"- `{item['path']}` — {item['kind']}, {item['status']}" for item in artifacts
        )
    else:
        lines.append("- None discovered.")

    lines.extend(["", "## Connected Contexts", ""])
    contexts = report["connected_contexts"]
    if contexts:
        for context in contexts:
            sources = ", ".join(f"`{path}`" for path in context["source_paths"])
            lines.append(f"- {context['url']} — pending authority/access review; found in {sources}")
    else:
        lines.append("- No URL contexts discovered; repository-wide authority confirmation is still pending.")

    signals = report["project_signals"]
    lines.extend(["", "## Repository Evidence", ""])
    evidence = report["evidence_sources"]
    if evidence:
        lines.extend(
            f"- `{item['path']}` — {', '.join(item['roles'])}" for item in evidence
        )
    else:
        lines.append("- No selected evidence sources discovered.")
    lines.extend(["", "## Project Signals", ""])
    lines.append(
        "- Manifests: "
        + (", ".join(f"`{item['path']}`" for item in signals["manifests"]) or "none")
    )
    lines.append(
        "- CI: " + (", ".join(f"`{item['path']}`" for item in signals["ci"]) or "none")
    )

    lines.extend(["", "## Recommendation Gate", "", "**Blocked.**", ""])
    lines.extend(f"- {reason}" for reason in report["recommendation_gate"]["reasons"])
    lines.extend(
        [
            "",
            "No alignment recommendation was generated, and no source files were changed.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    try:
        source = validate_source(args.target)
        archive = choose_archive_path(source, args.archive_dir) if args.archive_dir else None
        report = build_report(source, archive)
        if args.output_format == "json":
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(markdown_report(report), end="")
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
