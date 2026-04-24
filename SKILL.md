---
name: bootstrap-ai-native-project
description: Create an AI-native project scaffold with README, AGENTS, DESIGN, neutral specs, local project skills, design contracts, and tests; use when asked to bootstrap, initialize, scaffold, or reset an agent-ready project structure.
---

# Bootstrap AI-Native Project

## Overview

Use this skill to create the baseline project structure for an AI-native codebase. The scaffold is intentionally domain-neutral: it creates reusable spec templates, local agent skills, design contracts, and project operating docs without fake product examples.

## Quick Start

Run the bundled script from this skill directory:

```bash
python3 scripts/bootstrap_ai_native_project.py <target_dir> --project-name "Project Name"
```

Useful options:

- `--dry-run`: Show what would be created without writing files.
- `--force`: Overwrite existing scaffold files intentionally.
- `--project-name NAME`: Use a display name in generated starter content.

## Workflow

1. Resolve the target directory from the user's request. Default to the current workspace only when the user does not name a target.
2. Run `--dry-run` first if the target may contain existing files.
3. Run the script without `--force` for normal creation. If it reports skipped existing files, ask before rerunning with `--force` unless the user already requested replacement.
4. After creation, report the generated path and summarize any skipped or overwritten files.
5. If the user asks to change the scaffold contract, read `references/scaffold-contract.md` before editing the script.

## Output Contract

The script creates this structure:

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

The `specs/` files are templates, not sample product specs. Keep them neutral unless the user explicitly asks for project-specific starter examples.

## Edge Cases

- If the target directory does not exist, the script creates it.
- If scaffold files already exist, the script skips them unless `--force` is set.
- If the user asks for a different spec naming scheme, preserve the neutral template intent unless they explicitly want examples.
- If the generated contracts need to change, keep them valid JSON and update `references/scaffold-contract.md` with the new contract shape.

## Resources

- `scripts/bootstrap_ai_native_project.py`: Deterministic scaffold generator.
- `scripts/install_skill.py`: Local installer for copying this skill repo into the Codex skills directory.
- `references/scaffold-contract.md`: Structure and content contract for maintaining the generator.
