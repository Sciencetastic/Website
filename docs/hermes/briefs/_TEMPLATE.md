# Brief T-### for <coder | auditor | designer>

Copy this file to `T-###-<role>.md` and fill it in. Keep it short and self-contained. The agent
reading it knows nothing about the project or earlier steps.

## Job
(implement, verify a fix, audit, fix a bug, or review visuals)

## Goal
(what should be true when this is done)

## Context
(only the facts needed; paths to earlier reports, such as `docs/hermes/reports/T-###-coder.md`)

## Files to touch
- `path/to/file`

## Acceptance criteria
- (each one checkable by a script or a specific command)

## Commands to run
- `hermes\run_gates.bat`

## Out of scope
- (what not to change)

## Report
Write your report to `docs/hermes/reports/T-###-<role>.md`, including the raw command output.
Reply with at most 5 lines: PASS or FAIL, a one-line summary, and the report path.
