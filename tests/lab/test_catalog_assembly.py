"""Catalog assembly behavior and failure contracts."""
from __future__ import annotations
from dataclasses import replace
import tempfile
import unittest
from pathlib import Path
from fruitfly_agent.core import AgentLoopConfig
from fruitfly_agent.lab import WorkingMemoryReducer, WorkingMemoryConfig
from fruitfly_agent.lab.catalog import AssemblyContext, LabCatalog, MechanismSelection, ProviderBinding, assemble_lab, builtin_catalog
from tests.support.faux_provider import FauxProvider

from tests.support.catalog import mechanism_definition


class DescriptorTest(unittest.TestCase):
    def test_assembly_rejects_broken_lifecycle_before_application_start(self):
        class Resource:
            start = 'invalid'
            def close(self):
                pass
        resource = Resource()
        owned = []
        definition = mechanism_definition('broken-lifecycle',
            install=lambda state, context, parameters: state.with_component('resource', resource))
        context = AssemblyContext(Path.cwd(), object(), 'offline',
            lambda *_: ProviderBinding(FauxProvider(), 'offline', 'offline'), resource_sink=owned)
        with self.assertRaisesRegex(TypeError, 'component start must be callable'):
            assemble_lab(AgentLoopConfig(provider=FauxProvider()), catalog=LabCatalog((definition,)),
                selections=(MechanismSelection('broken-lifecycle'),), context=context)
        self.assertIn(resource, owned)


class CatalogTest(unittest.TestCase):
    def test_assembly_checks_declared_credentials_before_install_and_injects_snapshot(self):
        lookups = []
        def resolve(name):
            lookups.append(name)
            return "fixture-value"
        def install(state, context, parameters):
            self.assertEqual("fixture-value", context.secret_resolver("CUSTOM_KEY"))
            self.assertIsNone(context.secret_resolver("UNDECLARED_KEY"))
            return state
        definition = replace(mechanism_definition("custom"), credential_variables=lambda parameters: ("CUSTOM_KEY",), install=install)
        catalog = LabCatalog((definition,))
        context = AssemblyContext(Path.cwd(), object(), "offline", lambda *args: None, secret_resolver=resolve)
        assemble_lab(AgentLoopConfig(provider=FauxProvider()), catalog=catalog,
                     selections=(MechanismSelection("custom"),), context=context)
        self.assertEqual(["CUSTOM_KEY"], lookups)
        with self.assertRaisesRegex(ValueError, "CUSTOM_KEY"):
            assemble_lab(AgentLoopConfig(provider=FauxProvider()), catalog=catalog,
                         selections=(MechanismSelection("custom"),), context=replace(context, secret_resolver=None))

    def test_each_compaction_choice_assembles_with_only_required_provider(self) -> None:
        catalog = builtin_catalog()
        for algorithm, expected_provider_calls in (("working memory", 1),):
            with self.subTest(algorithm=algorithm), tempfile.TemporaryDirectory() as tmp:
                calls: list[tuple[str | None, int | None]] = []

                def resolve(profile, max_tokens):
                    calls.append((profile, max_tokens))
                    return ProviderBinding(FauxProvider(), "summary-model", "summary")

                result = assemble_lab(
                    AgentLoopConfig(provider=FauxProvider()),
                    catalog=catalog,
                    selections=(
                        MechanismSelection("context-history"),
                        MechanismSelection(
                            "working-memory-reduction",
                            parameters={},
                        ),
                    ),
                    context=AssemblyContext(
                        Path(tmp),
                        None,
                        "main-model",
                        resolve,
                    ),
                )

                self.assertIsNotNone(result.context_pipeline)
                self.assertEqual(("context-history", "working-memory-reduction"), result.mechanism_ids)
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
                mechanism_definition("later", order=20, install=installer("later")),
                mechanism_definition("first", order=10, install=installer("first")),
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

        invalid = LabCatalog((mechanism_definition("invalid", install=lambda *args: None),))
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
            return replace(state, reducer=WorkingMemoryReducer(WorkingMemoryConfig(), FauxProvider()))

        declared = LabCatalog(
            (
                mechanism_definition(
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
            (mechanism_definition("hidden-reduction", install=install_reduction),)
        )
        with self.assertRaisesRegex(ValueError, "undeclared reduction"):
            assemble_lab(
                AgentLoopConfig(provider=FauxProvider()),
                catalog=undeclared,
                selections=(MechanismSelection("hidden-reduction"),),
                context=context,
            )
