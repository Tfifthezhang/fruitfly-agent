---
name: regression-testing
description: Use this skill when repairing a defect, changing observable behavior, or handling a boundary condition in a coding task. Derive focused checks from the public contract so the repair preserves required behavior rather than merely satisfying a newly written test.
---

# Regression testing

[Up: Built-in coding Skills](../README.md)

## Overview

Translate a defect or changed requirement into observable checks. Reproduce the failure, test the intended contract and relevant boundaries, then verify the repair. A useful regression distinguishes correct behavior from the original defect.

## Communicate with the user

Adapt explanations to the user's technical background and keep progress concise. In unattended tasks, use available evidence and task-consistent assumptions without introducing a mandatory interview or approval stage.

## Execute the workflow

Identify an input that distinguishes the defect from intended behavior. Reuse existing test frameworks and support. Cover meaningful adjacent cases without mirroring private implementation. Confirm that a check fails for the intended reason when a before/after comparison is practical. Add tests where the task permits changes; use permitted temporary checks when tests are read-only. Keep supplied acceptance criteria authoritative. Do not modify protected tests, expected answers or evaluation machinery. New tests establish their covered behavior, not hidden-test success. Test-first development is optional and does not justify discarding valid implementation.

## Evaluate and improve

Check whether the workflow produced the requested behavior with proportionate effort. Separate observations from assumptions. Preserve useful evidence without creating unsolicited reports or plan files.

## Example

Input: fix division rounding for negative inputs.
Output: check negative fractional, positive, exact and zero cases against the specified rounding rule.

## Platform adaptation

Use ordinary host file and command tools. Treat unavailable capabilities as limits, not instructions to change the environment. The host owns permissions, lifecycle and verification policy. This skill supplies no independent authority.
