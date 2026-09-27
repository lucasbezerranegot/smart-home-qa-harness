## Summary

Describe the delivered behavior and why it is needed.

## Requirements

List every requirement delivered or affected by this pull request.

- Closes #ISSUE_NUMBER — `REQ-AREA-000`
- Relates to #ISSUE_NUMBER — `REQ-AREA-000`

## Acceptance criteria and verification

| Requirement | Acceptance evidence |
|---|---|
| `REQ-AREA-000` | Test, Gherkin scenario, dry-run, or documented verification |

## Commit mapping

- `REQ-AREA-000`: `commit-hash`, `commit-hash`

## Safety and failure behavior

Describe fail-safe behavior, authorization gates, retries, rollback, and any real-device impact.

## Test results

```text
Paste the relevant test and coverage summary here.
```

## Operational notes

Document configuration, deployment, migration, manual verification, and rollback steps. Write `Not applicable` when appropriate.

## Checklist

- [ ] Requirement Issues use the repository template and are written in English.
- [ ] Acceptance criteria are covered by automated tests or documented verification.
- [ ] External HTTP behavior is mocked in CI.
- [ ] Secrets, device identifiers, and personal measurements are not committed.
- [ ] Documentation and `.env.example` are updated when configuration changes.
- [ ] The pull request targets the default branch before using closing keywords.
