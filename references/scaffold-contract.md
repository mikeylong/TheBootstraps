# Scaffold Contract

Use this reference when changing `scripts/bootstrap_ai_native_project.py` or reviewing generated output.

## Purpose

The scaffold turns an empty directory into an AI-native project workspace. It gives coding agents enough project context to act responsibly without inventing feature-specific examples.

## Required Structure

```text
README.md
AGENTS.md
DESIGN.md
specs/feature-spec.md
specs/interface-contract.md
skills/build-page/SKILL.md
skills/build-page/examples.md
skills/refactor-component/SKILL.md
skills/refactor-component/checks.md
skills/write-tests/SKILL.md
contracts/design-tokens.schema.json
contracts/component-rules.json
tests/
```

## Content Intent

- `README.md`: Project purpose, framework map, and first-run workflow.
- `AGENTS.md`: Operating rules for agents working inside the project.
- `DESIGN.md`: Design principles, token usage, and component-rule expectations.
- `specs/feature-spec.md`: A neutral feature specification template covering goal, users, scope, requirements, acceptance criteria, risks, and open questions.
- `specs/interface-contract.md`: A neutral interface contract template covering surfaces, states, inputs, outputs, agent responsibilities, constraints, and validation expectations.
- `skills/build-page/`: Local guidance for building page-level UI from specs and contracts.
- `skills/refactor-component/`: Local guidance for changing components without breaking contracts.
- `skills/write-tests/`: Local guidance for translating specs and risks into focused tests.
- `contracts/design-tokens.schema.json`: JSON Schema for validating design-token files.
- `contracts/component-rules.json`: Starter component rules consumed by agents as behavioral constraints.
- `tests/`: Empty default test directory.

## Maintenance Rules

- Keep the scaffold domain-neutral by default.
- Keep generated JSON valid and parseable by Python's standard `json` module.
- Do not add generated package-manager files unless the user chooses a runtime stack.
- Preserve overwrite safety: existing files must not be replaced unless `--force` is supplied.
- Update this reference whenever the generated structure or content intent changes.
