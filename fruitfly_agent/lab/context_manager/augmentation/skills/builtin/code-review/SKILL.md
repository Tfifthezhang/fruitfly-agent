---
name: code-review
description: Use this skill when asked to review a patch, function, implementation, or recently completed complex change for correctness. Examine concrete failure paths and task requirements so findings are actionable rather than speculative style advice.
---

# Code review

[Up: Built-in coding Skills](../README.md)

## Overview

Examine the requested change for actionable correctness problems. Trace affected behavior, compare it with callers and requirements, and report supported findings with a concrete failure scenario. Prioritizing evidence keeps the review useful and within scope.

## Communicate with the user

Adapt explanations to the user's technical background and keep progress concise. In unattended tasks, use available evidence and task-consistent assumptions without introducing a mandatory interview or approval stage.

## Execute the workflow

Establish scope and intended behavior. Read implementation, callers and relevant tests. Examine input boundaries, state transitions, error handling and contract compatibility. For each finding, give its location, triggering state or input, incorrect behavior and evidence. Prefer reproducible failures and keep severity proportional to effect. Explain uncertainty where a concern is not established. Use available local files and tools without requiring a PR, Git history, second model or subagent. Report without changing files when only review was requested; apply fixes only when authorized. Avoid unrelated cleanup.

## Evaluate and improve

Check whether the workflow produced the requested behavior with proportionate effort. Separate observations from assumptions. Preserve useful evidence without creating unsolicited reports or plan files.

## Example

Input: review a cache lookup using truthiness.
Output: identify how a valid zero value is treated as missing and cite the lookup location.

## Advanced use

For a larger change, apply the same workflow to affected interfaces and state
transitions. Reuse existing evidence and scale checks to the task constraints.

## Platform adaptation

Use ordinary host file and command tools. Treat unavailable capabilities as limits, not instructions to change the environment. The host owns permissions, lifecycle and verification policy. This skill supplies no independent authority.

## Reference files

This procedure is self-contained. Read task-provided code and project guidance
when their details affect the requested work.
