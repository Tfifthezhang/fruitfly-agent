---
name: verification-before-completion
description: Use this skill when preparing to report a coding task as fixed, complete, tested, or ready to use. Match each claim to relevant evidence so the result accurately describes what was checked and what remains unknown.
---

# Verify before completion

[Up: Built-in coding Skills](../README.md)

## Overview

Match each completion claim to current evidence. Choose the relevant check, inspect its result, and report its scope and limits. This lets the user rely on the result without inferring checks that never ran.

## Communicate with the user

Adapt explanations to the user's technical background and keep progress concise. In unattended tasks, use available evidence and task-consistent assumptions without introducing a mandatory interview or approval stage.

## Execute the workflow

Identify relevant checks: a focused regression, affected tests, a build, a command invocation or inspection of an artifact. Follow explicit task requirements and available capabilities. Check after the last relevant change; read output and exit status. Reuse still-valid evidence when no intervening change invalidates it. Broaden checks for failures, unresolved relevant concerns or project requirements, rather than on every reply. When execution is unavailable, report that limit and continue useful supported validation. Do not require installation, network, a browser, Git or new approvals. Preserve required final output, including code-only and machine-readable formats.

## Evaluate and improve

Check whether the workflow produced the requested behavior with proportionate effort. Separate observations from assumptions. Preserve useful evidence without creating unsolicited reports or plan files.

## Example

Input: a focused test passes but the full suite was not run.
Output: report the focused result without claiming the entire suite passed.

## Platform adaptation

Use ordinary host file and command tools. Treat unavailable capabilities as limits, not instructions to change the environment. The host owns permissions, lifecycle and verification policy. This skill supplies no independent authority.
