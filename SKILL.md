---
name: bootstrap-ai-native-project
description: Create a safe AI-native project scaffold or analyze an existing repository for agentic alignment. Use when asked to bootstrap, initialize, scaffold, reset, adopt, audit, or align an agent-ready project structure. For existing repositories, inventory and archive current agentic artifacts, acquire every decision-relevant connected context, and produce an evidence-backed recommendation without applying changes.
---

# Bootstrap AI-Native Project

Choose one workflow before acting:

- **Create:** Generate the complete scaffold in a new or intentionally reset target.
- **Align:** Analyze an existing project, preserve its agentic artifacts, resolve connected context, and recommend a non-destructive alignment.

Never use the create workflow or `--force` as a substitute for alignment.

## Create

From this skill directory:

```bash
python3 scripts/bootstrap_ai_native_project.py <target_dir> --project-name "Project Name"
```

1. Resolve the target. Default to the current workspace only when none is named.
2. Use `--dry-run` when the target may contain files. It performs the same preflight and reports the same collisions as execution.
3. Run without `--force` normally. Use `--force` only when the user explicitly authorized replacement of scaffold-managed ordinary files.
4. Treat a symlinked target root or symlink along a managed destination as a hard error.
5. Report every created, skipped, or overwritten path.
6. Capture the first outcome, relevant sources, action boundaries, checkpoint, and stop or return condition.

Do not invent a runtime, token source, package manager, or test command. Record a missing prerequisite in current state and stop or return for a project decision.

Read `references/scaffold-contract.md` before changing the generator, generated templates, path rules, or output structure.

## Align

Read `references/alignment-contract.md` completely before inspecting or recommending changes to an existing repository.

```bash
python3 scripts/inspect_existing_project.py <target> --format markdown
```

After explicit archive authorization:

```bash
python3 scripts/inspect_existing_project.py <target> --format json --archive-dir <disjoint_archive_path>
```

1. Inventory the repository without mutating it or writing elsewhere. Omit `--archive-dir` for this default phase.
2. With explicit archive authorization, rerun with a named `--archive-dir` and verify the non-destructive archive outside the source tree.
3. Identify every decision-relevant connected context and request its content, authority, owner, and freshness.
4. Do not recommend an alignment until each required context is acquired, explicitly unavailable, or waived by the user.
5. Classify evidence and proposals as `adopt`, `link`, `create`, `patch`, or `defer`.
6. Stop after the evidence-backed recommendation. Applying any change requires a later, separate approval of the exact diff.

The inspector has no apply mode. Do not edit, move, merge, rename, or delete source artifacts during alignment.

## Context Model

Treat these as semantic roles, not mandatory filenames or locations:

- Stable instructions and intent
- Mutable current state
- Context and authority map
- Decision history

In create mode, the scaffold supplies conventional files for these roles. In align mode, map and preserve the project's existing sources; do not reconstruct old decisions or automatically merge their meaning.

## Resources

- `scripts/bootstrap_ai_native_project.py`: Deterministic scaffold generator.
- `scripts/inspect_existing_project.py`: Read-only repository inventory and external archive tool.
- `scripts/install_skill.py`: Installer for the Codex skills directory.
- `references/scaffold-contract.md`: Create-mode structure and safety contract.
- `references/alignment-contract.md`: Existing-project evidence, archival, context, and recommendation contract.
