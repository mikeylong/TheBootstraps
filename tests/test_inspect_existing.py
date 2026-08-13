"""Public-behavior tests for existing-project inspection and archival.

The suite invokes only the command-line interface. It deliberately treats
inspection as read-only and archival as a byte-preserving, manifest-backed
operation rather than importing implementation helpers.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INSPECTOR = REPOSITORY_ROOT / "scripts" / "inspect_existing_project.py"
RESOLVED_TEMP_ROOT = Path(tempfile.gettempdir()).resolve()

INSPECTOR_MODULE_NAME = "thebootstraps_existing_project_inspector"
INSPECTOR_SPEC = importlib.util.spec_from_file_location(INSPECTOR_MODULE_NAME, INSPECTOR)
if INSPECTOR_SPEC is None or INSPECTOR_SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"Could not load inspector module: {INSPECTOR}")
INSPECTOR_MODULE = importlib.util.module_from_spec(INSPECTOR_SPEC)
sys.modules[INSPECTOR_MODULE_NAME] = INSPECTOR_MODULE
INSPECTOR_SPEC.loader.exec_module(INSPECTOR_MODULE)


def isolated_temporary_directory() -> tempfile.TemporaryDirectory[str]:
    """Create fixtures below one canonical temp root.

    Resolving the shared root once prevents macOS ``/var`` versus
    ``/private/var`` aliases from making containment assertions lexical.
    """

    return tempfile.TemporaryDirectory(dir=RESOLVED_TEMP_ROOT)


def run_inspector(target: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the inspector through its supported command-line interface."""

    return subprocess.run(
        [sys.executable, str(INSPECTOR), str(target), *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def diagnostic(result: subprocess.CompletedProcess[str]) -> str:
    """Return the final non-empty diagnostic emitted by a rejected command."""

    output = result.stderr.strip() or result.stdout.strip()
    return output.splitlines()[-1] if output else ""


def tree_snapshot(root: Path) -> tuple[tuple[str, str, int, object], ...]:
    """Describe a tree without following symlinks or depending on timestamps."""

    if not os.path.lexists(root):
        return ((".", "missing", 0, None),)

    entries: list[tuple[str, str, int, object]] = []

    def visit(path: Path, relative_path: str) -> None:
        metadata = path.lstat()
        mode = stat.S_IMODE(metadata.st_mode)
        if stat.S_ISLNK(metadata.st_mode):
            entries.append((relative_path, "symlink", mode, os.readlink(path)))
            return
        if stat.S_ISDIR(metadata.st_mode):
            entries.append((relative_path, "directory", mode, None))
            for child in sorted(path.iterdir(), key=lambda item: item.name):
                child_relative = (
                    child.name if relative_path == "." else f"{relative_path}/{child.name}"
                )
                visit(child, child_relative)
            return
        if stat.S_ISREG(metadata.st_mode):
            entries.append((relative_path, "file", mode, path.read_bytes()))
            return
        entries.append((relative_path, "other", mode, metadata.st_mode))

    visit(root, ".")
    return tuple(entries)


def reported_paths(items: object) -> set[str]:
    """Return paths from a public list of path strings or path records."""

    if not isinstance(items, list):
        raise AssertionError(f"expected a list of paths, got {type(items).__name__}")
    paths: set[str] = set()
    for item in items:
        if isinstance(item, str):
            paths.add(item)
            continue
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            paths.add(item["path"])
            continue
        raise AssertionError(f"path entry has no public path: {item!r}")
    return paths


class ExistingProjectInspectorTests(unittest.TestCase):
    maxDiff = None

    def assert_success(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(
            result.returncode,
            0,
            msg=f"command failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def parse_json_report(self, result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        self.assert_success(result)
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            self.fail(f"inspector did not emit JSON: {error}\nstdout:\n{result.stdout}")
        self.assertIsInstance(report, dict)
        return report

    def create_representative_repository(self, root: Path) -> Path:
        """Create a repository-shaped fixture with agent and project signals."""

        target = root / "existing-project"
        (target / ".github/workflows").mkdir(parents=True)
        (target / ".agents/skills/review-change/agents").mkdir(parents=True)
        (target / ".agents/context").mkdir(parents=True)
        (target / "docs/adr").mkdir(parents=True)
        (target / "agents").mkdir(parents=True)

        shared_url = "https://github.com/acme/example/issues/42"
        figma_url = "https://www.figma.com/design/abc123/Existing-Project"
        (target / "AGENTS.md").write_text(
            "# Repository instructions\n"
            f"Use the governing issue at {shared_url}.\n",
            encoding="utf-8",
        )
        (target / "CLAUDE.md").write_text(
            "# Additional agent instructions\n"
            f"The interface source is {figma_url}.\n",
            encoding="utf-8",
        )
        (target / ".github/copilot-instructions.md").write_text(
            "Preserve public behavior and run the verified test command.\n",
            encoding="utf-8",
        )
        (target / "agents/openai.yaml").write_text(
            "interface:\n  display_name: Existing Project\n",
            encoding="utf-8",
        )
        (target / ".agents/skills/review-change/SKILL.md").write_text(
            "---\n"
            "name: review-change\n"
            "description: Review a bounded repository change.\n"
            "---\n\n"
            "# Review Change\n",
            encoding="utf-8",
        )
        (target / ".agents/skills/review-change/agents/openai.yaml").write_text(
            "interface:\n  display_name: Review Change\n",
            encoding="utf-8",
        )
        (target / ".agents/context/CURRENT.md").write_text(
            "# Current\n\nOutcome now: inspect before changing.\n",
            encoding="utf-8",
        )
        (target / "docs/adr/0001-context-authority.md").write_text(
            "# Context authority\n\n"
            f"The governing implementation issue is {shared_url}.\n",
            encoding="utf-8",
        )
        (target / "package.json").write_text(
            '{"name": "existing-project", "scripts": {"test": "node --test"}}\n',
            encoding="utf-8",
        )
        (target / "pyproject.toml").write_text(
            "[project]\nname = \"existing-project\"\nversion = \"0.1.0\"\n",
            encoding="utf-8",
        )
        (target / ".github/workflows/test.yml").write_text(
            "name: test\non: [push]\njobs: {}\n",
            encoding="utf-8",
        )
        return target

    def test_json_inventory_reports_artifacts_contexts_signals_and_blocked_gate(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory).resolve()
            target = self.create_representative_repository(fixture_root)

            report = self.parse_json_report(run_inspector(target, "--format", "json"))

            artifact_paths = reported_paths(report.get("artifacts"))
            expected_artifacts = {
                "AGENTS.md",
                "CLAUDE.md",
                ".github/copilot-instructions.md",
                "agents/openai.yaml",
                ".agents/skills/review-change/SKILL.md",
                ".agents/skills/review-change/agents/openai.yaml",
                ".agents/context/CURRENT.md",
                "docs/adr/0001-context-authority.md",
            }
            self.assertTrue(
                expected_artifacts.issubset(artifact_paths),
                f"missing artifact paths: {sorted(expected_artifacts - artifact_paths)}",
            )

            contexts = report.get("connected_contexts")
            self.assertIsInstance(contexts, list)
            contexts_by_url = {entry["url"]: entry for entry in contexts}
            self.assertEqual(len(contexts_by_url), len(contexts), "connected URLs were duplicated")

            shared_url = "https://github.com/acme/example/issues/42"
            figma_url = "https://www.figma.com/design/abc123/Existing-Project"
            self.assertEqual(set(contexts_by_url), {shared_url, figma_url})
            self.assertEqual(
                set(contexts_by_url[shared_url]["source_paths"]),
                {"AGENTS.md", "docs/adr/0001-context-authority.md"},
            )
            self.assertEqual(contexts_by_url[figma_url]["source_paths"], ["CLAUDE.md"])
            for context in contexts:
                self.assertTrue(context.get("governs"))
                self.assertTrue(context.get("relevance"))
                self.assertTrue(context.get("expected_owner"))
                self.assertIn("freshness_signal", context)
                self.assertIn("acquisition_evidence", context)
                self.assertTrue(context.get("required_disposition"))

            signals = report.get("project_signals")
            self.assertIsInstance(signals, dict)
            self.assertTrue(
                {"package.json", "pyproject.toml"}.issubset(
                    reported_paths(signals.get("manifests"))
                )
            )
            self.assertIn(
                ".github/workflows/test.yml",
                reported_paths(signals.get("ci")),
            )

            gate = report.get("recommendation_gate")
            self.assertIsInstance(gate, dict)
            self.assertEqual(gate.get("status"), "blocked")
            self.assertRegex(json.dumps(gate).lower(), r"context")

    def test_default_inspection_writes_nothing_and_does_not_create_archive(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory).resolve()
            target = self.create_representative_repository(fixture_root)
            before = tree_snapshot(target)
            before_fixture = tree_snapshot(fixture_root)

            result = run_inspector(target, "--format", "json")

            report = self.parse_json_report(result)
            self.assertEqual(tree_snapshot(target), before)
            self.assertEqual(tree_snapshot(fixture_root), before_fixture)
            archive = report.get("archive")
            self.assertIsInstance(archive, dict)
            self.assertEqual(archive.get("status"), "not_requested")
            self.assertIsNone(archive.get("path"))
            self.assertRegex(json.dumps(report["recommendation_gate"]).lower(), r"archive")

    def test_markdown_report_has_artifact_context_and_gate_sections(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory).resolve()
            target = self.create_representative_repository(fixture_root)

            result = run_inspector(target, "--format", "markdown")

            self.assert_success(result)
            self.assertRegex(result.stdout, r"(?im)^#{1,6}\s+.*artifacts?\b")
            self.assertRegex(result.stdout, r"(?im)^#{1,6}\s+.*connected contexts?\b")
            self.assertRegex(result.stdout, r"(?im)^#{1,6}\s+.*recommendation gate\b")
            self.assertRegex(result.stdout, r"(?i)\bblocked\b")

    def test_rejects_nonexistent_file_and_symlink_targets_without_mutation(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory).resolve()
            valid_target = self.create_representative_repository(fixture_root)
            file_target = fixture_root / "not-a-directory"
            file_target.write_text("ordinary file\n", encoding="utf-8")
            missing_target = fixture_root / "missing-project"
            linked_target = fixture_root / "linked-project"
            try:
                linked_target.symlink_to(valid_target, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symlinks are unavailable: {error}")

            cases = {
                "nonexistent": missing_target,
                "ordinary file": file_target,
                "symlink": linked_target,
            }
            for label, target in cases.items():
                with self.subTest(target=label):
                    before = tree_snapshot(fixture_root)
                    result = run_inspector(target, "--format", "json")
                    self.assertNotEqual(result.returncode, 0)
                    self.assertTrue(diagnostic(result))
                    self.assertEqual(tree_snapshot(fixture_root), before)

    def test_archive_destination_must_be_new_and_outside_source(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory).resolve()
            target = self.create_representative_repository(fixture_root)

            inside_target = target / "agent-artifact-archive"
            before = tree_snapshot(fixture_root)
            result = run_inspector(target, "--archive-dir", str(inside_target))
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(diagnostic(result))
            self.assertEqual(tree_snapshot(fixture_root), before)

            for kind in ("directory", "file"):
                with self.subTest(existing_archive=kind):
                    existing_archive = fixture_root / f"existing-{kind}"
                    if kind == "directory":
                        existing_archive.mkdir()
                        (existing_archive / "sentinel.txt").write_text(
                            "preserve me\n", encoding="utf-8"
                        )
                    else:
                        existing_archive.write_text("preserve me\n", encoding="utf-8")
                    before = tree_snapshot(fixture_root)
                    result = run_inspector(
                        target,
                        "--archive-dir",
                        str(existing_archive),
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertTrue(diagnostic(result))
                    self.assertEqual(tree_snapshot(fixture_root), before)

    def test_archive_copies_regular_artifacts_byte_for_byte_with_hash_manifest(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory).resolve()
            target = fixture_root / "existing-project"
            (target / ".agents/skills/example").mkdir(parents=True)
            agent_bytes = b"# Agent instructions\r\n\r\nPreserve these bytes.\r\n"
            skill_bytes = (
                b"---\nname: example\ndescription: Example local workflow.\n---\n\n# Example\n"
            )
            (target / "AGENTS.md").write_bytes(agent_bytes)
            (target / ".agents/skills/example/SKILL.md").write_bytes(skill_bytes)
            archive = fixture_root / "agent-artifact-archive"
            before = tree_snapshot(target)

            result = run_inspector(
                target,
                "--format",
                "json",
                "--archive-dir",
                str(archive),
            )

            self.parse_json_report(result)
            self.assertEqual(tree_snapshot(target), before)
            manifest_path = archive / "manifest.json"
            self.assertTrue(manifest_path.is_file(), "archive has no manifest.json")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            entries = manifest.get("artifacts")
            self.assertIsInstance(entries, list)
            entries_by_path = {entry["path"]: entry for entry in entries}

            expected = {
                "AGENTS.md": agent_bytes,
                ".agents/skills/example/SKILL.md": skill_bytes,
            }
            for source_path, expected_bytes in expected.items():
                with self.subTest(source_path=source_path):
                    entry = entries_by_path[source_path]
                    self.assertEqual(entry.get("kind"), "file")
                    self.assertEqual(entry.get("status"), "copied")
                    self.assertEqual(entry.get("sha256"), hashlib.sha256(expected_bytes).hexdigest())
                    self.assertEqual(entry.get("size"), len(expected_bytes))
                    archived_relative = Path(entry["archive_path"])
                    self.assertFalse(archived_relative.is_absolute())
                    self.assertNotIn("..", archived_relative.parts)
                    archived_file = archive / archived_relative
                    self.assertTrue(archived_file.is_file())
                    self.assertFalse(archived_file.is_symlink())
                    self.assertEqual(archived_file.read_bytes(), expected_bytes)

    def test_archive_records_symlinks_and_excludes_secret_like_artifacts(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory).resolve()
            target = fixture_root / "existing-project"
            (target / ".agents/skills/linked").mkdir(parents=True)
            (target / ".agents/context").mkdir(parents=True)
            (target / "AGENTS.md").write_text("# Safe instructions\n", encoding="utf-8")

            secret_value = "sk-test-fixture-secret-1234567890"
            environment_secret = "fixture-token-value-0987654321"
            (target / "CLAUDE.md").write_text(
                f"# Unsafe instructions\nOPENAI_API_KEY={secret_value}\n",
                encoding="utf-8",
            )
            (target / ".agents/context/.env").write_text(
                f"SERVICE_TOKEN={environment_secret}\n",
                encoding="utf-8",
            )
            json_secret = "ghp_abcdefghijklmnopqrstuvwxyz123456"
            (target / ".agents/context/settings.json").write_text(
                f'{{"access_token": "{json_secret}"}}\n',
                encoding="utf-8",
            )

            external = fixture_root / "outside-skill.md"
            external_bytes = b"EXTERNAL-SYMLINK-CONTENT-MUST-NOT-BE-ARCHIVED\n"
            external.write_bytes(external_bytes)
            linked_skill = target / ".agents/skills/linked/SKILL.md"
            try:
                linked_skill.symlink_to(external)
            except OSError as error:
                self.skipTest(f"symlinks are unavailable: {error}")

            archive = fixture_root / "agent-artifact-archive"
            before = tree_snapshot(target)
            result = run_inspector(target, "--archive-dir", str(archive))

            self.parse_json_report(result)
            self.assertEqual(tree_snapshot(target), before)
            self.assertEqual(external.read_bytes(), external_bytes)

            manifest_path = archive / "manifest.json"
            manifest_bytes = manifest_path.read_bytes()
            manifest = json.loads(manifest_bytes)
            entries_by_path = {entry["path"]: entry for entry in manifest["artifacts"]}

            symlink_entry = entries_by_path[".agents/skills/linked/SKILL.md"]
            self.assertEqual(symlink_entry.get("kind"), "symlink")
            self.assertEqual(symlink_entry.get("status"), "recorded")
            self.assertEqual(symlink_entry.get("link_target"), str(external))

            for secret_path in (
                "CLAUDE.md",
                ".agents/context/.env",
                ".agents/context/settings.json",
            ):
                with self.subTest(secret_path=secret_path):
                    entry = entries_by_path[secret_path]
                    self.assertEqual(entry.get("status"), "excluded")
                    self.assertRegex(str(entry.get("reason", "")), r"(?i)secret|credential")
                    self.assertNotIn("archive_path", entry)

            all_archived_bytes = b"".join(
                path.read_bytes()
                for path in archive.rglob("*")
                if path.is_file() and not path.is_symlink()
            )
            self.assertNotIn(secret_value.encode("utf-8"), all_archived_bytes)
            self.assertNotIn(environment_secret.encode("utf-8"), all_archived_bytes)
            self.assertNotIn(json_secret.encode("utf-8"), all_archived_bytes)
            self.assertNotIn(external_bytes.strip(), all_archived_bytes)
            self.assertFalse(
                any(path.is_symlink() for path in archive.rglob("*")),
                "archive recreated a source symlink instead of recording it",
            )

    @unittest.skipUnless(os.name == "posix", "permission fixture requires POSIX modes")
    def test_failed_archive_leaves_no_destination_or_staging_leftovers(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory).resolve()
            target = fixture_root / "existing-project"
            target.mkdir()
            (target / "AGENTS.md").write_text("# Agent instructions\n", encoding="utf-8")
            restricted_parent = fixture_root / "restricted-archive-parent"
            restricted_parent.mkdir()
            restricted_parent.chmod(0o500)
            archive = restricted_parent / "agent-artifact-archive"
            before_source = tree_snapshot(target)
            before_archive_parent = tree_snapshot(restricted_parent)

            try:
                if os.access(restricted_parent, os.W_OK):
                    self.skipTest("current privileges bypass unwritable-directory fixture")
                result = run_inspector(target, "--archive-dir", str(archive))
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(diagnostic(result))
                self.assertFalse(os.path.lexists(archive))
                self.assertEqual(tree_snapshot(target), before_source)
                self.assertEqual(tree_snapshot(restricted_parent), before_archive_parent)
            finally:
                restricted_parent.chmod(0o700)

    @unittest.skipUnless(shutil.which("git"), "git is required for fsmonitor isolation")
    def test_repository_fsmonitor_is_not_executed(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory).resolve()
            target = fixture_root / "existing-project"
            target.mkdir()
            (target / "AGENTS.md").write_text("# Safe instructions\n", encoding="utf-8")
            marker = target / "FS_MONITOR_EXECUTED"
            hook = fixture_root / "fsmonitor-hook.sh"
            hook.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 0\n", encoding="utf-8")
            hook.chmod(0o700)
            subprocess.run(
                ["git", "init", str(target)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(target), "config", "core.fsmonitor", str(hook)],
                check=True,
                capture_output=True,
                text=True,
            )

            before = tree_snapshot(target)
            report = self.parse_json_report(run_inspector(target, "--format", "json"))

            self.assertFalse(marker.exists(), "inspection executed repository-controlled fsmonitor")
            self.assertEqual(tree_snapshot(target), before)
            self.assertEqual(report["source_mutation_check"]["status"], "metadata_unchanged")

    def test_cleanup_refuses_identity_swapped_archive(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory).resolve()
            target = fixture_root / "existing-project"
            target.mkdir()
            (target / "AGENTS.md").write_text("# Safe instructions\n", encoding="utf-8")
            archive = fixture_root / "agentic-archive"
            unrelated = fixture_root / "unrelated"
            unrelated.mkdir()
            (unrelated / "DO_NOT_DELETE").write_text("preserve\n", encoding="utf-8")
            displaced = fixture_root / "displaced-owned-archive"
            original_fsync = INSPECTOR_MODULE.fsync_directory
            injected = False

            def fsync_with_swap(path: Path) -> None:
                nonlocal injected
                if (
                    not injected
                    and path == archive.parent
                    and (archive / "manifest.json").is_file()
                ):
                    injected = True
                    archive.rename(displaced)
                    unrelated.rename(archive)
                    raise RuntimeError("injected post-publication failure")
                original_fsync(path)

            with mock.patch.object(
                INSPECTOR_MODULE,
                "fsync_directory",
                side_effect=fsync_with_swap,
            ):
                with self.assertRaisesRegex(RuntimeError, "identity changed"):
                    INSPECTOR_MODULE.build_report(target, archive)

            self.assertTrue((archive / "DO_NOT_DELETE").is_file())
            self.assertTrue((displaced / "manifest.json").is_file())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
