"""JSON-schema validation + coercion table. Never raises."""

import unittest

from fruitfly_agent.core.tool_runtime.schema import validate_tool_arguments

SCHEMA = {
    "type": "object",
    "properties": {
        "command": {"type": "string"},
        "timeout": {"type": "number", "minimum": 0.1},
        "retries": {"type": "integer"},
        "verbose": {"type": "boolean"},
        "targets": {"type": "array", "items": {"type": "string"}},
        "nested": {
            "type": "object",
            "properties": {"mode": {"type": "string", "enum": ["fast", "slow"]}},
            "required": ["mode"],
        },
    },
    "required": ["command"],
    "additionalProperties": False,
}


class TestValidate(unittest.TestCase):
    def ok(self, args):
        result = validate_tool_arguments(SCHEMA, args)
        self.assertTrue(result.is_ok, result.error)
        return result.unwrap()

    def err(self, args):
        result = validate_tool_arguments(SCHEMA, args)
        self.assertFalse(result.is_ok)
        return result.error

    def test_passthrough(self):
        out = self.ok({"command": "ls"})
        self.assertEqual(out, {"command": "ls"})

    def test_coercions(self):
        out = self.ok({"command": "ls", "timeout": "5", "retries": "3", "verbose": "true"})
        self.assertEqual(out["timeout"], 5.0)
        self.assertEqual(out["retries"], 3)
        self.assertTrue(out["verbose"])

    def test_integer_rejects_fraction(self):
        self.err({"command": "ls", "retries": 2.5})

    def test_enum(self):
        self.ok({"command": "ls", "nested": {"mode": "fast"}})
        self.err({"command": "ls", "nested": {"mode": "turbo"}})

    def test_missing_required(self):
        self.err({})
        self.err({"timeout": 1})
        # nested required
        self.err({"command": "ls", "nested": {}})

    def test_additional_properties(self):
        self.err({"command": "ls", "sneaky": 1})

    def test_array_items_coerced(self):
        out = self.ok({"command": "ls", "targets": [1, "a"]})
        self.assertEqual(out["targets"], ["1", "a"])

    def test_minimum(self):
        self.err({"command": "ls", "timeout": 0.05})

    def test_non_dict_args(self):
        result = validate_tool_arguments(SCHEMA, ["ls"])
        self.assertFalse(result.is_ok)

    def test_unsupported_keyword(self):
        result = validate_tool_arguments(
            {"type": "object", "properties": {}, "oneOf": []}, {}
        )
        self.assertFalse(result.is_ok)
        self.assertIn("oneOf", result.error)

    def test_none_optional_dropped(self):
        out = self.ok({"command": "ls", "timeout": None})
        self.assertNotIn("timeout", out)


if __name__ == "__main__":
    unittest.main()
