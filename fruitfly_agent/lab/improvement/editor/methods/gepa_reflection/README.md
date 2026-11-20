# Use GEPA for one reflective proposal

[Up: Editor](../../README.md)

Select `parameters.settings.method: gepa-reflection` in the referenced
`improvement-editor` component. Install the optional `gepa` extra, which pins
`gepa==0.1.4`. The workspace editor remains the default method.

This adaptation uses the instruction renderer and output extractor from
[GEPA 0.1.4](https://pypi.org/project/gepa/0.1.4/). It uses the reflective
mutation idea from the [GEPA paper](https://arxiv.org/abs/2507.19457), with
FruitFlyAgent's own batch, Provider and candidate submission. It proposes one
replacement for an explicitly granted `base_prompt.parameters.instructions.system`
field. Task execution, evolutionary search and candidate evaluation are
independent operations.

Supply the same frozen group batch and its Organizer bundle. The reflection
packet must account for every group member and retained execution. The adapter
maps task instructions, execution receipts, indexed action metadata, final
output and feedback into the GEPA example structure without fetching
outside the batch. The rendered input, parsed draft and raw responses are
retained as research artifacts. Research CLI invocations also retain the
tool-free editor transcript through the shared Session storage.

The editor makes one tool-free proposal completion. A changed draft receives
one tool-free attribution completion before normal candidate validation.
Both calls use `models.roles.editor`. The editor checks input space after
rendering and reserves output tokens. Missing, inconsistent or oversized
packets fail explicitly. Offline checks use `tests.lab.test_gepa_reflection`.
