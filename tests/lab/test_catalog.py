"""Generic Lab catalog, profile, and assembly contracts."""

from __future__ import annotations

from dataclasses import replace
import tempfile
import unittest
from pathlib import Path

from fruitfly_agent.core import AgentLoopConfig
from fruitfly_agent.lab import SummarizingCompactor, SummarizingCompactorConfig
from fruitfly_agent.lab.catalog import (
    AssemblyContext,
    AssemblyState,
    LabCatalog,
    MechanismContribution,
    MechanismDefinition,
    MechanismDescriptor,
    MechanismEffects,
    MechanismSelection,
    ParameterDescriptor,
    ProviderBinding,
    assemble_lab,
    builtin_catalog,
)
from tests.support.faux_provider import FauxProvider


def _definition(
    mechanism_id: str,
    *,
    order: int = 100,
    requires: frozenset[str] = frozenset(),
    conflicts: frozenset[str] = frozenset(),
    group: str | None = None,
    phase: str | None = None,
    install=None,
) -> MechanismDefinition:
    return MechanismDefinition(
        MechanismDescriptor(
            mechanism_id=mechanism_id,
            label=mechanism_id,
            description="test mechanism",
            contributions=(
                MechanismContribution(
                    "online" if phase is not None else "capability",
                    "context" if phase is not None else "tools",
                    phase,
                ),
            ),
            parameters=(
                ParameterDescriptor(
                    "limit",
                    "integer",
                    "Limit",
                    "Positive test limit.",
                    2,
                    minimum=1,
                ),
            ),
            requires=requires,
            conflicts=conflicts,
            exclusive_group=group,
            install_order=order,
            effects=MechanismEffects(tools=(mechanism_id,)),
        ),
        install or (lambda state, context, parameters: state),
    )


class DescriptorTest(unittest.TestCase):
    def test_descriptor_serializes_multiple_contributions_without_a_version(self) -> None:
        descriptor = MechanismDescriptor(
            mechanism_id="programmatic-context",
            label="Programmatic context",
            description="External context plus a model-visible tool.",
            contributions=(
                MechanismContribution("online", "context", "externalization"),
                MechanismContribution("capability", "tools"),
            ),
            effects=MechanismEffects(tools=("ipython",)),
        )

        payload = descriptor.to_dict()

        self.assertNotIn("version", payload)
        self.assertNotIn("layer", payload)
        self.assertEqual(
            [
                {
                    "layer": "online",
                    "family": "context",
                    "context_phase": "externalization",
                },
                {
                    "layer": "capability",
                    "family": "tools",
                    "context_phase": None,
                },
            ],
            payload["contributions"],
        )

    def test_parameters_share_terminal_and_yaml_validation(self) -> None:
        integer = ParameterDescriptor(
            "count", "integer", "Count", "A bounded count.", 2, minimum=1, maximum=3
        )
        values = ParameterDescriptor(
            "tags", "string_list", "Tags", "Comma-separated tags.", ()
        )

        self.assertEqual(integer.parse("3"), 3)
        self.assertEqual(values.parse("one, two"), ("one", "two"))
        with self.assertRaisesRegex(ValueError, "at most"):
            integer.validate(4)

    def test_activation_scope_is_explicit_and_validated(self) -> None:
        for scope in ("live", "next_request", "new_session", "restart"):
            descriptor = MechanismDescriptor(
                mechanism_id=scope,
                label=scope,
                description="Supported activation scope.",
                contributions=(
                    MechanismContribution("online", "context", "augmentation"),
                ),
                activation=scope,  # type: ignore[arg-type]
            )
            self.assertEqual(descriptor.activation, scope)
        with self.assertRaisesRegex(ValueError, "unsupported activation scope"):
            MechanismDescriptor(
                mechanism_id="hot",
                label="Hot",
                description="Invalid hot mechanism.",
                contributions=(
                    MechanismContribution("online", "context", "augmentation"),
                ),
                activation="hot",  # type: ignore[arg-type]
            )

    def test_context_phase_is_restricted_to_online_context(self) -> None:
        with self.assertRaisesRegex(ValueError, "online/context"):
            MechanismContribution("capability", "tools", "externalization")
        with self.assertRaisesRegex(ValueError, "required exactly"):
            MechanismContribution("online", "context")


