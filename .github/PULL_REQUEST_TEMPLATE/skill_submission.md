## Skill

Reference: `<author>/<slug>`
Version: `X.Y.Z`
Description:

| Action | Reference prompt | Parameters |
| --- | --- | --- |
| | | |

## Fingerprint and access

- OS, OS version, hardware:
- App package and supported app versions:
- `data_access`:
- Contains Python: yes / no
- Skill class: hard / soft
- Explicit checkpoints (if soft):

## Evidence

- Bench summary, if `bench.yaml` is included:
- Demo, if `demo.gif` is included:
- Analyzer findings and rationale:

## Checklist

- [ ] Files live in `skillhub/<my-github-login>/<slug>/` or I am a maintainer.
- [ ] `ghost skill validate <path>` and dry `ghost skill test <path>` pass.
- [ ] Existing skill version increased using SemVer.
- [ ] Actions declare ref_prompt, params, steps, end_state_validator and test_case.
- [ ] Python targets resolve and data_access accurately declares access.
- [ ] README.md and SOFT.md describe usage, fingerprint and checkpoints.
- [ ] No private handles, credentials or personal contacts are included.
- [ ] Optional bench numbers come from real runs.
