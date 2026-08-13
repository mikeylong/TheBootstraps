"""Behavioral contract tests for the scaffold generator.

The suite intentionally invokes the public command-line interface. This keeps the
tests independent of the generator's internal planning and write helpers.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPOSITORY_ROOT / "scripts" / "bootstrap_ai_native_project.py"
RESOLVED_TEMP_ROOT = Path(tempfile.gettempdir()).resolve()


def isolated_temporary_directory() -> tempfile.TemporaryDirectory[str]:
    """Create fixtures below one canonical, symlink-free temp root."""

    return tempfile.TemporaryDirectory(dir=RESOLVED_TEMP_ROOT)

GENERATOR_MODULE_NAME = "thebootstraps_bootstrap_generator"
GENERATOR_SPEC = importlib.util.spec_from_file_location(GENERATOR_MODULE_NAME, GENERATOR)
if GENERATOR_SPEC is None or GENERATOR_SPEC.loader is None:  # pragma: no cover - import machinery failure
    raise RuntimeError(f"Could not load generator module: {GENERATOR}")
GENERATOR_MODULE = importlib.util.module_from_spec(GENERATOR_SPEC)
sys.modules[GENERATOR_MODULE_NAME] = GENERATOR_MODULE
GENERATOR_SPEC.loader.exec_module(GENERATOR_MODULE)

EXPECTED_FILES = {
    "README.md",
    "AGENTS.md",
    "CURRENT.md",
    "CONTEXT_MAP.md",
    "DECISIONS.md",
    "DESIGN.md",
    "specs/feature-spec.md",
    "specs/interface-contract.md",
    ".agents/skills/build-page/SKILL.md",
    ".agents/skills/build-page/examples.md",
    ".agents/skills/build-page/agents/openai.yaml",
    ".agents/skills/refactor-component/SKILL.md",
    ".agents/skills/refactor-component/checks.md",
    ".agents/skills/refactor-component/agents/openai.yaml",
    ".agents/skills/write-tests/SKILL.md",
    ".agents/skills/write-tests/agents/openai.yaml",
    "contracts/design-tokens.schema.json",
    "contracts/component-rules.json",
}

EXPECTED_DIRECTORIES = {
    "specs",
    ".agents",
    ".agents/skills",
    ".agents/skills/build-page",
    ".agents/skills/build-page/agents",
    ".agents/skills/refactor-component",
    ".agents/skills/refactor-component/agents",
    ".agents/skills/write-tests",
    ".agents/skills/write-tests/agents",
    "contracts",
    "plans",
    "tests",
}

SKILL_FILES = {
    "build-page": ".agents/skills/build-page/SKILL.md",
    "refactor-component": ".agents/skills/refactor-component/SKILL.md",
    "write-tests": ".agents/skills/write-tests/SKILL.md",
}

SKILL_INTERFACES = {
    "build-page": {
        "display_name": "Build Page",
        "short_description": "Build page-level UI from project contracts",
        "default_prompt": (
            "Use $build-page to implement the active page contract and report the validated checkpoint."
        ),
    },
    "refactor-component": {
        "display_name": "Refactor Component",
        "short_description": "Refactor components without breaking contracts",
        "default_prompt": (
            "Use $refactor-component to revise the active component while preserving its project contracts."
        ),
    },
    "write-tests": {
        "display_name": "Write Tests",
        "short_description": "Write focused tests from project contracts",
        "default_prompt": (
            "Use $write-tests to add focused tests for the active acceptance criteria and risks."
        ),
    },
}


def run_generator(target: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the generator using the same Python runtime as the tests."""

    return subprocess.run(
        [sys.executable, str(GENERATOR), str(target), *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def run_generator_with_umask(
    target: Path,
    umask: int,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    """Run the public CLI after setting a process-local umask."""

    wrapper = (
        "import os, runpy, sys; "
        "os.umask(int(sys.argv[1], 8)); "
        "script = sys.argv[2]; "
        "sys.argv = [script, *sys.argv[3:]]; "
        "runpy.run_path(script, run_name='__main__')"
    )
    return subprocess.run(
        [
            sys.executable,
            "-c",
            wrapper,
            f"{umask:o}",
            str(GENERATOR),
            str(target),
            *arguments,
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def diagnostic(result: subprocess.CompletedProcess[str]) -> str:
    """Return the stable final diagnostic line from a failed command."""

    output = result.stderr.strip() or result.stdout.strip()
    return output.splitlines()[-1] if output else ""


def available_codex_skill_validator() -> Path | None:
    """Find SkillSkill's dependency-free Codex validator when installed.

    Structural assertions remain the portable baseline. This optional lookup
    adds authoritative package validation on machines that have SkillSkill,
    without making that personal installation a suite dependency.
    """

    candidates: list[Path] = []
    configured_validator = os.environ.get("SKILLSKILL_VALIDATOR")
    if configured_validator:
        candidates.append(Path(configured_validator).expanduser())
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        candidates.append(Path(codex_home).expanduser() / "skills/skillskill/scripts/validate_skill.py")
    candidates.extend(
        (
            Path.home() / ".codex/skills/skillskill/scripts/validate_skill.py",
            Path.home() / ".agents/skills/skillskill/scripts/validate_skill.py",
        )
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def available_quick_skill_validator() -> Path | None:
    """Find the platform skill creator's quick validator when installed."""

    candidates: list[Path] = []
    configured_validator = os.environ.get("SKILL_QUICK_VALIDATOR")
    if configured_validator:
        candidates.append(Path(configured_validator).expanduser())
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        candidates.append(
            Path(codex_home).expanduser()
            / "skills/.system/skill-creator/scripts/quick_validate.py"
        )
    candidates.extend(
        (
            Path.home() / ".codex/skills/.system/skill-creator/scripts/quick_validate.py",
            Path.home() / ".agents/skills/.system/skill-creator/scripts/quick_validate.py",
        )
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def path_snapshot(root: Path) -> tuple[tuple[str, str, int, object], ...]:
    """Describe a tree without following symlinks.

    The representation includes path kind, mode, regular-file bytes, and link
    text. It is suitable for proving that a failed preflight left fixtures
    unchanged without depending on timestamps or inode allocation.
    """

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
                child_relative = child.name if relative_path == "." else f"{relative_path}/{child.name}"
                visit(child, child_relative)
            return
        if stat.S_ISREG(metadata.st_mode):
            entries.append((relative_path, "file", mode, path.read_bytes()))
            return
        entries.append((relative_path, "other", mode, metadata.st_mode))

    visit(root, ".")
    return tuple(entries)


class BootstrapGeneratorTests(unittest.TestCase):
    maxDiff = None

    def assert_success(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(
            result.returncode,
            0,
            msg=f"command failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def assert_rejected_without_changes(
        self,
        fixture_root: Path,
        target: Path,
        *arguments: str,
    ) -> subprocess.CompletedProcess[str]:
        before = path_snapshot(fixture_root)
        result = run_generator(target, *arguments)
        self.assertNotEqual(
            result.returncode,
            0,
            msg=f"unsafe fixture was accepted\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        self.assertTrue(diagnostic(result), "failure did not explain why preflight rejected the target")
        self.assertEqual(path_snapshot(fixture_root), before, "failed preflight mutated the fixture")
        return result

    def generate(self, target: Path, *arguments: str) -> None:
        result = run_generator(target, *arguments)
        self.assert_success(result)

    def test_clean_generation_has_exact_v2_structure(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            target = Path(temporary_directory) / "example-project"
            result = run_generator(target, "--project-name", "Example Project")
            self.assert_success(result)

            files = {
                path.relative_to(target).as_posix()
                for path in target.rglob("*")
                if path.is_file()
            }
            directories = {
                path.relative_to(target).as_posix()
                for path in target.rglob("*")
                if path.is_dir()
            }
            self.assertEqual(files, EXPECTED_FILES)
            self.assertEqual(directories, EXPECTED_DIRECTORIES)
            self.assertEqual(list((target / "plans").iterdir()), [])
            self.assertEqual(list((target / "tests").iterdir()), [])

    def test_dry_run_creates_nothing(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            target = fixture_root / "not-created"
            before = path_snapshot(fixture_root)

            result = run_generator(target, "--dry-run")

            self.assert_success(result)
            self.assertEqual(path_snapshot(fixture_root), before)
            self.assertFalse(os.path.lexists(target))

    def test_rerun_preserves_managed_and_unknown_ordinary_files(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            target = Path(temporary_directory) / "project"
            self.generate(target, "--project-name", "Example Project")
            managed_content = "# User-owned README\n"
            unknown_content = "Do not replace this file.\n"
            (target / "README.md").write_text(managed_content, encoding="utf-8")
            (target / "notes").mkdir()
            (target / "notes" / "user.txt").write_text(unknown_content, encoding="utf-8")

            result = run_generator(target, "--project-name", "Changed Project")

            self.assert_success(result)
            self.assertEqual((target / "README.md").read_text(encoding="utf-8"), managed_content)
            self.assertEqual((target / "notes" / "user.txt").read_text(encoding="utf-8"), unknown_content)

    def test_force_overwrites_managed_ordinary_files_only(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            target = Path(temporary_directory) / "project"
            self.generate(target, "--project-name", "Old Name")
            (target / "README.md").write_text("managed sentinel\n", encoding="utf-8")
            (target / "user-owned.txt").write_text("unknown sentinel\n", encoding="utf-8")

            result = run_generator(target, "--project-name", "New Name", "--force")

            self.assert_success(result)
            readme = (target / "README.md").read_text(encoding="utf-8")
            self.assertNotEqual(readme, "managed sentinel\n")
            self.assertIn("# New Name", readme)
            self.assertEqual((target / "user-owned.txt").read_text(encoding="utf-8"), "unknown sentinel\n")

    @unittest.skipUnless(os.name == "posix", "POSIX file-mode semantics required")
    def test_generated_files_honor_umask_and_force_preserves_existing_mode(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            target = Path(temporary_directory) / "project"

            result = run_generator_with_umask(target, 0o077)
            self.assert_success(result)
            readme = target / "README.md"
            self.assertEqual(stat.S_IMODE(readme.stat().st_mode), 0o600)

            readme.chmod(0o640)
            result = run_generator_with_umask(target, 0o077, "--force")
            self.assert_success(result)
            self.assertEqual(stat.S_IMODE(readme.stat().st_mode), 0o640)

    def test_atomic_create_race_preserves_new_sentinel_and_cleans_temporary_file(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            target = fixture_root / "README.md"
            sentinel_content = "competing create sentinel\n"
            real_lstat = GENERATOR_MODULE._lstat
            race_injected = False

            def lstat_then_create_sentinel(path: Path) -> os.stat_result | None:
                nonlocal race_injected
                metadata = real_lstat(path)
                if Path(path) == target and metadata is None and not race_injected:
                    target.write_text(sentinel_content, encoding="utf-8")
                    race_injected = True
                return metadata

            with mock.patch.object(GENERATOR_MODULE, "_lstat", side_effect=lstat_then_create_sentinel):
                with self.assertRaises(FileExistsError):
                    GENERATOR_MODULE._atomic_write(
                        target,
                        "generated content\n",
                        action="create",
                        existing_mode=None,
                    )

            self.assertTrue(race_injected)
            self.assertEqual(target.read_text(encoding="utf-8"), sentinel_content)
            self.assertEqual(
                [path.name for path in fixture_root.iterdir()],
                [target.name],
                "atomic create failure left a temporary file behind",
            )

    def test_forced_overwrite_inode_swap_aborts_without_clobbering_replacement(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            target = Path(temporary_directory) / "project"
            self.generate(target, "--project-name", "Example Project")
            readme = target / "README.md"
            readme.write_text("original managed sentinel\n", encoding="utf-8")
            plan = GENERATOR_MODULE.build_operation_plan(target, "Example Project", force=True)
            replacement_content = "replacement inode sentinel\n"
            displaced_readme = target.parent / "displaced-original-readme.md"
            real_lstat = GENERATOR_MODULE._lstat
            swap_injected = False

            def lstat_after_inode_swap(path: Path) -> os.stat_result | None:
                nonlocal swap_injected
                candidate = Path(path)
                if candidate == readme and not swap_injected:
                    readme.rename(displaced_readme)
                    readme.write_text(replacement_content, encoding="utf-8")
                    swap_injected = True
                return real_lstat(candidate)

            with mock.patch.object(GENERATOR_MODULE, "_lstat", side_effect=lstat_after_inode_swap):
                with self.assertRaisesRegex(FileExistsError, r"(?i)changed"):
                    GENERATOR_MODULE.execute_operation_plan(plan)

            self.assertTrue(swap_injected)
            self.assertEqual(readme.read_text(encoding="utf-8"), replacement_content)
            self.assertNotIn("# Example Project", readme.read_text(encoding="utf-8"))
            self.assertEqual(
                displaced_readme.read_text(encoding="utf-8"),
                "original managed sentinel\n",
            )
            displaced_readme.unlink()
            self.assertFalse(displaced_readme.exists())
            unsafe_leftovers = [
                path.name
                for path in target.iterdir()
                if path.name.endswith(".tmp") or ".backup-" in path.name
            ]
            self.assertEqual(unsafe_leftovers, [])

    @unittest.skipUnless(os.name == "posix", "POSIX file-mode semantics required")
    def test_atomic_write_keeps_temporary_private_until_content_is_written(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            target = fixture_root / "public.txt"
            observed_write_modes: list[int] = []
            real_fdopen = GENERATOR_MODULE.os.fdopen

            class ModeObservingHandle:
                def __init__(self, handle: object) -> None:
                    self.handle = handle

                def __enter__(self) -> "ModeObservingHandle":
                    return self

                def __exit__(self, *arguments: object) -> object:
                    return self.handle.__exit__(*arguments)

                def write(self, content: str) -> int:
                    observed_write_modes.append(
                        stat.S_IMODE(os.fstat(self.handle.fileno()).st_mode)
                    )
                    return self.handle.write(content)

                def flush(self) -> None:
                    self.handle.flush()

                def fileno(self) -> int:
                    return self.handle.fileno()

            def observing_fdopen(*arguments: object, **kwargs: object) -> ModeObservingHandle:
                return ModeObservingHandle(real_fdopen(*arguments, **kwargs))

            previous_umask = os.umask(0)
            try:
                with mock.patch.object(GENERATOR_MODULE.os, "fdopen", side_effect=observing_fdopen):
                    GENERATOR_MODULE._atomic_write(
                        target,
                        "public generated content\n",
                        action="create",
                        existing_mode=None,
                    )
            finally:
                os.umask(previous_umask)

            self.assertEqual(observed_write_modes, [0o600])
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o666)
            self.assertEqual(target.read_text(encoding="utf-8"), "public generated content\n")
            self.assertEqual([path.name for path in fixture_root.iterdir()], [target.name])

    def test_atomic_overwrite_interrupt_after_backup_rename_restores_public_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            target = fixture_root / "README.md"
            original_content = "original public content\n"
            target.write_text(original_content, encoding="utf-8")
            metadata = target.lstat()
            existing_mode = stat.S_IMODE(metadata.st_mode)
            existing_identity = (metadata.st_dev, metadata.st_ino)
            real_rename = Path.rename
            interruption_injected = False

            def rename_then_interrupt(path: Path, destination: Path) -> Path:
                nonlocal interruption_injected
                result = real_rename(path, destination)
                destination_path = Path(destination)
                if (
                    path == target
                    and destination_path.parent.name.startswith(f".{target.name}.backup-")
                    and not interruption_injected
                ):
                    interruption_injected = True
                    raise KeyboardInterrupt("injected after public file backup rename")
                return result

            with mock.patch.object(Path, "rename", new=rename_then_interrupt):
                with self.assertRaisesRegex(
                    KeyboardInterrupt,
                    r"injected after public file backup rename",
                ):
                    GENERATOR_MODULE._atomic_write(
                        target,
                        "generated replacement content\n",
                        action="overwrite",
                        existing_mode=existing_mode,
                        existing_identity=existing_identity,
                    )

            self.assertTrue(interruption_injected)
            self.assertEqual(target.read_text(encoding="utf-8"), original_content)
            self.assertNotIn("generated replacement content", target.read_text(encoding="utf-8"))
            self.assertEqual(
                [path.name for path in fixture_root.iterdir()],
                [target.name],
                "interrupted overwrite left a temporary file or backup directory behind",
            )

    def test_file_symlink_is_rejected_by_dry_run_and_execution_with_or_without_force(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            target = fixture_root / "project"
            target.mkdir()
            external_file = fixture_root / "external-readme.md"
            external_file.write_text("external sentinel\n", encoding="utf-8")
            try:
                (target / "README.md").symlink_to(external_file)
            except OSError as error:
                self.skipTest(f"symlinks are unavailable: {error}")

            for arguments in ((), ("--force",), ("--dry-run",), ("--force", "--dry-run")):
                with self.subTest(arguments=arguments):
                    self.assert_rejected_without_changes(fixture_root, target, *arguments)
                    self.assertEqual(external_file.read_text(encoding="utf-8"), "external sentinel\n")

    def test_directory_symlink_is_rejected_by_dry_run_and_execution_with_or_without_force(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            target = fixture_root / "project"
            external_directory = fixture_root / "external-contracts"
            target.mkdir()
            external_directory.mkdir()
            (external_directory / "sentinel.txt").write_text("external sentinel\n", encoding="utf-8")
            try:
                (target / "contracts").symlink_to(external_directory, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symlinks are unavailable: {error}")

            for arguments in ((), ("--force",), ("--dry-run",), ("--force", "--dry-run")):
                with self.subTest(arguments=arguments):
                    self.assert_rejected_without_changes(fixture_root, target, *arguments)
                    self.assertEqual(
                        (external_directory / "sentinel.txt").read_text(encoding="utf-8"),
                        "external sentinel\n",
                    )

    def test_collision_diagnostic_matches_dry_run_and_execution_without_partial_mutation(self) -> None:
        for force_arguments in ((), ("--force",)):
            with self.subTest(force=bool(force_arguments)):
                with isolated_temporary_directory() as temporary_directory:
                    fixture_root = Path(temporary_directory)
                    target = fixture_root / "project"
                    target.mkdir()
                    # This collision appears late enough in the declared tree to catch
                    # implementations that start creating earlier directories first.
                    (target / "contracts").write_text("user-owned collision\n", encoding="utf-8")
                    (target / "unknown.txt").write_text("unknown sentinel\n", encoding="utf-8")

                    dry_run = self.assert_rejected_without_changes(
                        fixture_root,
                        target,
                        *force_arguments,
                        "--dry-run",
                    )
                    execution = self.assert_rejected_without_changes(fixture_root, target, *force_arguments)

                    self.assertEqual(diagnostic(dry_run), diagnostic(execution))

    def test_target_root_symlink_is_always_rejected_without_mutation(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            real_target = fixture_root / "real-target"
            real_target.mkdir()
            (real_target / "sentinel.txt").write_text("external sentinel\n", encoding="utf-8")
            target = fixture_root / "design-system"
            try:
                target.symlink_to(real_target, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symlinks are unavailable: {error}")

            for arguments in ((), ("--force",), ("--dry-run",), ("--force", "--dry-run")):
                with self.subTest(arguments=arguments):
                    self.assert_rejected_without_changes(fixture_root, target, *arguments)

    def test_default_project_name_splits_word_separators_without_splitting_lowercase_s(self) -> None:
        cases = {
            "design-system": "Design System",
            "design_system": "Design System",
            "design system": "Design System",
            "sass-service": "Sass Service",
        }
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            for directory_name, expected_name in cases.items():
                with self.subTest(directory_name=directory_name):
                    target = fixture_root / directory_name
                    self.generate(target)
                    readme = (target / "README.md").read_text(encoding="utf-8")
                    self.assertEqual(readme.splitlines()[0], f"# {expected_name}")

    def test_generated_json_is_parseable(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            target = Path(temporary_directory) / "project"
            self.generate(target)

            for relative_path in sorted(path for path in EXPECTED_FILES if path.endswith(".json")):
                with self.subTest(path=relative_path):
                    value = json.loads((target / relative_path).read_text(encoding="utf-8"))
                    self.assertIsInstance(value, dict)

    def test_context_files_expose_required_fields_and_cross_links(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            target = Path(temporary_directory) / "project"
            self.generate(target)

            current = (target / "CURRENT.md").read_text(encoding="utf-8")
            for heading in (
                "Outcome Now",
                "Definition of Done",
                "Active Decisions",
                "Completed",
                "In Progress",
                "Next Action",
                "Open Questions and Blockers",
                "First Useful Checkpoint",
                "Stop or Return Condition",
                "Authorization and Approval Boundaries",
                "Active Plan",
            ):
                with self.subTest(file="CURRENT.md", heading=heading):
                    self.assertRegex(current, rf"(?im)^##+\s+{re.escape(heading)}\s*$")
            self.assertIn("CONTEXT_MAP.md", current)
            self.assertIn("DECISIONS.md", current)
            self.assertIn("plans/", current)

            context_map = (target / "CONTEXT_MAP.md").read_text(encoding="utf-8")
            for field in ("Path or URL", "What It Governs", "Authority", "When to Read", "Owner or Freshness"):
                with self.subTest(file="CONTEXT_MAP.md", field=field):
                    self.assertRegex(context_map, rf"(?i)\b{re.escape(field)}\b")
            for link in ("README.md", "AGENTS.md", "CURRENT.md", "DECISIONS.md", "DESIGN.md", "specs/", "contracts/"):
                with self.subTest(file="CONTEXT_MAP.md", link=link):
                    self.assertIn(link, context_map)

            decisions = (target / "DECISIONS.md").read_text(encoding="utf-8")
            for field in (
                "Date or Sequence",
                "Decision",
                "Reason and Evidence",
                "Scope",
                "Status When Recorded",
                "Supersedes",
            ):
                with self.subTest(file="DECISIONS.md", field=field):
                    self.assertRegex(decisions, rf"(?i)\b{re.escape(field)}\b")
            self.assertIn("CURRENT.md", decisions)

            readme = (target / "README.md").read_text(encoding="utf-8")
            for link in (
                "AGENTS.md",
                "CURRENT.md",
                "CONTEXT_MAP.md",
                "DECISIONS.md",
                "DESIGN.md",
                "specs/",
                ".agents/skills/",
                "contracts/",
                "plans/",
                "tests/",
            ):
                with self.subTest(file="README.md", link=link):
                    self.assertIn(link, readme)

            agents = (target / "AGENTS.md").read_text(encoding="utf-8")
            for link in (
                "CURRENT.md",
                "CONTEXT_MAP.md",
                "DECISIONS.md",
                "DESIGN.md",
                "specs/",
                ".agents/skills/",
                "contracts/",
                "plans/",
            ):
                with self.subTest(file="AGENTS.md", link=link):
                    self.assertIn(link, agents)

    def test_generated_skills_have_valid_portable_structure_and_context_links(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            target = Path(temporary_directory) / "project"
            self.generate(target)

            for expected_name, relative_path in SKILL_FILES.items():
                with self.subTest(skill=expected_name):
                    content = (target / relative_path).read_text(encoding="utf-8")
                    self.assertTrue(content.startswith("---\n"))
                    frontmatter_end = content.find("\n---\n", 4)
                    self.assertGreater(frontmatter_end, 4, "skill frontmatter is not closed")
                    frontmatter = content[4:frontmatter_end]
                    name_match = re.search(r"(?m)^name:\s*([^\n]+?)\s*$", frontmatter)
                    description_match = re.search(r"(?m)^description:\s*([^\n]+?)\s*$", frontmatter)
                    self.assertIsNotNone(name_match, "skill is missing a name")
                    self.assertIsNotNone(description_match, "skill is missing a description")
                    self.assertEqual(name_match.group(1).strip(" '\""), expected_name)
                    self.assertRegex(name_match.group(1).strip(" '\""), r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
                    description = description_match.group(1).strip(" '\"")
                    self.assertTrue(description)
                    self.assertLessEqual(len(description), 1024)
                    self.assertRegex(content[frontmatter_end + 5 :], r"(?m)^#\s+\S")
                    self.assertIn("CURRENT.md", content)
                    self.assertIn("CONTEXT_MAP.md", content)
                    self.assertIn("DECISIONS.md", content)

                    metadata_path = target / Path(relative_path).parent / "agents/openai.yaml"
                    metadata_lines = metadata_path.read_text(encoding="utf-8").splitlines()
                    self.assertEqual(metadata_lines[0], "interface:")
                    interface: dict[str, str] = {}
                    for line in metadata_lines[1:]:
                        if not line.strip():
                            continue
                        entry = re.fullmatch(r"  ([a-z_]+):\s*(\"(?:[^\"\\]|\\.)*\")", line)
                        self.assertIsNotNone(entry, f"invalid quoted interface entry: {line!r}")
                        key = entry.group(1)
                        self.assertNotIn(key, interface, f"duplicate interface key: {key}")
                        interface[key] = json.loads(entry.group(2))

                    self.assertEqual(interface, SKILL_INTERFACES[expected_name])
                    self.assertTrue(interface["display_name"].strip())
                    self.assertGreaterEqual(len(interface["short_description"]), 25)
                    self.assertLessEqual(len(interface["short_description"]), 64)
                    self.assertIn(f"${expected_name}", interface["default_prompt"])

    def test_generated_skills_pass_authoritative_codex_validator_when_available(self) -> None:
        validator = available_codex_skill_validator()
        if validator is None:
            self.skipTest("SkillSkill Codex validator is not installed")

        with isolated_temporary_directory() as temporary_directory:
            target = Path(temporary_directory) / "project"
            self.generate(target)
            skill_directories = [str(target / Path(path).parent) for path in SKILL_FILES.values()]

            result = subprocess.run(
                [sys.executable, str(validator), "--expect-codex", *skill_directories],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            self.assertEqual(
                result.returncode,
                0,
                msg=(
                    "generated skills failed authoritative Codex validation"
                    f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
                ),
            )

    def test_generated_skills_pass_quick_validator_when_available(self) -> None:
        validator = available_quick_skill_validator()
        if validator is None:
            self.skipTest("platform quick skill validator is not installed")

        with isolated_temporary_directory() as temporary_directory:
            target = Path(temporary_directory) / "project"
            self.generate(target)

            for skill_name, relative_path in SKILL_FILES.items():
                with self.subTest(skill=skill_name):
                    skill_directory = target / Path(relative_path).parent
                    result = subprocess.run(
                        [sys.executable, str(validator), str(skill_directory)],
                        cwd=REPOSITORY_ROOT,
                        capture_output=True,
                        text=True,
                        timeout=30,
                        check=False,
                    )
                    self.assertEqual(
                        result.returncode,
                        0,
                        msg=(
                            f"generated skill {skill_name} failed platform quick validation"
                            f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
                        ),
                    )


if __name__ == "__main__":
    unittest.main()
