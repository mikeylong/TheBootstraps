#!/usr/bin/env python3
"""Create an AI-native project scaffold."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from string import Template
from textwrap import dedent


DIRECTORIES = [
    "specs",
    "skills/build-page",
    "skills/refactor-component",
    "skills/write-tests",
    "contracts",
    "tests",
]


FILES = {
    "README.md": """\
        # $project_name

        This project is organized for agent-assisted product and interface work. The repository separates intent, design constraints, local skills, and validation so AI agents can make changes against explicit project contracts.

        ## Structure

        - `AGENTS.md`: Operating rules for agents working in this repository.
        - `DESIGN.md`: Design principles and contract expectations.
        - `specs/`: Product and interface specs that define what should be built.
        - `skills/`: Project-local skills for common implementation workflows.
        - `contracts/`: Machine-readable rules for design tokens and components.
        - `tests/`: Test coverage for implemented behavior.

        ## First Workflow

        1. Fill in `specs/feature-spec.md` with the first project goal.
        2. Fill in `specs/interface-contract.md` for the relevant surfaces, states, inputs, and outputs.
        3. Use the local skill that matches the task: `build-page`, `refactor-component`, or `write-tests`.
        4. Validate implementation against `DESIGN.md`, `contracts/`, and the acceptance criteria in `specs/`.
    """,
    "AGENTS.md": """\
        # Agent Instructions

        ## Operating Rules

        - Read `README.md`, `DESIGN.md`, relevant files in `specs/`, and the applicable local skill before making changes.
        - Treat `contracts/` as project constraints. Do not bypass token or component rules without updating the contract and explaining the reason.
        - Preserve user work. Do not overwrite existing files unless the user explicitly asks for replacement.
        - Keep changes scoped to the active spec and avoid unrelated refactors.
        - Add or update tests for behavior that changes.

        ## Local Skills

        - Use `skills/build-page/SKILL.md` for page-level UI work.
        - Use `skills/refactor-component/SKILL.md` for component changes.
        - Use `skills/write-tests/SKILL.md` for test planning and implementation.

        ## Handoff

        Summaries should name the spec followed, the contracts checked, tests run, and any open questions that remain.
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
    "skills/build-page/SKILL.md": """\
        ---
        name: build-page
        description: Build or revise page-level UI from the active spec, interface contract, design contract, and component rules.
        ---

        # Build Page

        Use this local skill when creating or revising a page, flow, or major screen.

        ## Workflow

        1. Read `DESIGN.md`, `contracts/component-rules.json`, and the relevant files in `specs/`.
        2. Identify the required surfaces, states, inputs, and outputs.
        3. Reuse existing components and tokens before creating new patterns.
        4. Implement the smallest page-level change that satisfies the spec.
        5. Verify responsive behavior, state coverage, and acceptance criteria.

        ## Output

        Report the spec followed, the surfaces changed, tests run, and any contract updates needed.
    """,
    "skills/build-page/examples.md": """\
        # Build Page Examples

        ## Prompt

        Use `skills/build-page/SKILL.md` to build the surface described in `specs/feature-spec.md` and `specs/interface-contract.md`.

        ## Expected Agent Behavior

        - Read the spec and interface contract first.
        - Check `DESIGN.md` and component rules before introducing UI patterns.
        - Implement all required states listed in the interface contract.
        - Run focused tests or document why tests are not available.
    """,
    "skills/refactor-component/SKILL.md": """\
        ---
        name: refactor-component
        description: Refactor existing components while preserving behavior, design-token usage, component rules, and test coverage.
        ---

        # Refactor Component

        Use this local skill when changing component internals, variants, props, styles, or composition.

        ## Workflow

        1. Locate current usages and tests before editing.
        2. Read `DESIGN.md` and `contracts/component-rules.json`.
        3. Preserve public behavior unless the active spec requires a change.
        4. Keep token usage and component variants aligned with project contracts.
        5. Update tests for any behavior, state, or accessibility change.

        ## Output

        Report changed components, preserved public interfaces, tests run, and any migration notes.
    """,
    "skills/refactor-component/checks.md": """\
        # Component Refactor Checks

        - Public props, exported names, and event behavior are preserved or intentionally migrated.
        - Token usage still follows `DESIGN.md` and `contracts/`.
        - Loading, empty, error, disabled, active, and success states still render as expected.
        - Existing tests pass and new tests cover changed behavior.
        - Call sites are updated when an intentional interface change is made.
    """,
    "skills/write-tests/SKILL.md": """\
        ---
        name: write-tests
        description: Write focused tests from specs, interface contracts, risks, acceptance criteria, and changed behavior.
        ---

        # Write Tests

        Use this local skill when adding or updating tests for project behavior.

        ## Workflow

        1. Read the active spec and interface contract.
        2. Map acceptance criteria and risks to test cases.
        3. Prefer behavior-level assertions over implementation details.
        4. Cover important states, validation, and failure modes.
        5. Run the relevant test command and report the result.

        ## Output

        Report test files changed, criteria covered, command output summary, and remaining gaps.
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
    name = target_dir.resolve().name
    if not name:
        return "AI-Native Project"
    words = re.split(r"[-_\\s]+", name)
    return " ".join(word.capitalize() for word in words if word) or "AI-Native Project"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an AI-native project scaffold.")
    parser.add_argument("target_dir", help="Directory where the scaffold should be created.")
    parser.add_argument("--project-name", help="Display name to use in starter content.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing scaffold files.")
    parser.add_argument("--dry-run", action="store_true", help="Show planned changes without writing files.")
    return parser.parse_args()


def write_scaffold(target_dir: Path, project_name: str, *, force: bool, dry_run: bool) -> dict[str, list[str]]:
    summary = {"created": [], "skipped": [], "overwritten": []}

    for directory in DIRECTORIES:
        path = target_dir / directory
        exists = path.exists()
        if dry_run:
            if not exists:
                summary["created"].append(f"{directory}/")
            continue
        if exists and not path.is_dir():
            raise FileExistsError(f"Cannot create directory because a file exists: {path}")
        path.mkdir(parents=True, exist_ok=True)
        if not exists:
            summary["created"].append(f"{directory}/")

    for relative_path, template in FILES.items():
        path = target_dir / relative_path
        content = normalize_content(template, project_name)
        exists = path.exists()

        if exists and not force:
            summary["skipped"].append(relative_path)
            continue

        if dry_run:
            summary["overwritten" if exists else "created"].append(relative_path)
            continue

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        summary["overwritten" if exists else "created"].append(relative_path)

    return summary


def print_summary(target_dir: Path, summary: dict[str, list[str]], *, dry_run: bool) -> None:
    mode = "Dry run" if dry_run else "Scaffold"
    print(f"{mode} target: {target_dir}")
    for key in ("created", "skipped", "overwritten"):
        values = summary[key]
        print(f"{key}: {len(values)}")
        for value in values:
            print(f"  - {value}")


def validate_generated_json(target_dir: Path, summary: dict[str, list[str]], *, dry_run: bool) -> None:
    if dry_run:
        return
    for relative_path in ("contracts/design-tokens.schema.json", "contracts/component-rules.json"):
        if relative_path not in summary["created"] and relative_path not in summary["overwritten"]:
            continue
        json.loads((target_dir / relative_path).read_text(encoding="utf-8"))


def main() -> int:
    args = parse_args()
    target_dir = Path(args.target_dir).expanduser()
    project_name = args.project_name or default_project_name(target_dir)

    if not args.dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)

    summary = write_scaffold(target_dir, project_name, force=args.force, dry_run=args.dry_run)
    validate_generated_json(target_dir, summary, dry_run=args.dry_run)
    print_summary(target_dir, summary, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
