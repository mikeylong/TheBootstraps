# TheBootstraps

TheBootstraps is a Codex skill for creating an agent-ready AI-native project scaffold.

It gives a new project the files an agent needs before implementation starts: operating rules, design constraints, neutral spec templates, local project skills, machine-readable contracts, and a place for tests.

## What It Creates

Running the bootstrap script creates this project structure:

```text
example-project/
|-- README.md
|-- AGENTS.md
|-- DESIGN.md
|-- specs/
|   |-- feature-spec.md
|   `-- interface-contract.md
|-- skills/
|   |-- build-page/
|   |   |-- SKILL.md
|   |   `-- examples.md
|   |-- refactor-component/
|   |   |-- SKILL.md
|   |   `-- checks.md
|   `-- write-tests/
|       `-- SKILL.md
|-- contracts/
|   |-- design-tokens.schema.json
|   `-- component-rules.json
`-- tests/
```

The generated `specs/` files are templates, not fake feature examples. They are meant to be filled in with the first real project goal and interface contract.

## Use It

Install the skill into Codex:

```bash
python3 scripts/install_skill.py --force
```

Create a new scaffold:

```bash
python3 scripts/bootstrap_ai_native_project.py ./example-project --project-name "Example AI-Native Project"
```

Useful options:

- `--dry-run`: Show what would be created without writing files.
- `--force`: Replace existing scaffold files intentionally.
- `--project-name`: Set the display name used in generated starter content.

## Result

A normal run reports the directories and files it created:

```text
Scaffold target: ./example-project
created: 18
  - specs/
  - skills/build-page/
  - skills/refactor-component/
  - skills/write-tests/
  - contracts/
  - tests/
  - README.md
  - AGENTS.md
  - DESIGN.md
  - specs/feature-spec.md
  - specs/interface-contract.md
  - skills/build-page/SKILL.md
  - skills/build-page/examples.md
  - skills/refactor-component/SKILL.md
  - skills/refactor-component/checks.md
  - skills/write-tests/SKILL.md
  - contracts/design-tokens.schema.json
  - contracts/component-rules.json
skipped: 0
overwritten: 0
```

The important part is the shape of the generated project:

- `README.md`, `AGENTS.md`, and `DESIGN.md` give agents the project frame.
- `specs/feature-spec.md` and `specs/interface-contract.md` define what should be built and how the interface should behave.
- `skills/` carries project-local workflows for building pages, refactoring components, and writing tests.
- `contracts/` holds JSON constraints for tokens and component rules.
- `tests/` starts empty so the project can choose its runtime and test framework later.

## Repository Layout

This repository is the skill package:

```text
TheBootstraps/
|-- SKILL.md
|-- agents/
|   `-- openai.yaml
|-- scripts/
|   |-- bootstrap_ai_native_project.py
|   `-- install_skill.py
`-- references/
    `-- scaffold-contract.md
```

`SKILL.md` is the agent-facing workflow. `scripts/bootstrap_ai_native_project.py` does the deterministic scaffold work. `references/scaffold-contract.md` is the maintenance contract for changing the generated structure.

## Validation

Validate the source skill package:

```bash
python3 "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" .
python3 "$HOME/.codex/skills/skillskill/scripts/validate_skill.py" --expect-codex .
```

Check the generated scaffold against a temporary directory:

```bash
tmpdir=$(mktemp -d)
python3 scripts/bootstrap_ai_native_project.py "$tmpdir/example-project" --project-name "Example AI-Native Project"
find "$tmpdir/example-project" -maxdepth 4 -print | sort
rm -rf "$tmpdir"
```
