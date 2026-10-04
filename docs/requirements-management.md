# Requirements Management

This document defines how product and quality requirements are created, traced, implemented, and closed in this repository. It is the source of truth for the requirement-writing process. GitHub Issues are the canonical records for individual requirements and their current status.

## Objectives

The process must make it possible to answer four questions:

1. Why does a behavior exist?
2. Which acceptance criteria define the behavior?
3. Which code and tests implement the requirement?
4. Which pull request delivered the requirement?

The intended traceability chain is:

```text
Requirement ID / GitHub Issue
        -> branch
        -> commits
        -> pull request
        -> code and automated tests
        -> merge into the default branch
```

## Requirement language

All requirement records must be written in English. Code identifiers may be included when they improve traceability, but the requirement must describe observable behavior rather than merely naming an implementation task.

Use normative language consistently:

- **must** for mandatory behavior;
- **must not** for prohibited behavior;
- **should** for a recommendation that may have a justified exception;
- **may** for an explicitly optional behavior.

## Requirement identifiers

Every requirement receives a stable identifier in its title:

```text
REQ-<AREA>-<NUMBER> — <observable capability>
NFR-<AREA>-<NUMBER> — <quality attribute or operational constraint>
```

Supported area codes are:

| Code | Area |
|---|---|
| `DATA` | Environmental data acquisition and validation |
| `HEAT` | Heating control |
| `HUM` | Humidifier control |
| `NTF` | Notifications |
| `OBS` | Observability |
| `OPS` | Runtime and deployment operations |
| `QA` | Verification and quality gates |
| `ROOM` | Room and device configuration |
| `SAFE` | Cross-cutting safety behavior |
| `STATE` | Persistent state and concurrency |
| `UI` | Browser dashboard and installable web experience |
| `VNT` | Ventilation decisions |

Identifiers are never reused. Renaming a requirement does not change its identifier. A materially different behavior receives a new identifier and links to the superseded requirement.

## Requirement scope

Create one requirement for one independently verifiable behavior. Acceptance criteria, error cases, and safety guards that exist only to make that behavior correct belong in the same Issue.

Create separate requirements when behaviors:

- can be delivered or prioritized independently;
- affect different actors or devices;
- have distinct safety consequences;
- require separate acceptance decisions.

Do not create requirements for refactoring steps, individual classes, file creation, or test-only mechanics unless they represent a genuine non-functional constraint.

## Required content

Every requirement Issue must contain:

- stable requirement ID and concise title;
- lifecycle status;
- origin and rationale;
- user story or system objective;
- testable acceptance criteria;
- safety and failure behavior where applicable;
- explicit out-of-scope items;
- traceability to code, tests, commits, and pull requests;
- dependencies or related requirements.

Acceptance criteria should use Given/When/Then when boundaries, state transitions, or failures matter. Use checklist statements for simple structural constraints.

## Lifecycle

| Status | Meaning |
|---|---|
| `Planned` | Accepted into the backlog but implementation has not started. |
| `In progress` | A branch, commit, or uncommitted implementation exists, but the requirement is not on the default branch. |
| `Implemented` | The acceptance criteria are implemented, verified, and merged into the default branch. |
| `Blocked` | Progress requires a decision or external dependency. |
| `Superseded` | Another requirement replaced this behavior. |

Retrospective requirements must state that they were documented after implementation. They must still describe business behavior and cite existing evidence.

## Workflow for new work

1. Search existing Issues and the [requirements catalog](requirements-catalog.md) to prevent duplicates.
2. Create the requirement with the repository requirement template.
3. Assign the next unused ID for the relevant area.
4. Agree on acceptance criteria before implementation where practical.
5. Create a branch that includes the Issue number, for example `codex/42-room-ventilation`.
6. Reference the Issue in commits with `Refs #42` or `(#42)`.
7. Add the requirement and verification evidence to the pull request description.
8. Use `Closes #42` in a pull request targeting the default branch.
9. Merge only after the acceptance criteria have test or documented verification evidence.
10. Update the requirements catalog if the status or traceability summary changed.

GitHub closing keywords are placed in the pull request description rather than relying only on a commit message. This keeps the pull request visible as the delivery record and closes the Issue only after the pull request reaches the default branch.

## Existing commits without Issue numbers

Do not rewrite stable history only to add Issue numbers. Create the retrospective requirement and map the existing hashes in its Traceability section. The delivering pull request can close multiple related Issues:

```markdown
Closes #12
Closes #13

## Commit mapping

- #12: `b29e719`, `69bff46`
- #13: `7d83e1e`, `2c6ba7b`
```

## Branches and commits

Preferred branch format:

```text
codex/<issue-number>-<short-description>
```

Preferred commit examples:

```text
feat(heating): add hysteresis control (#42)
test(heating): cover threshold boundaries (#42)
fix(ventilation): isolate missing room readings (#51)
```

One commit may support more than one requirement when the behaviors cannot be separated safely. Record that mapping in the pull request rather than forcing artificial commits.

## Verification evidence

Evidence may include:

- Gherkin scenarios under `tests/features/`;
- unit or component-integration tests;
- mocked provider failures;
- a safe dry-run result;
- an explicitly authorized real-device smoke test;
- CI and coverage results;
- operational journal output for a controlled pilot.

Real-device verification supplements deterministic automated tests; it does not replace them.

## Definition of Ready

A requirement is ready for implementation when:

- its purpose and actor are clear;
- acceptance criteria include important boundaries and failure paths;
- safety behavior is explicit;
- dependencies and exclusions are recorded;
- the requirement does not conflict with another active requirement.

## Definition of Done

A requirement is implemented only when:

- all mandatory acceptance criteria are satisfied;
- automated tests cover the deterministic behavior;
- external calls are mocked in CI;
- documentation and safe operational instructions are updated when applicable;
- the pull request links and closes the Issue;
- the quality gate passes on the supported Python version;
- any required manual hardware verification is recorded without committing secrets or personal measurements.

## Changes discovered during implementation

If work on `codex/refactor-room-ventilation` or another branch reveals a new behavior:

1. Decide whether it is an acceptance criterion of an existing requirement or an independently valuable behavior.
2. If independent, create a new requirement before merging the behavior.
3. Mark it `In progress` and link the current branch or commits.
4. Update affected requirements when a threshold, schedule, or safety rule changes.
5. Never silently change a requirement by changing only its tests or constants.
