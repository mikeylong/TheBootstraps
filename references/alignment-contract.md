# Existing-Project Alignment Contract

Use this reference for every existing-project alignment and before changing `scripts/inspect_existing_project.py`, its report schema, archival rules, context gate, or tests.

## Contents

- [Purpose and boundary](#purpose-and-boundary)
- [Workflow](#workflow)
- [Inventory](#inventory)
- [Archive contract](#archive-contract)
- [Connected-context gate](#connected-context-gate)
- [Semantic context roles](#semantic-context-roles)
- [Recommendation contract](#recommendation-contract)
- [Safety and validation](#safety-and-validation)

## Purpose and Boundary

Align an existing repository to an agent-ready operating pattern without treating it as a blank target or presuming its current structure is wrong.

V1's default inventory mode is fully read-only and writes nothing. Archive creation is a separate, explicit opt-in write action enabled only by `--archive-dir`, and it may write only at a path fully disjoint from the source. V1 stops after an evidence-backed recommendation and provides no apply mode.

Authorization to inspect, archive, gather context, or recommend does not authorize changing the repository. Any later implementation must be a separate workflow based on the exact proposed diff and a separate user approval.

## Workflow

Follow this order without skipping a gate:

1. Resolve and validate the exact repository or monorepo scope.
2. Inventory repository-local evidence without mutation or external writes.
3. After explicit archive authorization, create and verify the named external archive of existing agentic artifacts.
4. Identify every decision-relevant connected context.
5. Request its content and establish authority, owner, freshness, and access status.
6. Resolve every required-context request as acquired, explicitly unavailable, or user-waived.
7. Reconcile the evidence and identify conflicts or uncertainty.
8. Produce a recommendation using the allowed action classes.
9. Stop. Do not apply the recommendation.

Run the deterministic inspector from the skill directory:

```bash
python3 scripts/inspect_existing_project.py <target> [--format json|markdown] [--archive-dir PATH]
```

Omit `--archive-dir` for the default write-free inventory. Supplying it explicitly authorizes creation of one new external archive; it does not authorize any source change.

The same inspection must produce equivalent facts in JSON and Markdown. Output formatting must not change discovery, exclusions, or archive contents.

## Inventory

Inventory before judging. At minimum, inspect when present:

- Root and nested agent instruction files
- Repository-local skills, prompts, commands, hooks, and agent configuration
- Current-state, context-map, plan, handoff, specification, and decision artifacts
- README, contribution, architecture, security, and governance documentation
- Runtime manifests, workspace definitions, test configuration, and CI workflows
- Git remotes, submodules, linked repositories, and repository scope boundaries
- References to issue trackers, pull requests, design systems, documents, deployments, observability, data sources, and other external systems

Treat discovered commands and conventions as evidence, not automatic authority. Distinguish literal facts, inferred candidates, and confirmed governing sources in the report.

Do not follow repository symlinks during discovery. Record the link and its target text as evidence, then require separate authority before inspecting the destination.

## Archive Contract

Create the archive before making any recommendation, but only after the caller explicitly supplies `--archive-dir`. If a valid archive cannot be created and verified, stop with an evidence report.

The archive path must be fully disjoint from the source: it cannot equal, contain, or be contained by the resolved target. Reject ambiguous or overlapping paths before writing.

Archive existing agentic artifacts non-destructively:

- Leave every source path and byte unchanged.
- Copy eligible ordinary files byte-for-byte under their original relative paths.
- Record directories and file types needed to explain the preserved tree.
- Record symlinks and their link-target text without following them.
- Never move, rename, rewrite, delete, or replace a source artifact.
- Do not write archive receipts, manifests, or markers inside the inspected repository.

Include a machine-readable manifest with, at minimum:

- Resolved source and archive roots
- Inspection time and repository revision or dirty-state evidence when available
- Original relative path and file type for every candidate artifact
- Size and SHA-256 digest for every copied ordinary file
- Link-target text for every recorded symlink
- Status for each candidate: copied, excluded, or failed
- Reason for every exclusion or failure

Exclude suspected sensitive content rather than copying it. Sensitive candidates include credentials, private keys, tokens, secrets, environment files, and files whose names or detected content indicate authentication material. Record only the relative path, exclusion classification, and reason; never place a secret value or content-derived excerpt in the manifest or report.

An archive is verified only after every copied file's digest matches its source and every candidate has a manifest disposition.

## Connected-Context Gate

A connected context is decision-relevant when its contents or authority could materially change what the alignment should adopt, preserve, add, patch, or defer. Discover connections from repository evidence rather than assuming a fixed list.

For every decision-relevant context, record:

- Stable identifier, path, or URL
- What decision or project area it can govern
- Why it is relevant
- Expected authority and owner
- Freshness signal or last-known date
- Access status and acquisition evidence
- Required disposition

Request the context and confirmation of its authority before recommending. Use a connected tool only when it is available, authorized, and within the requested scope. If access or authority cannot be established, ask the user rather than silently downgrading the source or guessing from nearby evidence.

Every required context must reach exactly one gate status:

- **Acquired:** Content and authority were inspected and recorded.
- **Explicitly unavailable:** The owner or user confirmed it cannot be supplied; record the resulting evidence limit.
- **Waived:** The user knowingly allowed recommendation without it; record the waiver and bounded consequence.

Do not recommend while a required context is merely pending, inaccessible without disposition, stale without owner confirmation, or unrequested. Do not present an unavailable or waived source as supporting evidence.

## Semantic Context Roles

Evaluate four roles without requiring any particular filename, directory, or tool:

1. **Stable instructions and intent:** Durable constraints, policies, architecture, product intent, and behavioral contracts.
2. **Mutable current state:** The active outcome, progress, blockers, authority boundaries, checkpoint, and stop condition.
3. **Context and authority map:** Routing information that says what each source governs, when to read it, and how authoritative or fresh it is.
4. **Decision history:** Consequential choices, evidence, status, and explicit supersession over time.

An existing artifact may contribute to more than one role. State its authority for each role rather than renaming or copying it into the create-mode filenames.

Do not reconstruct past decisions from Git history, chats, code shape, or inferred intent. If no authoritative decision record exists, recommend a forward-only practice and leave the historical gap explicit.

## Recommendation Contract

Classify every proposed treatment with exactly one action:

- **Adopt:** Keep and use an existing artifact in place because evidence shows it already fills the role.
- **Link:** Point agents to an existing authoritative source without duplicating it.
- **Create:** Propose a new artifact only for a demonstrated uncovered role.
- **Patch:** Propose a minimal, exact change to an existing artifact while preserving its other meaning.
- **Defer:** Make no change because evidence, authority, scope, or conflict resolution is incomplete.

Do not automatically merge the semantics of existing artifacts. Do not replace an established system merely because its names differ from the create scaffold. Conflicting authorities require owner resolution or `defer`.

The recommendation must include:

- Inspection scope and archive receipt
- Evidence inventory and required-context disposition table
- Existing coverage of the four semantic roles
- Authority conflicts, uncertainties, and evidence limitations
- Each proposed action, its evidence, target, and intended effect
- Exact patch text or diff for every `patch`
- Explicitly untouched artifacts and systems
- Validation and rollback expectations for a possible later implementation

End by stating that no source changes were made. A later request to apply must present the exact diff for approval; approval of the recommendation alone is insufficient.

## Safety and Validation

The inspector must:

- Keep source traversal and archive writing separate.
- Reject source/archive overlap in either containment direction.
- Refuse to follow symlinks or escape the resolved source scope.
- Avoid emitting secret values in archives, reports, errors, or logs.
- Fail closed before recommendation when archival verification or the context gate is incomplete.
- Produce deterministic ordering so reports and manifests are reviewable.
- Perform no source writes. Compare stable path/type/mode/size/time/device/inode metadata before and after inspection, and verify copied artifact bytes separately; describe this as a mutation check rather than absolute proof of byte identity.

Tests should cover read-only operation, clean and dirty repositories, nested instruction scopes, monorepos, symlinks, sensitive exclusions, byte and hash fidelity, source/archive overlap, missing access, explicit unavailability, user waivers, unresolved authority conflicts, deterministic output, and JSON/Markdown fact parity.
