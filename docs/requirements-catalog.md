# Requirements Catalog

This catalog is the versioned index of product and quality requirements. The linked GitHub Issue is the canonical record for acceptance criteria, discussion, and current lifecycle state. The process for adding and tracing requirements is defined in [Requirements Management](requirements-management.md).

## Implemented on the default branch

| ID | Requirement | Area | Evidence summary | GitHub Issue |
|---|---|---|---|---|
| `REQ-VNT-001` | Recommend evening ventilation for summer cooling | Ventilation | Decision engine, unit and integration tests | [#3](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/3) |
| `REQ-VNT-002` | Recommend closing windows for summer heat protection | Ventilation | Decision engine, unit and integration tests | [#4](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/4) |
| `REQ-VNT-003` | Recommend humidity ventilation on cool days | Ventilation | Decision engine and BDD scenarios | [#5](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/5) |
| `REQ-VNT-004` | Restrict ventilation decisions to configured periods | Ventilation | Boundary tests and BDD scenarios | [#6](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/6) |
| `REQ-DATA-001` | Read current and forecast outdoor temperature | Data | Open-Meteo client tests | [#7](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/7) |
| `REQ-DATA-002` | Read validated indoor temperature and humidity | Data | SwitchBot Meter client tests | [#8](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/8) |
| `REQ-NTF-001` | Deliver window recommendations through Voice Monkey | Notifications | Webhook adapter and guarded smoke test | [#9](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/9) |
| `REQ-NTF-002` | Suppress duplicate notifications per action period | Notifications | Persistent reservation store tests | [#10](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/10) |
| `REQ-SAFE-001` | Fail safely when required environmental data is unavailable | Safety | Orchestrator failure-path tests | [#11](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/11) |
| `REQ-OPS-001` | Run scheduled environmental control locally | Operations | Docker runtime and systemd units | [#12](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/12) |
| `REQ-QA-001` | Provide guarded hardware and end-to-end smoke tests | QA | Read-only and explicit opt-in scripts | [#13](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/13) |
| `NFR-QA-001` | Enforce the automated quality gate | QA | GitHub Actions, branch coverage threshold | [#14](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/14) |

## Delivered through pull request #37

These requirements are implemented and delivered to the default branch by [pull request #37](https://github.com/lucasbezerranegot/smart-home-qa-harness/pull/37).

| ID | Requirement | Evidence summary | Existing commits | GitHub Issue |
|---|---|---|---|---|
| `REQ-HEAT-001` | Control heating with temperature hysteresis | Heating engine and BDD scenarios | `b29e719`, `69bff46` | [#15](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/15) |
| `REQ-HEAT-002` | Associate every heating zone with its own Meter and relay channel | Configuration and association tests | `7d83e1e`, `2c6ba7b` | [#16](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/16) |
| `REQ-HEAT-003` | Turn heating off for unavailable or unsafe Meter readings | Safe decision paths and adapter tests | `b29e719`, `2c6ba7b` | [#17](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/17) |
| `REQ-HEAT-004` | Apply and confirm SwitchBot relay channel commands | Relay adapter and orchestration tests | `5452e79`, `c1c1676` | [#18](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/18) |
| `REQ-HEAT-005` | Configure up to six independent heating zones | Application configuration tests | `322884b` | [#19](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/19) |
| `REQ-HEAT-006` | Protect manual real-heating commands | Dry-run and explicit authorization controls | `322884b` | [#20](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/20) |
| `REQ-HEAT-007` | Run a guarded scheduled children-room heating pilot | Scheduled runner, timer, and tests | `d468706` | [#21](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/21) |

## In progress on `codex/refactor-room-ventilation`

These requirements describe the current uncommitted branch work observed on 2026-09-26.

| ID | Requirement | Evidence summary | GitHub Issue |
|---|---|---|---|
| `REQ-ROOM-001` | Maintain a validated shared room and device registry | `room_config.py` and tests | [#22](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/22) |
| `REQ-VNT-005` | Evaluate and aggregate ventilation recommendations by room | Room-aware engine, aggregation, and tests | [#23](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/23) |
| `REQ-HUM-001` | Control humidifiers using schedule and humidity hysteresis | Humidifier engine and boundary tests | [#24](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/24) |
| `REQ-HUM-002` | Apply and confirm SwitchBot Plug Mini humidifier commands | Plug adapter and controller tests | [#25](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/25) |
| `REQ-ROOM-002` | Run one fault-isolated room-control cycle | Shared Meter reads, partial failures, combined result | [#26](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/26) |

## Planned

| ID | Requirement | Area | Source | GitHub Issue |
|---|---|---|---|---|
| `REQ-VNT-006` | Compare indoor and outdoor moisture before recommending humidity ventilation | Ventilation | README roadmap | [#27](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/27) |
| `REQ-VNT-007` | Remind residents to close windows after short ventilation | Ventilation | README roadmap | [#28](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/28) |
| `REQ-HEAT-008` | Apply a scheduled bathroom comfort-heating profile | Heating | Product idea | [#29](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/29) |
| `REQ-HEAT-009` | Apply configurable nighttime bedroom temperature profiles | Heating | Product idea | [#30](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/30) |
| `REQ-HEAT-010` | Integrate installed SwitchBot radiator thermostats | Heating | README roadmap | [#31](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/31) |
| `REQ-HUM-003` | Detect probable low water from calibrated humidifier power | Humidifier | Branch roadmap | [#32](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/32) |
| `REQ-NTF-003` | Announce the affected room names dynamically | Notifications | Branch roadmap | [#33](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/33) |
| `REQ-NTF-004` | Recover safely from failed notification delivery | Notifications | README roadmap | [#34](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/34) |
| `REQ-STATE-001` | Improve state retention and concurrent access safety | State | README roadmap | [#35](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/35) |
| `REQ-OBS-001` | Provide structured operational logging and monitoring | Observability | README roadmap | [#36](https://github.com/lucasbezerranegot/smart-home-qa-harness/issues/36) |
