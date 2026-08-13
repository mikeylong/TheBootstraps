#!/usr/bin/env python3
"""Create an AI-native project scaffold."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from string import Template
from textwrap import dedent


DIRECTORIES = (
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
)


FILES = {
    "README.md": """\
        # $project_name

        This project is organized for agent-assisted product and interface work. The repository separates intent, design constraints, local skills, and validation so AI agents can make changes against explicit project contracts.

        ## Structure

        - `AGENTS.md`: Operating rules for agents working in this repository.
        - `CURRENT.md`: Mutable source of truth for the active outcome, progress, next action, and boundaries.
        - `CONTEXT_MAP.md`: Pointers to governing context and when to read it.
        - `DECISIONS.md`: Append-only history of consequential decisions and their evidence.
        - `DESIGN.md`: Design principles and contract expectations.
        - `specs/`: Product and interface specs that define what should be built.
        - `.agents/skills/`: Discoverable project-local skills for common implementation workflows.
        - `contracts/`: Machine-readable rules for design tokens and components.
        - `plans/`: Optional checked-in execution plans for complex work.
        - `tests/`: Test coverage for implemented behavior.

        ## First Workflow

        1. Review `CURRENT.md`; confirm the outcome, authorization boundary, stop or return condition, and first useful checkpoint.
        2. Resolve its open questions and fill in the active files in `specs/`.
        3. Use `CONTEXT_MAP.md` to load only the sources needed for the next decision.
        4. Use the local skill that matches the task: `build-page`, `refactor-component`, or `write-tests`.
        5. Record missing runtime, design-token source, or test command instead of inventing one.
        6. Validate against the active spec, `DESIGN.md`, and `contracts/`; then update `CURRENT.md` and append consequential decisions to `DECISIONS.md`.
    """,
    "AGENTS.md": """\
        # Agent Instructions

        ## Operating Rules

        - Read `CURRENT.md` first. Treat it as the mutable source of truth for active work.
        - Use `CONTEXT_MAP.md` to load only the sources relevant to the next decision.
        - Apply stable rules from this file, `DESIGN.md`, `contracts/`, the active files in `specs/`, and the applicable local skill.
        - Treat `contracts/` as project constraints. Do not bypass token or component rules without updating the contract and explaining the reason.
        - Preserve user work. Do not overwrite existing files unless the user explicitly asks for replacement.
        - Keep changes scoped to the active spec and avoid unrelated refactors.
        - Add or update tests for behavior that changes.
        - Before relying on a runtime, design-token source, or test command, confirm it is recorded in project context. If it is missing, add it to `CURRENT.md` under open questions and ask; never invent it.
        - Stop or return when the condition recorded in `CURRENT.md` is met.

        ## State and Decisions

        - Update `CURRENT.md` after a consequential decision or checkpoint. Keep the outcome, completed work, in-progress work, next action, open questions, and boundaries current.
        - Append consequential decisions and their reason or evidence to `DECISIONS.md`. Never rewrite history; record a replacement as a new entry that identifies the superseded decision.
        - For complex work, create a focused plan under `plans/` and link it from `CURRENT.md`. Do not create plan files for routine work.
        - Never infer approval for publication, spending, deletion, deployment, or contacting people. Record and ask for authorization when it is not explicit.

        ## Local Skills

        - Use `.agents/skills/build-page/SKILL.md` for page-level UI work.
        - Use `.agents/skills/refactor-component/SKILL.md` for component changes.
        - Use `.agents/skills/write-tests/SKILL.md` for test planning and implementation.

        ## Handoff

        Before handoff, make `CURRENT.md` sufficient for a fresh agent to resume. Summaries should name the spec followed, contracts checked, tests run, current checkpoint, next action, and remaining open questions.
    """,
    "CURRENT.md": """\
        # Current Project State

        This file is the mutable source of truth for active work. Keep it concise and rewrite it as the work changes.

        ## Outcome now

        Define the first project outcome in `specs/feature-spec.md` and confirm the inputs required to execute it.

        ## Definition of done

        - The outcome, scope, acceptance criteria, relevant sources, and authorization boundary are explicit.
        - The first useful checkpoint can be validated with a recorded command or review method.

        ## Active decisions

        - The scaffold is stack-neutral. It does not record a runtime, design-token source, or test command; treat each as unresolved until project evidence or the owner supplies it.
        - `CURRENT.md` outranks historical entries in `DECISIONS.md` for active state.

        ## Completed

        - The baseline project structure and durable context files were initialized.

        ## In progress

        - Project admission: defining the first outcome and resolving required inputs.

        ## Next action

        Ask the project owner to resolve the open questions below, then complete the active spec and interface contract.

        ## Open questions and blockers

        - Which runtime and toolchain, if any, govern this project?
        - What is the authoritative design-token source, if one is required?
        - What exact test or validation command should agents run?

        Do not infer answers. Record the owner's answers here and add source pointers to `CONTEXT_MAP.md`.

        ## First useful checkpoint

        The owner has confirmed the outcome, relevant sources, action boundaries, missing inputs, and a reviewable acceptance check.

        ## Stop or return condition

        Stop before implementation when the outcome, governing source, required input, or authorization is unresolved. Return when the first useful checkpoint is ready for review or a recorded boundary requires owner action.

        ## Authorization and approval boundaries

        Work only within the user's stated scope. Do not publish, spend money, delete material data, deploy, or contact people without explicit authorization.

        ## Active plan

        None. Add a focused file under `plans/` and link it here only when the work is complex enough to need one.
    """,
    "CONTEXT_MAP.md": """\
        # Context Map

        Use this file as a map of pointers, not a copy of project context. Load only the sources needed for the next decision and keep authority and freshness visible.

        | Path or URL | What it governs | Authority level | When to read | Owner or freshness |
        | --- | --- | --- | --- | --- |
        | `README.md` | Project purpose, structure, and first workflow | Orientation | When entering the project | Update when the project front door changes |
        | `CURRENT.md` | Active outcome, progress, next action, questions, checkpoint, and boundaries | Active source of truth | At the start of every task and before handoff | Keep current after consequential work |
        | `AGENTS.md` | Stable operating rules and state protocol | Governing instructions | Before making changes | Update only when stable rules change |
        | `specs/feature-spec.md` | Outcome, users, scope, requirements, acceptance criteria, and risks | Active product contract when completed | Before implementing or reviewing behavior | Confirm with project owner |
        | `specs/interface-contract.md` | Surfaces, states, inputs, outputs, constraints, and validation | Active interface contract when completed | Before changing an interface | Confirm with project owner |
        | `DESIGN.md` | Stable design principles and contract expectations | Governing design guidance | Before interface or component work | Review when design policy changes |
        | `contracts/` | Machine-readable token and component constraints | Required project constraints | Before affected implementation or review | Keep synchronized with approved rules |
        | `DECISIONS.md` | Consequential decision history and evidence | Historical; never silently overrides `CURRENT.md` | When rationale or superseded guidance matters | Append-only |
        | `plans/` | Optional execution plans for complex work | Active only when linked from `CURRENT.md` | When an active plan is linked | Update at checkpoints |

        ## Unresolved source pointers

        The runtime/toolchain, authoritative design-token source, and exact test command are intentionally unresolved. Ask the project owner and record the answers in `CURRENT.md` before adding pointers here; never invent them.
    """,
    "DECISIONS.md": """\
        # Decision History

        Append consequential decisions below. Do not edit or delete prior entries. When guidance changes, add a replacement entry that identifies the superseded decision. Historical entries never silently outrank `CURRENT.md`.

        ## DEC-000 — Keep the starter stack neutral

        - **Date or sequence:** DEC-000
        - **Decision:** Do not select or infer a runtime, design-token source, or test command in the baseline scaffold.
        - **Reason and evidence:** Those choices depend on project evidence and owner intent that the scaffold does not have.
        - **Scope:** Initial project admission and all generated local skills.
        - **Status when recorded:** Active.
        - **Supersedes:** None.

        ## Entry template

        - **Date or sequence:** YYYY-MM-DD or DEC-NNN
        - **Decision:**
        - **Reason and evidence:**
        - **Scope:**
        - **Status when recorded:** Active or superseded
        - **Supersedes:** Prior ID or none
    """,
    "DESIGN.md": """\
        # Design Contract

        ## Principles

        - Design from explicit specs, not inferred product stories.
        - Prefer reusable components and stable interaction patterns over one-off UI.
        - Use design tokens for color, spacing, typography, radius, and elevation decisions.
        - Make states visible: loading, empty, error, disabled, active, and success states should be intentionally handled.
        - Keep interfaces inspectable by agents: names, props, variants, and state transitions should be clear.

        ## Contracts

        - `contracts/design-tokens.schema.json` defines the expected shape for token files.
        - `contracts/component-rules.json` defines component-level constraints agents should preserve.

        ## Review Checklist

        - Does the implementation satisfy the active spec?
        - Are token and component rules respected?
        - Are responsive behavior and state coverage addressed?
        - Are tests aligned with the acceptance criteria?
    """,
    "specs/feature-spec.md": """\
        # Feature Spec

        ## Goal

        Describe the user or business outcome this feature should create.

        ## Users

        Name the primary users, their context, and what they need to accomplish.

        ## Scope

        In scope:

        - TBD

        Out of scope:

        - TBD

        ## Requirements

        - TBD

        ## Acceptance Criteria

        - TBD

        ## Risks

        - TBD

        ## Open Questions

        - TBD
    """,
    "specs/interface-contract.md": """\
        # Interface Contract

        ## Surfaces

        List the pages, panels, dialogs, flows, or API surfaces this work touches.

        ## States

        Define expected states, including loading, empty, error, disabled, active, and success where relevant.

        ## Inputs

        Describe user inputs, system inputs, data dependencies, and validation rules.

        ## Outputs

        Describe UI output, persisted data, emitted events, side effects, and user feedback.

        ## Agent Responsibilities

        - Follow `DESIGN.md` and files in `contracts/`.
        - Preserve existing behavior outside the stated surfaces.
        - Add tests that map to the acceptance criteria.

        ## Constraints

        - TBD

        ## Validation

        - TBD
    """,
    ".agents/skills/build-page/SKILL.md": """\
        ---
        name: build-page
        description: Build or revise page-level UI from the active spec, interface contract, design contract, and component rules.
        ---

        # Build Page

        Use this local skill when creating or revising a page, flow, or major screen.

        ## Workflow

        1. Read `CURRENT.md`, then use `CONTEXT_MAP.md` to load the active spec, interface contract, `DESIGN.md`, and relevant files in `contracts/`.
        2. Confirm the outcome, authorization boundary, required surfaces, states, inputs, outputs, and first useful checkpoint.
        3. Confirm the runtime, authoritative design-token source, and exact validation or test command when the work requires them. If any is missing, record it under open questions in `CURRENT.md` and ask; never invent it.
        4. Reuse existing components and approved tokens before creating new patterns.
        5. Implement the smallest page-level change that satisfies the spec.
        6. Verify responsive behavior, state coverage, and acceptance criteria with the recorded method.
        7. Update `CURRENT.md` after the checkpoint and append consequential decisions with evidence to `DECISIONS.md`.

        ## Output

        Report the spec followed, surfaces changed, checkpoint reached, recorded tests or validation run, next action, open questions, and any contract updates needed.
    """,
    ".agents/skills/build-page/examples.md": """\
        # Build Page Examples

        ## Prompt

        Use `.agents/skills/build-page/SKILL.md` to build the surface described in `specs/feature-spec.md` and `specs/interface-contract.md`.

        ## Expected Agent Behavior

        - Read `CURRENT.md` first, then follow pointers in `CONTEXT_MAP.md` to the spec and interface contract.
        - Check `DESIGN.md` and component rules before introducing UI patterns.
        - Ask for and record any missing runtime, token source, or validation command instead of inventing it.
        - Implement all required states listed in the interface contract.
        - Run focused tests or document why tests are not available.
        - Update current state and append consequential decisions before handoff.
    """,
    ".agents/skills/build-page/agents/openai.yaml": """\
        interface:
          display_name: "Build Page"
          short_description: "Build page-level UI from project contracts"
          default_prompt: "Use $build-page to implement the active page contract and report the validated checkpoint."
    """,
    ".agents/skills/refactor-component/SKILL.md": """\
        ---
        name: refactor-component
        description: Refactor existing components while preserving behavior, design-token usage, component rules, and test coverage.
        ---

        # Refactor Component

        Use this local skill when changing component internals, variants, props, styles, or composition.

        ## Workflow

        1. Read `CURRENT.md`, then use `CONTEXT_MAP.md` to locate current usages, tests, the active spec, `DESIGN.md`, and component rules.
        2. Confirm the active outcome, authorization boundary, and first useful checkpoint.
        3. Confirm the runtime, authoritative design-token source, and exact validation or test command when the work requires them. If any is missing, record it under open questions in `CURRENT.md` and ask; never invent it.
        4. Preserve public behavior unless the active spec requires a change.
        5. Keep token usage and component variants aligned with project contracts.
        6. Update and run the recorded tests for any behavior, state, or accessibility change.
        7. Update `CURRENT.md` after the checkpoint and append consequential decisions with evidence to `DECISIONS.md`.

        ## Output

        Report changed components, preserved public interfaces, checkpoint reached, tests run, next action, open questions, and any migration notes.
    """,
    ".agents/skills/refactor-component/checks.md": """\
        # Component Refactor Checks

        - Public props, exported names, and event behavior are preserved or intentionally migrated.
        - Token usage still follows `DESIGN.md` and `contracts/`.
        - Loading, empty, error, disabled, active, and success states still render as expected.
        - Existing tests pass and new tests cover changed behavior.
        - Call sites are updated when an intentional interface change is made.
        - `CURRENT.md` reflects the checkpoint, next action, and unresolved questions.
        - Consequential decisions and their evidence are appended to `DECISIONS.md`.
    """,
    ".agents/skills/refactor-component/agents/openai.yaml": """\
        interface:
          display_name: "Refactor Component"
          short_description: "Refactor components without breaking contracts"
          default_prompt: "Use $refactor-component to revise the active component while preserving its project contracts."
    """,
    ".agents/skills/write-tests/SKILL.md": """\
        ---
        name: write-tests
        description: Write focused tests from specs, interface contracts, risks, acceptance criteria, and changed behavior.
        ---

        # Write Tests

        Use this local skill when adding or updating tests for project behavior.

        ## Workflow

        1. Read `CURRENT.md`, then use `CONTEXT_MAP.md` to load the active spec, interface contract, existing tests, and relevant contracts.
        2. Confirm the outcome, authorization boundary, and first useful checkpoint.
        3. Confirm the project runtime and exact test command. If either is missing, record it under open questions in `CURRENT.md` and ask; never invent a framework or command.
        4. Confirm the authoritative design-token source when tests assert token behavior; record and ask if it is missing.
        5. Map acceptance criteria and risks to test cases.
        6. Prefer behavior-level assertions over implementation details.
        7. Cover important states, validation, and failure modes.
        8. Run the recorded test command and report the result.
        9. Update `CURRENT.md` after the checkpoint and append consequential decisions with evidence to `DECISIONS.md`.

        ## Output

        Report test files changed, criteria covered, checkpoint reached, recorded command and output summary, next action, and remaining gaps.
    """,
    ".agents/skills/write-tests/agents/openai.yaml": """\
        interface:
          display_name: "Write Tests"
          short_description: "Write focused tests from project contracts"
          default_prompt: "Use $write-tests to add focused tests for the active acceptance criteria and risks."
    """,
    "contracts/design-tokens.schema.json": """\
        {
          "$schema": "https://json-schema.org/draft/2020-12/schema",
          "title": "Design Tokens",
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "color": {
              "type": "object",
              "additionalProperties": { "type": "string" }
            },
            "space": {
              "type": "object",
              "additionalProperties": { "type": "string" }
            },
            "typography": {
              "type": "object",
              "additionalProperties": { "type": "string" }
            },
            "radius": {
              "type": "object",
              "additionalProperties": { "type": "string" }
            },
            "shadow": {
              "type": "object",
              "additionalProperties": { "type": "string" }
            }
          }
        }
    """,
    "contracts/component-rules.json": """\
        {
          "version": 1,
          "rules": [
            {
              "id": "use-design-tokens",
              "severity": "required",
              "description": "Use project design tokens for color, spacing, typography, radius, and shadow decisions."
            },
            {
              "id": "cover-core-states",
              "severity": "required",
              "description": "Account for loading, empty, error, disabled, active, and success states when a surface can enter them."
            },
            {
              "id": "preserve-component-contracts",
              "severity": "required",
              "description": "Do not change public component props, events, or exported names unless the active spec requires it."
            }
          ]
        }
    """,
}


def normalize_content(template: str, project_name: str) -> str:
    text = dedent(template).strip() + "\n"
    return Template(text).safe_substitute(project_name=project_name)


def default_project_name(target_dir: Path) -> str:
    name = Path(os.path.abspath(os.fspath(target_dir))).name
    if not name:
        return "AI-Native Project"
    words = re.split(r"[-_\s]+", name)
    return " ".join(word.capitalize() for word in words if word) or "AI-Native Project"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an AI-native project scaffold.")
    parser.add_argument("target_dir", help="Directory where the scaffold should be created.")
    parser.add_argument("--project-name", help="Display name to use in starter content.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing scaffold files.")
    parser.add_argument("--dry-run", action="store_true", help="Show planned changes without writing files.")
    return parser.parse_args()


@dataclass(frozen=True)
class PlannedOperation:
    """One validated filesystem operation in a scaffold plan."""

    kind: str
    relative_path: str
    action: str
    content: str | None = None
    existing_mode: int | None = None
    existing_identity: tuple[int, int] | None = None


@dataclass(frozen=True)
class OperationPlan:
    """The complete immutable plan shared by dry-run and execution."""

    requested_target: Path
    resolved_target: Path
    operations: tuple[PlannedOperation, ...]

    def summary(self) -> dict[str, list[str]]:
        summary = {"created": [], "skipped": [], "overwritten": []}
        for operation in self.operations:
            if operation.relative_path == "." or operation.action == "ensure":
                continue
            display_path = operation.relative_path
            if operation.kind == "directory":
                display_path += "/"
            summary[
                {
                    "create": "created",
                    "skip": "skipped",
                    "overwrite": "overwritten",
                }[operation.action]
            ].append(display_path)
        return summary


def _absolute_without_resolving(path: Path) -> Path:
    """Return a normalized absolute path without following its final component."""

    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _lstat(path: Path) -> os.stat_result | None:
    """Inspect a path without following a final symlink."""

    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _assert_within_target(path: Path, resolved_target: Path) -> None:
    resolved_path = path.resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_target)
    except ValueError as error:
        raise ValueError(
            f"Planned path resolves outside target: {path} -> {resolved_path}"
        ) from error


def _inspect_planned_path(
    target: Path,
    relative_path: str,
    resolved_target: Path,
) -> os.stat_result | None:
    """Reject symlinks and invalid ancestors, then return final path metadata."""

    if relative_path == ".":
        candidate = target
        parts: tuple[str, ...] = ()
    else:
        relative = Path(relative_path)
        if (
            relative.is_absolute()
            or not relative.parts
            or any(part in ("", ".", "..") for part in relative.parts)
        ):
            raise ValueError(f"Scaffold path must be a safe relative path: {relative_path!r}")
        candidate = target / relative
        parts = relative.parts

    target_metadata = _lstat(target)
    if target_metadata is not None:
        if stat.S_ISLNK(target_metadata.st_mode):
            raise ValueError(f"Refusing symlink target: {target}")
        if not stat.S_ISDIR(target_metadata.st_mode):
            raise FileExistsError(f"Target exists and is not a directory: {target}")

    current = target
    final_metadata = target_metadata
    for index, part in enumerate(parts):
        current = current / part
        metadata = _lstat(current)
        if metadata is None:
            final_metadata = None
            break
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"Refusing symlink at planned path: {current}")
        if index < len(parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
            raise FileExistsError(f"Planned path requires a directory but found another type: {current}")
        final_metadata = metadata

    _assert_within_target(candidate, resolved_target)
    return final_metadata


def build_operation_plan(target_dir: Path, project_name: str, *, force: bool) -> OperationPlan:
    """Validate the complete scaffold and return the only plan execution may use."""

    requested_target = _absolute_without_resolving(target_dir)
    target_metadata = _lstat(requested_target)
    if target_metadata is not None:
        if stat.S_ISLNK(target_metadata.st_mode):
            raise ValueError(f"Refusing symlink target: {requested_target}")
        if not stat.S_ISDIR(target_metadata.st_mode):
            raise FileExistsError(f"Target exists and is not a directory: {requested_target}")

    resolved_target = requested_target.resolve(strict=False)
    _assert_within_target(requested_target, resolved_target)
    contents = {
        relative_path: normalize_content(template, project_name)
        for relative_path, template in FILES.items()
    }

    # Validate generated contracts before any filesystem operation, including
    # when an existing copy would be skipped without --force.
    for relative_path in (
        "contracts/design-tokens.schema.json",
        "contracts/component-rules.json",
    ):
        json.loads(contents[relative_path])

    operations: list[PlannedOperation] = [
        PlannedOperation(
            kind="directory",
            relative_path=".",
            action="ensure" if target_metadata is not None else "create",
        )
    ]

    for relative_path in DIRECTORIES:
        metadata = _inspect_planned_path(requested_target, relative_path, resolved_target)
        path = requested_target / relative_path
        if metadata is not None and not stat.S_ISDIR(metadata.st_mode):
            raise FileExistsError(f"Cannot create directory because another path type exists: {path}")
        operations.append(
            PlannedOperation(
                kind="directory",
                relative_path=relative_path,
                action="ensure" if metadata is not None else "create",
            )
        )

    for relative_path, content in contents.items():
        metadata = _inspect_planned_path(requested_target, relative_path, resolved_target)
        path = requested_target / relative_path
        if metadata is not None and not stat.S_ISREG(metadata.st_mode):
            raise FileExistsError(f"Cannot create file because another path type exists: {path}")
        if metadata is None:
            action = "create"
            existing_mode = None
            existing_identity = None
        elif force:
            action = "overwrite"
            existing_mode = stat.S_IMODE(metadata.st_mode)
            existing_identity = (metadata.st_dev, metadata.st_ino)
        else:
            action = "skip"
            existing_mode = stat.S_IMODE(metadata.st_mode)
            existing_identity = (metadata.st_dev, metadata.st_ino)
        operations.append(
            PlannedOperation(
                kind="file",
                relative_path=relative_path,
                action=action,
                content=content,
                existing_mode=existing_mode,
                existing_identity=existing_identity,
            )
        )

    return OperationPlan(
        requested_target=requested_target,
        resolved_target=resolved_target,
        operations=tuple(operations),
    )


def _verify_execution_state(
    plan: OperationPlan,
    operation: PlannedOperation,
) -> os.stat_result | None:
    metadata = _inspect_planned_path(
        plan.resolved_target,
        operation.relative_path,
        plan.resolved_target,
    )
    path = (
        plan.resolved_target
        if operation.relative_path == "."
        else plan.resolved_target / operation.relative_path
    )

    if operation.kind == "directory":
        if operation.action == "create" and metadata is not None:
            raise FileExistsError(f"Planned directory appeared after preflight: {path}")
        if operation.action == "ensure" and (metadata is None or not stat.S_ISDIR(metadata.st_mode)):
            raise FileExistsError(f"Planned directory changed after preflight: {path}")
        return metadata

    if operation.action == "create" and metadata is not None:
        raise FileExistsError(f"Planned file appeared after preflight: {path}")
    if operation.action in ("skip", "overwrite") and (
        metadata is None or not stat.S_ISREG(metadata.st_mode)
    ):
        raise FileExistsError(f"Planned file changed after preflight: {path}")
    if operation.action == "overwrite" and (
        operation.existing_identity is None
        or (metadata.st_dev, metadata.st_ino) != operation.existing_identity
    ):
        raise FileExistsError(f"Planned file identity changed after preflight: {path}")
    return metadata


def _atomic_write(
    path: Path,
    content: str,
    *,
    action: str,
    existing_mode: int | None,
    existing_identity: tuple[int, int] | None = None,
) -> None:
    """Replace one ordinary file atomically without following a final symlink."""

    if existing_mode is None:
        current_umask = os.umask(0)
        os.umask(current_umask)
        write_mode = 0o666 & ~current_umask
    else:
        write_mode = existing_mode

    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    backup_root: Path | None = None
    backup_path: Path | None = None
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
            file_descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), write_mode)
            os.fsync(handle.fileno())

        metadata = _lstat(path)
        if metadata is not None and stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"Refusing symlink introduced at planned path: {path}")
        if action == "create" and metadata is not None:
            raise FileExistsError(f"Planned file appeared after preflight: {path}")
        if action == "overwrite" and (metadata is None or not stat.S_ISREG(metadata.st_mode)):
            raise FileExistsError(f"Planned file changed after preflight: {path}")
        if action == "overwrite" and (
            existing_identity is None
            or (metadata.st_dev, metadata.st_ino) != existing_identity
        ):
            raise FileExistsError(f"Planned file identity changed after preflight: {path}")

        if action == "create":
            # A hard-link commit is atomic and refuses an existing path, so a
            # user file that appears after preflight cannot be overwritten.
            os.link(temporary_path, path)
        elif action == "overwrite":
            backup_root = Path(tempfile.mkdtemp(dir=path.parent, prefix=f".{path.name}.backup-"))
            backup_path = backup_root / path.name
            try:
                path.rename(backup_path)
                backup_metadata = backup_path.lstat()
                if (backup_metadata.st_dev, backup_metadata.st_ino) != existing_identity:
                    raise FileExistsError(f"Planned file identity changed during overwrite: {path}")
                os.link(temporary_path, path)
            except BaseException:
                if os.path.lexists(backup_path) and not os.path.lexists(path):
                    os.link(backup_path, path)
                    backup_path.unlink()
                raise
            backup_path.unlink()
        else:
            raise ValueError(f"Unsupported file action: {action}")
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        if backup_root is not None:
            try:
                backup_root.rmdir()
            except OSError:
                pass


def execute_operation_plan(plan: OperationPlan) -> None:
    """Execute a previously validated plan without recomputing its actions."""

    for operation in plan.operations:
        path = (
            plan.resolved_target
            if operation.relative_path == "."
            else plan.resolved_target / operation.relative_path
        )

        if operation.relative_path == "." and operation.action == "create":
            # The target's canonical path was fixed during preflight. Parent
            # creation happens only after the full plan has been accepted.
            path.mkdir(parents=True, exist_ok=False)
            continue

        _verify_execution_state(plan, operation)

        if operation.kind == "directory":
            if operation.action == "create":
                path.mkdir()
            continue

        if operation.action == "skip":
            continue
        if operation.content is None:
            raise ValueError(f"File operation has no content: {operation.relative_path}")
        _atomic_write(
            path,
            operation.content,
            action=operation.action,
            existing_mode=operation.existing_mode,
            existing_identity=operation.existing_identity,
        )


def write_scaffold(
    target_dir: Path,
    project_name: str,
    *,
    force: bool,
    dry_run: bool,
) -> dict[str, list[str]]:
    """Build one full plan and either report or execute that exact plan."""

    plan = build_operation_plan(target_dir, project_name, force=force)
    summary = plan.summary()
    if not dry_run:
        execute_operation_plan(plan)
    return summary


def print_summary(target_dir: Path, summary: dict[str, list[str]], *, dry_run: bool) -> None:
    mode = "Dry run" if dry_run else "Scaffold"
    print(f"{mode} target: {target_dir}")
    for key in ("created", "skipped", "overwritten"):
        values = summary[key]
        print(f"{key}: {len(values)}")
        for value in values:
            print(f"  - {value}")


def main() -> int:
    args = parse_args()
    target_dir = Path(args.target_dir).expanduser()
    project_name = args.project_name or default_project_name(target_dir)

    summary = write_scaffold(target_dir, project_name, force=args.force, dry_run=args.dry_run)
    print_summary(target_dir, summary, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
