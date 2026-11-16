# Share durable working files

[Up: Agents](../README.md)

The `work-products` H component supplies attributed working files for coding,
analysis and investigation. It uses a host-provided store and makes no model
requests. Enable it through ordinary component configuration; the installed
profile enables it. Child runtimes inherit its effective values with independent
writers. A restricted child can read its own products; its parent can inspect all
writers in that collaboration scope. Evidence grants remain separate.

| Tool | Behavior |
|---|---|
| `save_checkpoint` | Save text with an expected revision; zero creates a new name |
| `list_work_products` | Page identities, revisions and content hashes without bodies |
| `read_work_product` | Read an exact immutable revision in character pages |
| `patch_checkpoint` | Atomically repair JSON fields in an owned revision |

Publish progress after a bounded subproblem, before changing materials or
handing off work, and before context pressure. Include source references,
uncertainties and next actions. The parent reads relevant products rather than
repeatedly copying complete child output. A checkpoint is not task completion,
verification, or an original-reading receipt. Models choose and publish semantic
progress; the host does not invent a summary when the model has not written one.

Run stores content under its existing artifact store and atomic locators beside
the parent Session in `SESSION.jsonl.work/<producer>/<name>.json`. Each locator
references previous immutable revisions. Restricted research hosts share a
stage-scoped `roles/<role>/shared.work/` directory across format repairs. Publication checks concurrent changes and
rejects traversal and symlinks. Parent failure and resource retirement do not
delete products. Reopening a store validates referenced content before supplying
it. Persistence does not automatically replay work or authorize cross-run reuse.
The host scopes the store independently from the execution filesystem, including
when task tools operate over SSH.

Owner [defaults](methods/managed/defaults.yaml) declare tool instructions and
read/directory defaults and the context-pressure threshold. `improvement.py` admits instruction changes through the
ordinary parameter candidate path. Integrity, producer permissions, schemas and
revision checks are protected. The Python contracts bound text to 120000
characters and read pages to 24000. A pressure hook requests a checkpoint and
integration before further material expansion. Pressure uses the shared working
input budget, output reserve and measurement margin, even when the model window
is much larger. It does not invent task findings.
Read/list/patch schemas become visible after saved products exist, keeping an
empty runtime request compact. The Run store owns disk persistence; Lab owns
tool behavior. Selected restricted roles use the same installer as daily Agents.

A stage may additionally supply `submit_work_product`. It reads an exact saved
JSON revision and invokes the existing owner validator. Rejected submissions can
be repaired with `patch_checkpoint`; final authorization and citation checks
remain with the stage. No alternative final document grammar is introduced.

Offline checks: `tests.run.test_work_products` and
`tests.run.test_research_runtime`. Fake execution proves persistence, isolation
and configured behavior, not the correctness of generated findings.
