# Scaffold Contract

Use this reference when changing `scripts/bootstrap_ai_native_project.py`, its generated templates, or tests that define the generated contract.

## Contents

- [Purpose](#purpose)
- [Required structure](#required-structure)
- [Context model](#context-model)
- [First workflow contract](#first-workflow-contract)
- [File intent](#file-intent)
- [Safety and preflight invariants](#safety-and-preflight-invariants)
- [Admission rules](#admission-rules)
- [Maintenance and validation](#maintenance-and-validation)

## Purpose

Turn an empty or partially populated directory into an agent-ready workspace without inventing feature details, runtime choices, credentials, or commands. The scaffold separates durable constraints from changing execution state so a fresh agent can recover the project accurately without treating conversation history as authority.

## Required Structure

```text
README.md
AGENTS.md
CURRENT.md
CONTEXT_MAP.md
DECISIONS.md
DESIGN.md
specs/feature-spec.md
specs/interface-contract.md
.agents/skills/build-page/SKILL.md
.agents/skills/build-page/agents/openai.yaml
.agents/skills/build-page/examples.md
.agents/skills/refactor-component/SKILL.md
.agents/skills/refactor-component/agents/openai.yaml
.agents/skills/refactor-component/checks.md
.agents/skills/write-tests/SKILL.md
.agents/skills/write-tests/agents/openai.yaml
contracts/design-tokens.schema.json
contracts/component-rules.json
plans/
tests/
```

Generate `plans/` as an available workspace, but do not invent a plan file. A project creates a checked-in plan only when the work is complex enough to benefit from one. Keep `tests/` empty until the project chooses a runtime and test framework.

`.agents/skills/` is the repository-local Codex discovery path. Each local skill must include `agents/openai.yaml` with UI-facing metadata that matches its `SKILL.md`. All generated instructions and examples must refer to these locations, never the legacy top-level `skills/` path.

## Context Model

Keep these layers separate and name their authority explicitly:

1. **Stable instructions and intent:** `AGENTS.md`, `DESIGN.md`, relevant `specs/`, and `contracts/` govern durable operating rules, desired behavior, and machine-readable constraints. Change them intentionally when the project contract changes.
2. **Mutable current state:** `CURRENT.md` is the concise source of truth for active execution. Rewrite it as checkpoints, blockers, authorization, or the next action changes.
3. **Context map:** `CONTEXT_MAP.md` is a routing layer. Point to sources instead of copying their full contents. For every important path or URL, record what it governs, its authority, when to read it, and an owner or freshness signal when useful.
4. **Append-only history:** `DECISIONS.md` records consequential choices, reasons, and evidence. Never delete or rewrite an earlier decision to make history look current. Append a new entry that identifies any decision it supersedes. When history conflicts with `CURRENT.md`, current state controls unless a governing source proves that state stale.

`README.md` is the human and agent front door across these layers. A separate file in `plans/` may carry detailed execution steps for complex work, but it must be linked from `CURRENT.md`; it does not replace current state.

### `CURRENT.md` Fields

Keep the file short and reviewable. Provide explicit prompts for:

- Outcome now
- Definition of done
- Active decisions
- Completed
- In progress
- Next action
- Open questions and blockers
- First useful checkpoint
- Stop or return condition
- Authorization and approval boundaries
- Active plan, when one exists

### `CONTEXT_MAP.md` Entry Fields

For each source, provide:

- Path or URL
- What it governs
- Authority level
- When to read it
- Owner or freshness signal, when useful

Do not imply that every listed source must be loaded for every task. The map exists to help the agent select only context relevant to the next decision.

### `DECISIONS.md` Entry Fields

Each consequential entry provides:

- Date or stable sequence identifier
- Decision
- Reason and evidence
- Scope
- Status when recorded
- Superseded decision identifier, when applicable

Treat a superseding entry as the historical record of replacement. Do not silently edit the earlier entry. Trivial progress belongs in `CURRENT.md`, not in the decision log.

## First Workflow Contract

The generated `README.md`, `CURRENT.md`, and `AGENTS.md` must give a new agent a copyable first action and require five inputs before meaningful implementation:

1. **Outcome:** State the result and definition of done.
2. **Relevant source material:** Register governing paths or URLs in `CONTEXT_MAP.md`, including their authority.
3. **Action boundaries:** Record what the agent may change and what still needs approval.
4. **First useful checkpoint:** Define the smallest reviewable result that can disprove a bad direction early.
5. **Stop or return condition:** State when the agent must stop, summarize evidence, and return control.

After a consequential checkpoint, update `CURRENT.md`. When evidence changes a decision, apply the new decision to unfinished work and append the reason to `DECISIONS.md`, identifying what it supersedes.

## File Intent

- `README.md`: Plain-language front door, repository map, and first workflow.
- `AGENTS.md`: Concise stable operating rules and routing order. Direct agents to read `CURRENT.md` first, use `CONTEXT_MAP.md` to select sources, then apply relevant stable constraints.
- `CURRENT.md`: Mutable execution state and handoff. It is not a chronological diary.
- `CONTEXT_MAP.md`: Source inventory, authority map, and selective-reading guide.
- `DECISIONS.md`: Append-only evidence-backed decision history.
- `DESIGN.md`: Stable design principles and contract expectations.
- `specs/feature-spec.md`: Neutral template for outcome, users, scope, requirements, acceptance criteria, risks, and open questions.
- `specs/interface-contract.md`: Neutral template for surfaces, states, inputs, outputs, agent responsibilities, constraints, and validation expectations.
- `.agents/skills/build-page/`: Codex-discoverable local workflow for page-level UI from active state, specs, and contracts.
- `.agents/skills/refactor-component/`: Codex-discoverable local workflow for changing components without breaking public behavior or contracts.
- `.agents/skills/write-tests/`: Codex-discoverable local workflow for translating acceptance criteria and risks into focused tests once a test command is known.
- `.agents/skills/*/agents/openai.yaml`: UI-facing metadata for each generated local skill; keep its display name, short description, and default prompt aligned with that skill's frontmatter and workflow.
- `contracts/design-tokens.schema.json`: JSON Schema for validating a future project token file; it is not itself a concrete token source.
- `contracts/component-rules.json`: Starter behavioral constraints for components.
- `plans/`: Optional detailed execution plans for complex work.
- `tests/`: Empty project test directory until the project selects a test framework.

Generated local skills must read `CURRENT.md` before acting, use `CONTEXT_MAP.md` to find relevant evidence, and update current state after a consequential checkpoint. They must not convert an empty template into inferred authorization.

## Safety and Preflight Invariants

The generator must create and validate one complete operation plan before any mutation. The same planner and validation path must serve dry-run and execution.

- Reject a symlinked target root and any symlink encountered in an existing path component from that root through a managed destination, for files or directories, with or without `--force`.
- Prove every resolved managed destination remains beneath the resolved target.
- Reject incompatible path types and parent-path collisions before creating any directory or file.
- Return the same collision error in dry-run and execution for the same starting tree.
- Leave the target unchanged when preflight fails. Do not create a partial scaffold.
- Without `--force`, preserve existing managed ordinary files and report them as skipped.
- With `--force`, replace only known scaffold-managed ordinary files. Preserve unknown files and directories.
- Use atomic file replacement after successful preflight so an individual managed file is never left partially written.
- Keep generated JSON parseable with Python's standard `json` module.

`--force` authorizes replacement; it never relaxes containment, symlink, or path-type validation.

## Admission Rules

The scaffold is deliberately stack-neutral. Its templates and local skills must not invent:

- A language runtime or package manager
- A concrete design-token source
- A test framework or test command
- Credentials, deployment targets, external publication, spending, deletion, or permission to contact people

When required input is absent, record the gap under open questions or blockers in `CURRENT.md`, state the affected checkpoint, and stop or return for a project decision. Do not turn a placeholder in `specs/` into authorization.

## Maintenance and Validation

- Keep generated content domain-neutral unless the user asks for project-specific starter content.
- Keep `SKILL.md` concise; place field definitions, output-tree details, and safety invariants here.
- Update all generated cross-links, this reference, README examples, and regression assertions together when a managed path changes.
- Preserve dry-run parity and no-partial-mutation behavior when adding a file or directory.
- Test default display-name derivation for hyphens, underscores, spaces, and names containing lowercase `s`.
- Require the source package and every generated local skill to pass both `quick_validate.py` and `validate_skill.py --expect-codex`; rerun them whenever metadata or local workflows change.

Run the regression suite and both package validators:

```bash
python3 -m unittest discover -s tests -v
python3 "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" .
python3 "$HOME/.codex/skills/skillskill/scripts/validate_skill.py" --expect-codex .
```

After generating a fixture, validate every repository-local skill with both validators:

```bash
for skill_dir in ./example-project/.agents/skills/*; do
  python3 "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" "$skill_dir"
  python3 "$HOME/.codex/skills/skillskill/scripts/validate_skill.py" --expect-codex "$skill_dir"
done
```

The unittest suite should cover clean generation, idempotence, `--force`, unknown-file preservation, default naming, dry-run parity, full preflight, no partial mutation, root and descendant symlink rejection, installer replacement behavior, generated repository-skill paths and metadata, both validators for every generated local skill, required context headings, and cross-links.
