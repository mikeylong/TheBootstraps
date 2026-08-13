# TheBootstraps

TheBootstraps is a Codex skill with two explicit workflows:

- **Create** gives a new project a safe, agent-ready context system before implementation begins.
- **Align** analyzes an existing project, preserves its agentic artifacts, gathers its connected context, and produces an evidence-backed recommendation without changing the source.

Alignment is not greenfield generation with `--force`. Existing repositories keep their own structure and authority unless a later, exact diff is separately approved.

## Create a New Project

Install the skill into Codex:

```bash
python3 scripts/install_skill.py --force
```

Create a scaffold:

```bash
python3 scripts/bootstrap_ai_native_project.py ./example-project --project-name "Example AI-Native Project"
```

Useful options:

- `--dry-run`: Run the same preflight as execution and preview the planned changes without writing.
- `--force`: Replace scaffold-managed ordinary files only when that replacement is intentional. It never permits symlinks or incompatible path types.
- `--project-name`: Set the display name used in generated starter content.

The generator validates the complete operation before mutating the target. Without `--force`, it preserves existing ordinary files; it always preserves files outside the scaffold contract.

### What Create Generates

```text
example-project/
|-- README.md
|-- AGENTS.md
|-- CURRENT.md
|-- CONTEXT_MAP.md
|-- DECISIONS.md
|-- DESIGN.md
|-- specs/
|   |-- feature-spec.md
|   `-- interface-contract.md
|-- .agents/
|   `-- skills/
|       |-- build-page/
|       |   |-- SKILL.md
|       |   |-- agents/
|       |   |   `-- openai.yaml
|       |   `-- examples.md
|       |-- refactor-component/
|       |   |-- SKILL.md
|       |   |-- agents/
|       |   |   `-- openai.yaml
|       |   `-- checks.md
|       `-- write-tests/
|           |-- SKILL.md
|           `-- agents/
|               `-- openai.yaml
|-- contracts/
|   |-- design-tokens.schema.json
|   `-- component-rules.json
|-- plans/
`-- tests/
```

Each repository-local skill under `.agents/skills/` is a complete Codex package with `SKILL.md` and `agents/openai.yaml`.

The generated context files have deliberately different jobs:

- `AGENTS.md`, `DESIGN.md`, `specs/`, and `contracts/` hold stable instructions and constraints.
- `CURRENT.md` is the short, mutable source of truth for what is happening now.
- `CONTEXT_MAP.md` routes agents to relevant sources and records their authority instead of copying everything into one file.
- `DECISIONS.md` is append-only history for consequential decisions, evidence, and superseded assumptions.
- `plans/` is available for complex work that needs a checked-in execution plan.

The generated front door asks the first person or agent to record:

1. The outcome and definition of done.
2. The relevant sources and their authority.
3. Action and approval boundaries.
4. The first useful, reviewable checkpoint.
5. The condition for stopping and returning control.

The scaffold deliberately does not choose a runtime, create concrete design tokens, or invent a test command. Missing prerequisites remain explicit decisions.

A run reports the target and classifies every managed path as created, skipped, or overwritten. A dry-run reports the same planned classifications without writing. The generated files, rather than the receipt, become the project's ongoing source of truth.

## Align an Existing Project

Run the read-only inventory first. With no archive option, it writes nothing:

```bash
python3 scripts/inspect_existing_project.py ./existing-project --format markdown
```

Then explicitly opt in to a preservation archive at a path disjoint from the source:

```bash
python3 scripts/inspect_existing_project.py ./existing-project \
  --format markdown \
  --archive-dir ./existing-project-agentic-archive
```

JSON output is also available for tools and downstream analysis:

```bash
python3 scripts/inspect_existing_project.py ./existing-project \
  --format json \
  --archive-dir ./existing-project-agentic-archive
```

The inspector never creates a default archive. `--archive-dir` explicitly authorizes that external write action; it does not authorize source changes. The archive and source must be completely disjoint.

Alignment follows this gate:

1. **Inventory:** Read the repository, its nested scopes, and references without changing filesystem state.
2. **Preserve:** After explicit archive authorization, copy existing agent instructions, skills, prompts, context files, and related agentic artifacts byte-for-byte where safe to the named external path.
3. **Request context:** Identify every connected source that could materially change the recommendation, including its authority, owner, freshness, and access status.
4. **Resolve access:** Acquire each required context or record that it is explicitly unavailable or waived by the user.
5. **Recommend:** Show what to `adopt`, `link`, `create`, `patch`, or `defer`, grounded in the resolved evidence.

The archive preserves relative paths and records hashes and file types. It records symlinks without following them. Suspected sensitive content is not copied; exclusions and their reasons remain visible in the manifest. Creating the archive does not move, rename, rewrite, or delete the originals.

The four context layers are semantic roles, not required filenames:

- Stable instructions and intent
- Mutable current state
- Context and authority map
- Decision history

An existing `AGENTS.md`, ADR directory, product document, tracker, or other source may already fill one of those roles. Alignment maps that evidence instead of imposing the create-mode tree. It never automatically merges documents or reconstructs historical decisions from commits, chats, or inference.

### V1 Boundary

V1 stops at an evidence-backed recommendation. The inspector has no apply mode and never changes the inspected source.

Inspection, archival, and permission to recommend do not authorize implementation. Any later application is a separate, manual workflow and requires approval of the exact proposed diff. The recommendation must also identify what will remain untouched.

See `references/alignment-contract.md` for the complete evidence, archive, context-resolution, and recommendation rules.

## Repository Layout

```text
TheBootstraps/
|-- SKILL.md
|-- agents/
|   `-- openai.yaml
|-- scripts/
|   |-- bootstrap_ai_native_project.py
|   |-- inspect_existing_project.py
|   `-- install_skill.py
|-- references/
|   |-- alignment-contract.md
|   `-- scaffold-contract.md
`-- tests/
```

`SKILL.md` routes create and align requests. Each workflow's detailed invariants live in its matching contract under `references/`.

## Validation

Run the standard-library regression suite:

```bash
python3 -m unittest discover -s tests -v
```

Then run both skill-package validators:

```bash
python3 "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" .
python3 "$HOME/.codex/skills/skillskill/scripts/validate_skill.py" --expect-codex .
```

After creating a fixture, validate every generated repository-local skill with both validators:

```bash
for skill_dir in ./example-project/.agents/skills/*; do
  python3 "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" "$skill_dir"
  python3 "$HOME/.codex/skills/skillskill/scripts/validate_skill.py" --expect-codex "$skill_dir"
done
```
