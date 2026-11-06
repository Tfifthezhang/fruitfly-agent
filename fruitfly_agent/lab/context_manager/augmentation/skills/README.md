# Use retained Skills

[Up: Augmentation](../README.md)

Skills are reusable task procedures, not Python plugins. Names, descriptions and
scoped resource locations enter the catalog. Bodies and text references load only
when the model reads them through the ordinary read tool. Visibility does not
prove invocation or task success.

## Enable and inspect

Enable H `skills` and the read tool. Skills are enabled by default. The menu offers
one Skills switch; S `skill-library` is attached retained content, without a separate
mechanism switch. Packaged
[Built-in coding Skills](builtin/README.md) are available without a checkout or a
workspace `.skills` directory. The catalog's `settings.root` selects additional
workspace Skills. A duplicate identity across sources fails instead of silently
shadowing a procedure. Source files are never overwritten.

`/skills` lists every active Skill name and description. `/skills read ID` displays one entry.
Runtime contents stay frozen until checked replacement or a new session.

| Skill | Scope |
|---|---|
| systematic-debugging | Investigate reproducible errors and repair causes |
| regression-testing | Derive focused checks from required public behavior |
| verification-before-completion | Support completion claims with relevant evidence |
| code-review | Find actionable correctness issues in the requested scope |

Descriptions use imperative triggers, concrete situations and reasons for using the
procedure. Bodies explain the workflow, communication, evaluation and platform
limits with examples. They do not introduce interviews, approval gates, commits,
mandatory agents or an independent optimization loop. A supplied task's output,
tool and execution contracts remain authoritative.

## Add workspace content

```text
.skills/example/
├── SKILL.md
└── references/checklist.md
```

Use YAML frontmatter with `name` and `description`, followed by the procedure.
Relative text references resolve against the resource parent. Hidden files and
descendant symlinks are excluded. Discovery retains diagnostics and has bounded
entry, depth and byte scans. The effective library rejects unsupported identities,
missing required descriptions, conflicting entries, unsupported execution metadata
and invalid resources. Only `name`, `description` and boolean
`disable-model-invocation` frontmatter is admitted into the effective library.
`disable-model-invocation: true` hides the entry; no manual invocation bypass is
implemented. Naming a skill in ordinary task text can guide model selection.

## Improve descriptions and bodies

`skill-library` is one S owner with independently identified entries. Its
`parameters.content.documents` stores canonical JSON text. Authorized changes may
edit descriptions, bodies and bounded text references while preserving identities,
source attribution and visibility policy. The H catalog separately exposes
`instructions.usage` and `settings.max_chars` (16000). Source root and provenance
remain protected from candidate grants.

Candidates use shared configuration materialization. The installed candidate
regenerates both the directory and resource bodies, so a description edit changes
what the model sees and a body edit changes what read returns. The complete bodies
are not injected to simulate successful invocation. Frozen text resources participate
in S snapshots and export; linked executable programs are not frozen or executed.

When metadata exceeds the H projection budget, the prompt retains a complete
`INDEX.md` resource pointer. Reading it discovers every visible Skill without
injecting procedure bodies. An insufficient budget for that pointer fails
configuration instead of making installed content unreachable.

## Extend installation

[packages.py](packages.py) defines `SkillPackage` and `SkillPackageSource`.
[installation.py](installation.py) validates and prepares a package without network
or activation. External installers can implement that source seam later.
Identity, origin, revision, content hash, license and text references travel with
the package. The source interface reserves dependency declarations; nonempty
dependencies fail admission until an adapter can validate and supply them. Download adapters and executable/binary package support are not
implemented. The host owns approval and activation; package text grants no tools.

## Files and offline checks

| File | Responsibility |
|---|---|
| [Methods](methods/README.md) | Parsing, H defaults and progressive projection |
| [library.py](library.py), [resources.py](resources.py) | S content and frozen read resources |
| [registration.py](registration.py), [improvement.py](improvement.py) | Owner mechanism and target declarations |
| [skill-library.yaml](skill-library.yaml) | Initial retained content |

```bash
.venv/bin/python -m unittest tests.lab.test_skill_catalog tests.lab.test_retained_targets tests.lab.test_skill_packages
```

No model requests occur during discovery, installation preparation or assembly.
Offline tests cover projection and isolation, not model gains or benchmark scores.

Collections also respect the editable component file budget: their YAML content
encoding is bounded to 118000 characters, reserving owner metadata within the
120000-character component limit. Oversized collections fail admission; retained
entries are not silently truncated.
