"""Catalog behavior and failure contracts."""
from __future__ import annotations
from dataclasses import replace
import unittest
from fruitfly_agent.lab.catalog import LabCatalog, MechanismContribution, MechanismDescriptor, MechanismEffects, MechanismSelection, ParameterDescriptor, builtin_catalog

from tests.support.catalog import mechanism_definition


class DescriptorTest(unittest.TestCase):
    def test_registration_rejects_invalid_installer_contract_before_discovery(self):
        async def asynchronous(state, context, parameters):
            return state
        for install, message in ((asynchronous, 'synchronous'),
                (lambda state: state, 'accept'),
                (lambda state, context, parameters, required: state, 'accept')):
            with self.subTest(install=install), self.assertRaisesRegex(TypeError, message):
                mechanism_definition('invalid-installer', install=install)

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
    def test_dynamic_setup_credentials_validate_declarations(self):
        from fruitfly_agent.lab.catalog.models import SetupCredential
        definition = builtin_catalog().get('web-search-tool')
        for fields in ([SetupCredential('api_key_env', 'Key', 'Hidden')],
                       (SetupCredential('unknown', 'Key', 'Hidden'),),
                       (SetupCredential('backend', 'Key', 'Hidden'),),
                       (SetupCredential('api_key_env', 'Key', 'Hidden', variable='invalid variable'),),
                       (SetupCredential('api_key_env', 'Key', 'Hidden'),) * 2):
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, 'setup credentials'):
                invalid = replace(definition, setup=replace(definition.setup, credential_resolver=lambda parameters: fields))
                invalid.setup_credentials({'backend': 'deepseek', 'api_key_env': ''})
        with self.assertRaisesRegex(TypeError, 'credential_resolver'):
            replace(definition, setup=replace(definition.setup, credential_resolver='invalid'))

    def test_credential_declarations_are_offline_normalized_and_enabled_only(self):
        calls = []
        def credentials(parameters):
            calls.append(parameters["limit"])
            return ("SHARED_KEY", "CUSTOM_KEY", "SHARED_KEY")
        definition = replace(mechanism_definition("custom"), credential_variables=credentials,
                             install=lambda *args: self.fail("discovery constructed a runtime"))
        catalog = LabCatalog((definition,))
        self.assertEqual(("CUSTOM_KEY", "SHARED_KEY"), catalog.required_credentials((MechanismSelection("custom"),)))
        self.assertEqual([2], calls)
        self.assertEqual((), catalog.required_credentials((MechanismSelection("custom", enabled=False),)))
        self.assertEqual([2], calls)
        for result in ("CUSTOM_KEY", ("a key value",), (123,)):
            invalid = replace(definition, credential_variables=lambda parameters: result)
            with self.subTest(result=result), self.assertRaisesRegex(ValueError, "environment variable"):
                invalid.required_credentials({})

    def test_registration_rejects_missing_display_metadata_and_unknown_user_fields(self):
        definition = builtin_catalog().get('read-tool')
        for changes in ({'implementation_path': ''}, {'documentation_path': ''},
                        {'implementation_path': '../missing.py'}, {'implementation_path': 'bad\npath.py'},
                        {'input_parameters': ('unknown',)}, {'input_parameters': 'unknown'},
                        {'descriptor': replace(definition.descriptor, description='line\nbreak')}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(definition, **changes)
        with self.assertRaises(ValueError):
            replace(definition, descriptor=replace(definition.descriptor, description=' '))

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

    def test_unknown_mechanisms_are_rejected_even_when_disabled(self) -> None:
        catalog = builtin_catalog()
        for mechanism in ("unregistered-improver", "unregistered-context", "unregistered-tool", "task-material-recording"):
            for enabled in (True, False):
                with self.subTest(mechanism=mechanism, enabled=enabled):
                    with self.assertRaisesRegex(ValueError, "unknown mechanism.*Remove this selection"):
                        catalog.resolve((MechanismSelection(mechanism, enabled=enabled),))

    def test_rejects_duplicates_dependencies_conflicts_and_exclusive_groups(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate mechanism"):
            LabCatalog((mechanism_definition("same"), mechanism_definition("same")))

        catalog = LabCatalog(
            (
                mechanism_definition("base"),
                mechanism_definition("dependent", requires=frozenset({"base"})),
                mechanism_definition("other", conflicts=frozenset({"base"})),
                mechanism_definition("left", group="slot"),
                mechanism_definition("right", group="slot"),
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
                mechanism_definition("external-a", phase="externalization"),
                mechanism_definition("external-b", phase="externalization"),
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
        custom = mechanism_definition("external-knowledge")
        extended = base.extended((custom,))

        self.assertNotIn(
            "external-knowledge",
            {item.mechanism_id for item in base.descriptors()},
        )
        self.assertIn(
            "external-knowledge",
            {item.mechanism_id for item in extended.descriptors()},
        )
