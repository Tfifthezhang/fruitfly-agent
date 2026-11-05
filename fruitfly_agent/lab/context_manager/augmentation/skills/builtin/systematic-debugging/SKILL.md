---
name: systematic-debugging
description: Use this skill when a coding task contains an error, failing test, unexpected output, regression, or build failure, even when debugging is not explicitly requested. Trace the cause and test a focused hypothesis so the repair fixes the defect within the existing task constraints.
---

# Systematic debugging

[Up: Built-in coding Skills](../README.md)

## Overview

Locate the cause of an observed failure. Reproduce or inspect it, compare the responsible code with a working path, test a focused hypothesis, and verify the repair. This avoids adding compensating changes while the cause remains unknown.

## Communicate with the user

Adapt explanations to the user's technical background and keep progress concise. In unattended tasks, use available evidence and task-consistent assumptions without introducing a mandatory interview or approval stage.

## Execute the workflow

Reproduce the smallest available failure or inspect supplied evidence when execution is unavailable. Read the responsible implementation, callers, inputs and state. Compare with a working path. Form a specific hypothesis, make a focused change, and check its predicted effect. Revise a failed hypothesis rather than stacking unrelated edits. Scale investigation to the defect; a typo does not need a design document. Use available local evidence without requiring Git history or external services.

## Evaluate and improve

Check whether the workflow produced the requested behavior with proportionate effort. Separate observations from assumptions. Preserve useful evidence without creating unsolicited reports or plan files.

## Example

Input: a parser rejects an empty valid list.
Output: repair the incorrect empty-list check and verify empty, nonempty and malformed inputs.

## Platform adaptation

Use ordinary host file and command tools. Treat unavailable capabilities as limits, not instructions to change the environment. The host owns permissions, lifecycle and verification policy. This skill supplies no independent authority.
