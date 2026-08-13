"""Regression tests for the local skill installer."""

from __future__ import annotations

import importlib.util
import io
import os
import shutil
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tests.test_bootstrap import diagnostic, isolated_temporary_directory, path_snapshot


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPOSITORY_ROOT / "scripts" / "install_skill.py"
SKILL_NAME = "bootstrap-ai-native-project"

INSTALLER_SPEC = importlib.util.spec_from_file_location("thebootstraps_install_skill", INSTALLER)
if INSTALLER_SPEC is None or INSTALLER_SPEC.loader is None:  # pragma: no cover - import machinery failure
    raise RuntimeError(f"Could not load installer module: {INSTALLER}")
INSTALLER_MODULE = importlib.util.module_from_spec(INSTALLER_SPEC)
INSTALLER_SPEC.loader.exec_module(INSTALLER_MODULE)


def run_installer(destination: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(INSTALLER), "--dest", str(destination), *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def run_fixture_installer(
    source: Path,
    destination: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    """Run the copied source package's public installer entrypoint."""

    return subprocess.run(
        [
            sys.executable,
            str(source / "scripts/install_skill.py"),
            "--dest",
            str(destination),
            *arguments,
        ],
        cwd=source,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def copy_source_package(destination: Path) -> Path:
    """Copy the source package into an isolated containment fixture."""

    return Path(
        shutil.copytree(
            REPOSITORY_ROOT,
            destination,
            ignore=shutil.ignore_patterns(".git", ".DS_Store", "__pycache__", "*.pyc"),
        )
    )


def invoke_install(root: Path, target: Path, *, force: bool, dry_run: bool) -> str:
    """Call the imported installer while capturing its user-facing receipt."""

    output = io.StringIO()
    with redirect_stdout(output):
        INSTALLER_MODULE.install(root, target, force=force, dry_run=dry_run)
    return output.getvalue()


class InstallerTests(unittest.TestCase):
    maxDiff = None

    def assert_success(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(
            result.returncode,
            0,
            msg=f"command failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_dry_run_for_new_target_creates_nothing(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            destination = fixture_root / "skills"
            before = path_snapshot(fixture_root)

            result = run_installer(destination, "--dry-run")

            self.assert_success(result)
            self.assertEqual(path_snapshot(fixture_root), before)
            self.assertIn("Would create", result.stdout)
            self.assertFalse(os.path.lexists(destination))

    def test_existing_target_is_rejected_identically_by_dry_run_and_execution(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            destination = fixture_root / "skills"
            target = destination / SKILL_NAME
            target.mkdir(parents=True)
            (target / "sentinel.txt").write_text("installed sentinel\n", encoding="utf-8")
            before = path_snapshot(fixture_root)

            dry_run = run_installer(destination, "--dry-run")
            self.assertNotEqual(dry_run.returncode, 0)
            self.assertEqual(path_snapshot(fixture_root), before)

            execution = run_installer(destination)
            self.assertNotEqual(execution.returncode, 0)
            self.assertEqual(path_snapshot(fixture_root), before)
            self.assertEqual(diagnostic(dry_run), diagnostic(execution))

    def test_destination_parent_file_is_rejected_identically_without_mutation(self) -> None:
        for force_arguments in ((), ("--force",)):
            with self.subTest(force=bool(force_arguments)):
                with isolated_temporary_directory() as temporary_directory:
                    fixture_root = Path(temporary_directory)
                    destination = fixture_root / "skills"
                    destination.write_text("user-owned destination\n", encoding="utf-8")
                    before = path_snapshot(fixture_root)

                    dry_run = run_installer(destination, *force_arguments, "--dry-run")
                    self.assertNotEqual(dry_run.returncode, 0)
                    self.assertEqual(path_snapshot(fixture_root), before)

                    execution = run_installer(destination, *force_arguments)
                    self.assertNotEqual(execution.returncode, 0)
                    self.assertEqual(path_snapshot(fixture_root), before)
                    self.assertEqual(diagnostic(dry_run), diagnostic(execution))

    def test_real_run_creates_a_new_install(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            destination = Path(temporary_directory) / "skills"
            target = destination / SKILL_NAME

            result = run_installer(destination)

            self.assert_success(result)
            self.assertTrue((target / "SKILL.md").is_file())

    def test_forced_dry_run_predicts_replacement_without_mutation(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            destination = fixture_root / "skills"
            target = destination / SKILL_NAME
            target.mkdir(parents=True)
            (target / "sentinel.txt").write_text("installed sentinel\n", encoding="utf-8")
            before = path_snapshot(fixture_root)

            result = run_installer(destination, "--force", "--dry-run")

            self.assert_success(result)
            self.assertEqual(path_snapshot(fixture_root), before)
            self.assertIn("Would replace", result.stdout)

    def test_force_replaces_existing_target_and_cleans_up_staging(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            destination = Path(temporary_directory) / "skills"
            target = destination / SKILL_NAME
            target.mkdir(parents=True)
            (target / "sentinel.txt").write_text("installed sentinel\n", encoding="utf-8")

            result = run_installer(destination, "--force")

            self.assert_success(result)
            self.assertFalse((target / "sentinel.txt").exists())
            self.assertTrue((target / "SKILL.md").is_file())

            leftovers = [path.name for path in destination.iterdir() if path.name != SKILL_NAME]
            self.assertEqual(leftovers, [], "installer left a staging or backup directory behind")

    def test_target_symlink_is_rejected_even_with_force_and_dry_run(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            destination = fixture_root / "skills"
            destination.mkdir()
            external = fixture_root / "external-installed-copy"
            external.mkdir()
            (external / "sentinel.txt").write_text("external sentinel\n", encoding="utf-8")
            target = destination / SKILL_NAME
            try:
                target.symlink_to(external, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symlinks are unavailable: {error}")

            for arguments in ((), ("--force",), ("--dry-run",), ("--force", "--dry-run")):
                with self.subTest(arguments=arguments):
                    before = path_snapshot(fixture_root)
                    result = run_installer(destination, *arguments)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertRegex(diagnostic(result), r"(?i)(symlink|direct child)")
                    self.assertEqual(path_snapshot(fixture_root), before)

    def test_destination_symlink_is_rejected_even_with_force_and_dry_run(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            external_destination = fixture_root / "external-skills"
            external_destination.mkdir()
            (external_destination / "sentinel.txt").write_text("external sentinel\n", encoding="utf-8")
            destination = fixture_root / "skills"
            try:
                destination.symlink_to(external_destination, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symlinks are unavailable: {error}")

            for arguments in ((), ("--force",), ("--dry-run",), ("--force", "--dry-run")):
                with self.subTest(arguments=arguments):
                    before = path_snapshot(fixture_root)
                    result = run_installer(destination, *arguments)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertRegex(diagnostic(result), r"(?i)symlink")
                    self.assertEqual(path_snapshot(fixture_root), before)
                    self.assertEqual(
                        (external_destination / "sentinel.txt").read_text(encoding="utf-8"),
                        "external sentinel\n",
                    )

    def test_symlink_in_earlier_destination_ancestor_is_always_rejected(self) -> None:
        topologies = {
            "existing destination behind link": ("linked-parent", "skills"),
            "missing descendants behind link": ("linked-parent", "missing", "skills"),
        }
        for label, destination_parts in topologies.items():
            with self.subTest(topology=label):
                with isolated_temporary_directory() as temporary_directory:
                    fixture_root = Path(temporary_directory)
                    external = fixture_root / "external-tree"
                    external.mkdir()
                    (external / "sentinel.txt").write_text("external sentinel\n", encoding="utf-8")
                    link = fixture_root / "linked-parent"
                    try:
                        link.symlink_to(external, target_is_directory=True)
                    except OSError as error:
                        self.skipTest(f"symlinks are unavailable: {error}")

                    if label.startswith("existing"):
                        (external / "skills").mkdir()
                    destination = fixture_root.joinpath(*destination_parts)
                    before = path_snapshot(fixture_root)
                    diagnostics: list[str] = []

                    for arguments in ((), ("--force",), ("--dry-run",), ("--force", "--dry-run")):
                        with self.subTest(topology=label, arguments=arguments):
                            result = run_installer(destination, *arguments)
                            self.assertNotEqual(result.returncode, 0)
                            self.assertRegex(diagnostic(result), r"(?i)symlink")
                            diagnostics.append(diagnostic(result))
                            self.assertEqual(path_snapshot(fixture_root), before)
                            self.assertEqual(
                                (external / "sentinel.txt").read_text(encoding="utf-8"),
                                "external sentinel\n",
                            )

                    self.assertEqual(len(set(diagnostics)), 1)

    def test_untrusted_skill_names_are_rejected_before_any_install_action(self) -> None:
        invalid_names: tuple[tuple[str, str | None], ...] = (
            ("parent traversal", "../external-target"),
            ("current directory", "."),
            ("absolute path", "__ABSOLUTE_FIXTURE_PATH__"),
            ("forward-slash path", "a/b"),
            ("backslash path", r"a\b"),
            ("empty name", ""),
            ("mismatched quote", "'broken"),
            ("missing name", None),
        )
        for label, configured_name in invalid_names:
            for arguments in ((), ("--force",), ("--dry-run",), ("--force", "--dry-run")):
                with self.subTest(name=label, arguments=arguments):
                    with isolated_temporary_directory() as temporary_directory:
                        fixture_root = Path(temporary_directory)
                        source = copy_source_package(fixture_root / "source-skill")
                        destination = fixture_root / "install-destination"
                        protected = fixture_root / "protected-external"
                        protected.mkdir()
                        (protected / "sentinel.txt").write_text("external sentinel\n", encoding="utf-8")
                        name = (
                            str(fixture_root / "absolute-target")
                            if configured_name == "__ABSOLUTE_FIXTURE_PATH__"
                            else configured_name
                        )
                        name_line = "" if name is None else f"name: {name}\n"
                        (source / "SKILL.md").write_text(
                            f"---\n{name_line}description: Isolated installer fixture.\n---\n\n# Fixture\n",
                            encoding="utf-8",
                        )
                        before = path_snapshot(fixture_root)

                        result = run_fixture_installer(source, destination, *arguments)

                        self.assertNotEqual(result.returncode, 0)
                        self.assertRegex(diagnostic(result), r"(?i)name")
                        self.assertEqual(path_snapshot(fixture_root), before)
                        self.assertEqual(
                            (protected / "sentinel.txt").read_text(encoding="utf-8"),
                            "external sentinel\n",
                        )

    def test_valid_hyphen_skill_name_installs_as_direct_child(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            source = copy_source_package(fixture_root / "source-skill")
            valid_name = "valid-skill-2"
            (source / "SKILL.md").write_text(
                f"---\nname: {valid_name}\ndescription: Isolated installer fixture.\n---\n\n# Fixture\n",
                encoding="utf-8",
            )
            destination = fixture_root / "install-destination"
            parsed_name = INSTALLER_MODULE.skill_name(source)
            target = INSTALLER_MODULE.install_target(destination, parsed_name)
            self.assertEqual(parsed_name, valid_name)
            self.assertEqual(target.parent.resolve(strict=False), destination.resolve(strict=False))

            before = path_snapshot(fixture_root)
            dry_run = run_fixture_installer(source, destination, "--dry-run")
            self.assert_success(dry_run)
            self.assertIn("Would create", dry_run.stdout)
            self.assertEqual(path_snapshot(fixture_root), before)

            real_run = run_fixture_installer(source, destination)
            self.assert_success(real_run)
            self.assertTrue((target / "SKILL.md").is_file())
            self.assertEqual(
                {path.name for path in destination.iterdir()},
                {valid_name},
                "valid skill installed outside its direct-child target",
            )

    def test_source_symlinks_are_rejected_before_dry_run_or_execution(self) -> None:
        topologies = (
            "external file",
            "external directory",
            "dangling link",
            "directory cycle",
        )
        for topology in topologies:
            with self.subTest(topology=topology):
                with isolated_temporary_directory() as temporary_directory:
                    fixture_root = Path(temporary_directory)
                    source = copy_source_package(fixture_root / "source-skill")
                    external = fixture_root / "external"
                    external.mkdir()
                    sentinel = external / "sentinel.txt"
                    sentinel.write_text("external sentinel\n", encoding="utf-8")
                    source_link = source / "fixture-link"
                    try:
                        if topology == "external file":
                            source_link.symlink_to(sentinel)
                        elif topology == "external directory":
                            source_link.symlink_to(external, target_is_directory=True)
                        elif topology == "dangling link":
                            source_link.symlink_to(fixture_root / "missing-link-target")
                        else:
                            source_link.symlink_to(source, target_is_directory=True)
                    except OSError as error:
                        self.skipTest(f"symlinks are unavailable: {error}")

                    destination = fixture_root / "install-destination"
                    target = destination / SKILL_NAME
                    before = path_snapshot(fixture_root)
                    dry_run = run_fixture_installer(source, destination, "--dry-run")
                    execution = run_fixture_installer(source, destination)

                    self.assertNotEqual(dry_run.returncode, 0)
                    self.assertNotEqual(execution.returncode, 0)
                    self.assertRegex(diagnostic(dry_run), r"(?i)symlink")
                    self.assertEqual(diagnostic(dry_run), diagnostic(execution))
                    self.assertEqual(path_snapshot(fixture_root), before)
                    self.assertFalse(os.path.lexists(target))
                    self.assertEqual(sentinel.read_text(encoding="utf-8"), "external sentinel\n")

    def test_non_force_create_race_preserves_competing_target(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            source = copy_source_package(fixture_root / "source-skill")
            target = fixture_root / "installed-sibling"
            competing_content = "competing target sentinel\n"
            real_copytree = INSTALLER_MODULE.shutil.copytree

            def copytree_then_create_target(*args: object, **kwargs: object) -> Path:
                copied = real_copytree(*args, **kwargs)
                if Path(args[0]) == source:
                    target.mkdir()
                    (target / "sentinel.txt").write_text(competing_content, encoding="utf-8")
                return Path(copied)

            with mock.patch.object(
                INSTALLER_MODULE.shutil,
                "copytree",
                side_effect=copytree_then_create_target,
            ):
                with self.assertRaisesRegex(FileExistsError, r"(?i)(exists|changed)"):
                    invoke_install(source, target, force=False, dry_run=False)

            self.assertEqual((target / "sentinel.txt").read_text(encoding="utf-8"), competing_content)
            self.assertFalse((target / "SKILL.md").exists())
            self.assertEqual(
                {path.name for path in fixture_root.iterdir()},
                {source.name, target.name},
                "failed create left a staging or backup directory behind",
            )

    def test_non_force_create_race_after_lexists_preserves_empty_competing_target(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory).resolve()
            staged_target = fixture_root / "staged-skill"
            staged_target.mkdir()
            (staged_target / "SKILL.md").write_text("generated skill\n", encoding="utf-8")
            target = fixture_root / "installed-skill"
            real_lexists = os.path.lexists
            injected = False
            competing_identity: tuple[int, int] | None = None

            def lexists_then_create(path: object) -> bool:
                nonlocal injected, competing_identity
                result = real_lexists(path)
                if Path(path) == target and not result and not injected:
                    target.mkdir()
                    metadata = target.lstat()
                    competing_identity = (metadata.st_dev, metadata.st_ino)
                    injected = True
                return result

            with mock.patch.object(
                INSTALLER_MODULE.os.path,
                "lexists",
                side_effect=lexists_then_create,
            ):
                with self.assertRaisesRegex(FileExistsError, r"(?i)appeared"):
                    INSTALLER_MODULE.replace_directory(
                        staged_target,
                        target,
                        action="create",
                        expected_identity=None,
                    )

            self.assertTrue(injected)
            self.assertEqual(INSTALLER_MODULE.directory_identity(target), competing_identity)
            self.assertEqual(list(target.iterdir()), [])
            self.assertTrue((staged_target / "SKILL.md").is_file())

    def test_forced_replace_identity_swap_preserves_replacement_target(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            source = copy_source_package(fixture_root / "source-skill")
            target = fixture_root / "installed-sibling"
            target.mkdir()
            (target / "sentinel.txt").write_text("original target sentinel\n", encoding="utf-8")
            displaced_target = fixture_root / "displaced-original-target"
            replacement_content = "replacement target sentinel\n"
            real_copytree = INSTALLER_MODULE.shutil.copytree
            swap_injected = False

            def copytree_then_swap_target(*args: object, **kwargs: object) -> Path:
                nonlocal swap_injected
                copied = real_copytree(*args, **kwargs)
                if Path(args[0]) == source and not swap_injected:
                    target.rename(displaced_target)
                    target.mkdir()
                    (target / "sentinel.txt").write_text(replacement_content, encoding="utf-8")
                    swap_injected = True
                return Path(copied)

            with mock.patch.object(
                INSTALLER_MODULE.shutil,
                "copytree",
                side_effect=copytree_then_swap_target,
            ):
                with self.assertRaisesRegex(FileExistsError, r"(?i)changed"):
                    invoke_install(source, target, force=True, dry_run=False)

            self.assertTrue(swap_injected)
            self.assertEqual((target / "sentinel.txt").read_text(encoding="utf-8"), replacement_content)
            self.assertFalse((target / "SKILL.md").exists())
            self.assertEqual(
                (displaced_target / "sentinel.txt").read_text(encoding="utf-8"),
                "original target sentinel\n",
            )
            self.assertEqual(
                {path.name for path in fixture_root.iterdir()},
                {source.name, target.name, displaced_target.name},
                "identity-swap failure left a staging or backup directory behind",
            )

    def test_keyboard_interrupt_after_backup_rename_restores_previous_target(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            source = copy_source_package(fixture_root / "source-skill")
            target = fixture_root / "installed-sibling"
            target.mkdir()
            (target / "sentinel.txt").write_text("previous install sentinel\n", encoding="utf-8")
            before = path_snapshot(fixture_root)
            real_rename = Path.rename
            interruption_injected = False

            def rename_with_interrupt(path: Path, destination: Path) -> Path:
                nonlocal interruption_injected
                resolved_destination = Path(destination)
                if path != target and resolved_destination == target and not interruption_injected:
                    interruption_injected = True
                    raise KeyboardInterrupt("injected after backup rename")
                return real_rename(path, destination)

            with mock.patch.object(Path, "rename", new=rename_with_interrupt):
                with self.assertRaisesRegex(KeyboardInterrupt, r"injected after backup rename"):
                    invoke_install(source, target, force=True, dry_run=False)

            self.assertTrue(interruption_injected)
            self.assertEqual(path_snapshot(fixture_root), before)
            self.assertEqual(
                (target / "sentinel.txt").read_text(encoding="utf-8"),
                "previous install sentinel\n",
            )
            self.assertFalse((target / "SKILL.md").exists())
            self.assertEqual(
                {path.name for path in fixture_root.iterdir()},
                {source.name, target.name},
                "interrupted replacement left a staging or backup directory behind",
            )

    def test_keyboard_interrupt_on_return_from_backup_rename_restores_previous_target(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            source = copy_source_package(fixture_root / "source-skill")
            target = fixture_root / "installed-sibling"
            target.mkdir()
            (target / "sentinel.txt").write_text("previous install sentinel\n", encoding="utf-8")
            before = path_snapshot(fixture_root)
            real_rename = Path.rename
            interruption_injected = False

            def rename_then_interrupt(path: Path, destination: Path) -> Path:
                nonlocal interruption_injected
                result = real_rename(path, destination)
                if path == target and ".backup-" in Path(destination).name and not interruption_injected:
                    interruption_injected = True
                    raise KeyboardInterrupt("injected after backup rename returned")
                return result

            with mock.patch.object(Path, "rename", new=rename_then_interrupt):
                with self.assertRaisesRegex(KeyboardInterrupt, r"injected after backup rename returned"):
                    invoke_install(source, target, force=True, dry_run=False)

            self.assertTrue(interruption_injected)
            self.assertEqual(path_snapshot(fixture_root), before)
            self.assertEqual(
                (target / "sentinel.txt").read_text(encoding="utf-8"),
                "previous install sentinel\n",
            )
            self.assertFalse((target / "SKILL.md").exists())
            self.assertEqual(
                {path.name for path in fixture_root.iterdir()},
                {source.name, target.name},
                "interrupt at backup-rename return left staging or backup data behind",
            )

    def test_target_strict_child_of_source_is_rejected_without_mutation(self) -> None:
        for force in (False, True):
            with self.subTest(force=force):
                with isolated_temporary_directory() as temporary_directory:
                    fixture_root = Path(temporary_directory)
                    source = copy_source_package(fixture_root / "source-skill")
                    target = source / "nested-install"
                    before = path_snapshot(fixture_root)

                    for dry_run in (True, False):
                        with self.subTest(force=force, dry_run=dry_run):
                            with self.assertRaisesRegex(ValueError, r"(?i)(inside|source)"):
                                invoke_install(source, target, force=force, dry_run=dry_run)
                            self.assertEqual(path_snapshot(fixture_root), before)

    def test_source_strict_child_of_target_is_rejected_with_force_without_mutation(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            target = fixture_root / "install-parent"
            target.mkdir()
            (target / "sentinel.txt").write_text("ancestor sentinel\n", encoding="utf-8")
            source = copy_source_package(target / "source-skill")
            before = path_snapshot(fixture_root)

            for dry_run in (True, False):
                with self.subTest(dry_run=dry_run):
                    with self.assertRaisesRegex(ValueError, r"(?i)(contain|source)"):
                        invoke_install(source, target, force=True, dry_run=dry_run)
                    self.assertEqual(path_snapshot(fixture_root), before)
                    self.assertEqual((target / "sentinel.txt").read_text(encoding="utf-8"), "ancestor sentinel\n")

    def test_target_equal_source_is_rejected_identically_without_mutation(self) -> None:
        for force in (False, True):
            with self.subTest(force=force):
                with isolated_temporary_directory() as temporary_directory:
                    fixture_root = Path(temporary_directory)
                    source = copy_source_package(fixture_root / "source-skill")
                    (source / "sentinel.txt").write_text("source sentinel\n", encoding="utf-8")
                    before = path_snapshot(fixture_root)
                    diagnostics: list[str] = []

                    for dry_run in (True, False):
                        with self.subTest(force=force, dry_run=dry_run):
                            with self.assertRaisesRegex(
                                ValueError,
                                r"(?i)(same|source|equal|separate|outside)",
                            ) as raised:
                                invoke_install(source, source, force=force, dry_run=dry_run)
                            diagnostics.append(str(raised.exception))
                            self.assertEqual(path_snapshot(fixture_root), before)
                            self.assertEqual(
                                (source / "sentinel.txt").read_text(encoding="utf-8"),
                                "source sentinel\n",
                            )

                    self.assertEqual(diagnostics[0], diagnostics[1])

    def test_sibling_target_succeeds_without_staging_leftovers(self) -> None:
        with isolated_temporary_directory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            source = copy_source_package(fixture_root / "source-skill")
            target = fixture_root / "installed-sibling"
            before = path_snapshot(fixture_root)

            dry_run_output = invoke_install(source, target, force=False, dry_run=True)
            self.assertIn("Would create", dry_run_output)
            self.assertEqual(path_snapshot(fixture_root), before)

            real_output = invoke_install(source, target, force=False, dry_run=False)
            self.assertIn("Installed", real_output)
            self.assertEqual(path_snapshot(target), path_snapshot(source))
            self.assertEqual(
                {path.name for path in fixture_root.iterdir()},
                {source.name, target.name},
                "installer left a staging or backup directory behind",
            )


if __name__ == "__main__":
    unittest.main()