class CatalogTest(unittest.TestCase):
    def test_unknown_mechanisms_have_actionable_configuration_errors(self) -> None:
        catalog = builtin_catalog()

        for mechanism in ("unregistered-recorder", "unregistered-observer"):
            with self.subTest(mechanism=mechanism):
                with self.assertRaises(ValueError) as failure:
                    catalog.get(mechanism)
                message = str(failure.exception)
                self.assertIn(f"unknown mechanism {mechanism!r}", message)
                self.assertIn("available:", message)
                for descriptor in catalog.descriptors():
                    self.assertIn(descriptor.mechanism_id, message)
                self.assertIn("Remove this selection or register", message)

    def test_empty_catalog_rejects_unknown_mechanisms_with_registration_entry(self) -> None:
        with self.assertRaises(ValueError) as failure:
            LabCatalog(()).get("unregistered-mechanism")
        message = str(failure.exception)
        self.assertIn("available: none", message)
        self.assertIn("register the mechanism in the Catalog", message)

    def test_builtin_descriptors_use_two_dimensional_architecture(self) -> None:
        catalog = builtin_catalog()
        expected = {
            "read-tool": ("capability", "tools", None, "tools"),
            "ipython-tool": ("capability", "tools", None, "tools"),
            "skill-catalog": (
                "online",
                "context",
                "augmentation",
                "context-manager",
            ),
            "rlm-ipython": (
                "online",
                "context",
                "externalization",
                "context-manager",
            ),
            "compaction": (
                "online",
                "context",
                "reduction",
                "context-manager",
            ),
        }
        for mechanism_id, coordinates in expected.items():
            descriptor = catalog.get(mechanism_id).descriptor
            primary = descriptor.primary
            self.assertEqual(
                coordinates[:3],
                (
                    primary.layer,
                    primary.family,
                    primary.context_phase,
                ),
            )

    def test_builtin_catalog_covers_every_current_selectable_harness_feature(self) -> None:
        self.assertEqual(
            {item.mechanism_id for item in builtin_catalog().descriptors()},
            {
                "local-env",
                "read-tool",
                "bash-tool",
                "edit-tool",
                "write-tool",
                "ipython-tool",
                "skill-catalog",
                "information-context",
                "memory-files",
                "knowledge-files",
                "live-http",
                "compaction",
                "rlm-ipython",
                "opro",
            },
        )

    def test_unknown_mechanisms_are_rejected_even_when_disabled(self) -> None:
        catalog = builtin_catalog()
        for mechanism in ("unregistered-optimizer", "unregistered-context", "unregistered-tool"):
            for enabled in (True, False):
                with self.subTest(mechanism=mechanism, enabled=enabled):
                    with self.assertRaisesRegex(ValueError, "unknown mechanism.*Remove this selection"):
                        catalog.resolve((MechanismSelection(mechanism, enabled=enabled),))

    def test_native_optimizers_use_algorithm_neutral_task_path(self) -> None:
        catalog = builtin_catalog()
        for mechanism in ("opro",):
            with self.subTest(mechanism=mechanism):
                definition = catalog.get(mechanism)
                self.assertFalse(definition.descriptor.default_enabled)
                parameters = {item.name: item.default for item in definition.descriptor.parameters}
                self.assertEqual(parameters["cases_path"], ".fruitfly/optimization/cases.json")
                self.assertFalse(any("reflection" in name for name in parameters))

    def test_ipython_and_rlm_descriptors_have_separate_effects(self) -> None:
        catalog = builtin_catalog()
        descriptor = catalog.get("rlm-ipython").descriptor
        tool = catalog.get("ipython-tool").descriptor

        self.assertEqual(
            ("online", "context", "externalization"),
            (
                descriptor.primary.layer,
                descriptor.primary.family,
                descriptor.primary.context_phase,
            ),
        )
        self.assertFalse(descriptor.default_enabled)
        self.assertEqual(frozenset({"ipython-tool"}), descriptor.requires)
        self.assertEqual((), descriptor.effects.tools)
        self.assertFalse(descriptor.effects.uses_provider)
        self.assertFalse(descriptor.effects.uses_network)
        self.assertTrue(descriptor.effects.writes_files)
        self.assertEqual(("ipython",), tool.effects.tools)
        self.assertTrue(tool.effects.uses_provider)
        self.assertTrue(tool.effects.uses_network)
        self.assertIn(
            "max_query_calls",
            {parameter.name for parameter in tool.parameters},
        )

    def test_compaction_descriptor_owns_config_and_costs(self) -> None:
        definition = builtin_catalog().get("compaction")
        descriptor = definition.descriptor
        self.assertEqual("reduction", descriptor.primary.context_phase)
        self.assertNotIn("profile", {p.name for p in descriptor.parameters})
        self.assertTrue(descriptor.effects.uses_provider)
        self.assertTrue(descriptor.effects.uses_network)
        self.assertEqual("summarizing-v2", definition.implementation_id)

    def test_compaction_rejects_profile_parameter_even_when_disabled(self):
        for name in ("unregistered-profile", "summarizing"):
            for enabled in (True, False):
                with self.subTest(name=name, enabled=enabled):
                    with self.assertRaisesRegex(ValueError, "profile is unsupported; remove profile"):
                        builtin_catalog().resolve((MechanismSelection(
                            "compaction", enabled=enabled, parameters={"profile": name}
                        ),))

    def test_rejects_duplicates_dependencies_conflicts_and_exclusive_groups(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate mechanism"):
            LabCatalog((_definition("same"), _definition("same")))

        catalog = LabCatalog(
            (
                _definition("base"),
                _definition("dependent", requires=frozenset({"base"})),
                _definition("other", conflicts=frozenset({"base"})),
                _definition("left", group="slot"),
                _definition("right", group="slot"),
            )
        )
        with self.assertRaisesRegex(ValueError, "requires"):
            catalog.resolve((MechanismSelection("dependent"),))
        with self.assertRaisesRegex(ValueError, "conflicts"):
            catalog.resolve(
                (MechanismSelection("base"), MechanismSelection("other"))
            )
        with self.assertRaisesRegex(ValueError, "exclusive"):
            catalog.resolve(
                (MechanismSelection("left"), MechanismSelection("right"))
            )

        phase_catalog = LabCatalog(
            (
                _definition("external-a", phase="externalization"),
                _definition("external-b", phase="externalization"),
            )
        )
        resolved = phase_catalog.resolve(
            (
                MechanismSelection("external-a"),
                MechanismSelection("external-b"),
            )
        )
        self.assertEqual(
            ("external-a", "external-b"),
            tuple(item.definition.descriptor.mechanism_id for item in resolved),
        )

    def test_explicit_extension_is_immutable_and_discoverable(self) -> None:
        base = builtin_catalog()
        custom = _definition("external-knowledge")
        extended = base.extended((custom,))

        self.assertNotIn(
            "external-knowledge",
            {item.mechanism_id for item in base.descriptors()},
        )
        self.assertIn(
            "external-knowledge",
            {item.mechanism_id for item in extended.descriptors()},
        )

    def test_each_compaction_choice_assembles_with_only_required_provider(self) -> None:
        catalog = builtin_catalog()
        for algorithm, expected_provider_calls in (("summarizing", 1),):
            with self.subTest(algorithm=algorithm), tempfile.TemporaryDirectory() as tmp:
                calls: list[tuple[str | None, int | None]] = []

                def resolve(profile, max_tokens):
                    calls.append((profile, max_tokens))
                    return ProviderBinding(FauxProvider(), "summary-model", "summary")

                result = assemble_lab(
                    AgentLoopConfig(provider=FauxProvider()),
                    catalog=catalog,
                    selections=(
                        MechanismSelection(
                            "compaction",
                            parameters={},
                        ),
                    ),
                    context=AssemblyContext(
                        Path(tmp),
                        object(),
                        "main-model",
                        resolve,
                    ),
                )

                self.assertIsNotNone(result.context_pipeline)
                self.assertEqual(("compaction",), result.mechanism_ids)
                self.assertEqual(expected_provider_calls, len(calls))

    def test_assembly_is_stable_and_rejects_non_state_installers(self) -> None:
        observed: list[str] = []

        def installer(name):
            def install(state, context, parameters):
                observed.append(name)
                return state.with_component(name, parameters["limit"])

            return install

        catalog = LabCatalog(
            (
                _definition("later", order=20, install=installer("later")),
                _definition("first", order=10, install=installer("first")),
            )
        )
        context = AssemblyContext(
            Path.cwd(),
            object(),  # installers in this test do not consume SessionLike
            "offline",
            lambda *_: ProviderBinding(FauxProvider(), "offline", "offline"),
        )
        result = assemble_lab(
            AgentLoopConfig(provider=FauxProvider()),
            catalog=catalog,
            selections=(MechanismSelection("later"), MechanismSelection("first")),
            context=context,
        )

        self.assertEqual(observed, ["first", "later"])
        self.assertEqual(result.mechanism_ids, ("first", "later"))
        self.assertEqual(result.components, {"first": 2, "later": 2})

        invalid = LabCatalog((_definition("invalid", install=lambda *args: None),))
        with self.assertRaisesRegex(TypeError, "expected AssemblyState"):
            assemble_lab(
                AgentLoopConfig(provider=FauxProvider()),
                catalog=invalid,
                selections=(MechanismSelection("invalid"),),
                context=context,
            )

    def test_assembly_binds_reduction_to_its_declaring_mechanism(self) -> None:
        context = AssemblyContext(
            Path.cwd(),
            object(),
            "offline",
            lambda *_: ProviderBinding(FauxProvider(), "offline", "offline"),
        )

        def install_reduction(state, context, parameters):
            return replace(state, reducer=SummarizingCompactor(SummarizingCompactorConfig(), FauxProvider()))

        declared = LabCatalog(
            (
                _definition(
                    "custom-reduction",
                    phase="reduction",
                    install=install_reduction,
                ),
            )
        )
        result = assemble_lab(
            AgentLoopConfig(provider=FauxProvider()),
            catalog=declared,
            selections=(MechanismSelection("custom-reduction"),),
            context=context,
        )

        self.assertEqual(
            ("custom-reduction",),
            result.context_pipeline.profile.reduction,
        )

        undeclared = LabCatalog(
            (_definition("hidden-reduction", install=install_reduction),)
        )
        with self.assertRaisesRegex(ValueError, "undeclared reduction"):
            assemble_lab(
                AgentLoopConfig(provider=FauxProvider()),
                catalog=undeclared,
                selections=(MechanismSelection("hidden-reduction"),),
                context=context,
            )




if __name__ == "__main__":
    unittest.main()
