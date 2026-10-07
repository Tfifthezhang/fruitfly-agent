"""Frontend-neutral configuration controller substitutes."""

from dataclasses import replace

from fruitfly_agent.interactive.configuration import (
    ConfigurationActionResult, ConfigurationMechanism, ConfigurationParameter,
    ConfigurationSelectionGroup, ConfigurationSnapshot,
)


class MockConfiguration:
    def __init__(self, *, model=None) -> None:
        self.model = model
        self.saved = False
        self.changed = False
        self.enabled = False
        self.parameter = True

    def snapshot(self):
        return ConfigurationSnapshot(
            "/workspace/fruitfly.yaml",
            "default",
            ("default",),
            "models.yaml",
            self.model,
            ("offline",),
            (
                ConfigurationMechanism(
                    "custom",
                    "custom",
                    "Injected mechanism",
                    "Provided entirely by the configuration snapshot.",
                    self.enabled,
                    "new_session",
                    parameters=(
                        ConfigurationParameter(
                            "feature",
                            "Feature",
                            "Toggle the injected feature.",
                            "boolean",
                            self.parameter,
                        ),
                    ),
                ),
            ),
            ready=self.model is not None,
            changed=self.changed,
        )

    def select_profile(self, profile_id):
        self.changed = True
        return ConfigurationActionResult("selected", changed=True)

    def select_model_catalog(self, path):
        self.changed = True
        return ConfigurationActionResult("catalog", changed=True)

    def select_model(self, model_profile):
        self.model = model_profile
        self.changed = True
        return ConfigurationActionResult("model", changed=True)

    def set_mechanism(self, mechanism_id, *, enabled):
        self.enabled = enabled
        self.changed = True
        return ConfigurationActionResult("mechanism", changed=True)

    def set_parameter(self, mechanism_id, name, value):
        self.parameter = value == "true"
        self.changed = True
        return ConfigurationActionResult("parameter", changed=True)

    def save(self):
        self.saved = True
        self.changed = False
        return ConfigurationActionResult("saved", saved=True)

    def reset(self):
        self.changed = False
        self.enabled = False
        return ConfigurationActionResult("reset")



class AlgorithmConfiguration(MockConfiguration):
    def __init__(self) -> None:
        super().__init__(model="offline")
        self.enabled = True
        self.algorithm = "variant-b"

    def snapshot(self):
        snapshot = super().snapshot()
        options = ("variant-a", "variant-b", "variant-c")
        return replace(snapshot,
            mechanisms=tuple(ConfigurationMechanism(
                option, "compaction", option, "Detailed algorithm tuning.",
                self.enabled and self.algorithm == option, "new_session",
                parameters=(ConfigurationParameter("max_tokens", "Maximum tokens", "Hidden tuning", "integer", 1000),),
                selection_group="reduction",
            ) for option in options),
            selection_groups=(ConfigurationSelectionGroup(
                "reduction", "Reduction", "compaction", "reduction", options,
                self.algorithm if self.enabled else None,
            ),),
        )

    def select_algorithm(self, group_id, option_id):
        assert group_id == "reduction"
        if option_id is not None:
            self.algorithm = option_id
        self.enabled = option_id is not None
        self.changed = True
        return ConfigurationActionResult("algorithm", changed=True)

