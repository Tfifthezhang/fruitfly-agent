"""Core tool-schema validation and primitive coercion.

Supported schema subset:
type (string/number/integer/boolean/array/object), enum, required, properties,
items, description, minimum/maximum, additionalProperties: false.

Never raises — every failure is a Result.failure with a message the model can
act on (the loop converts it into an error tool result).
"""

from __future__ import annotations

from typing import Any

from ..errors import Result

_UNSUPPORTED = ("$ref", "oneOf", "anyOf", "allOf", "not", "pattern", "patternProperties")


def validate_tool_arguments(schema: dict[str, Any], args: Any) -> Result[dict[str, Any]]:
    for keyword in _UNSUPPORTED:
        if keyword in schema:
            return Result.failure(f"unsupported schema keyword: {keyword}")
    if schema.get("type") != "object":
        return Result.failure(f"tool schema must be type object, got {schema.get('type')!r}")
    if not isinstance(args, dict):
        return Result.failure(f"tool arguments must be an object, got {type(args).__name__}")

    properties = schema.get("properties") or {}
    if not isinstance(properties, dict):
        return Result.failure("schema 'properties' must be an object")

    coerced: dict[str, Any] = {}
    for key, value in args.items():
        prop = properties.get(key)
        if prop is None:
            if schema.get("additionalProperties") is False:
                return Result.failure(
                    f"unexpected argument {key!r}; allowed: {', '.join(sorted(properties))}"
                )
            coerced[key] = value
            continue
        result = _coerce_value(prop, value, path=key)
        if not result.is_ok:
            return result
        coerced[key] = result.unwrap()

    required = schema.get("required") or []
    if isinstance(required, str):
        required = [required]
    for key in required:
        if key not in args:
            return Result.failure(f"missing required argument {key!r}")

    # Omit optional keys whose coerced value is None.
    coerced = {k: v for k, v in coerced.items() if v is not None}
    return Result.success(coerced)


def _coerce_value(schema: dict[str, Any], value: Any, path: str) -> Result[Any]:
    expected = schema.get("type")
    if expected is None:
        return Result.success(value)

    if value is None:
        return Result.success(None)

    if expected == "string":
        if isinstance(value, str):
            coerced = Result.success(value)
        elif isinstance(value, (int, float, bool)):
            coerced = Result.success(str(value))
        else:
            return Result.failure(f"{path}: expected string, got {type(value).__name__}")
    elif expected in ("number", "integer"):
        coerced = _coerce_number(value, path, integer=expected == "integer")
        if not coerced.is_ok:
            return coerced
        value = coerced.unwrap()
        if "minimum" in schema and value < schema["minimum"]:
            return Result.failure(f"{path}: value {value} is below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            return Result.failure(f"{path}: value {value} is above maximum {schema['maximum']}")
        coerced = Result.success(value)
    elif expected == "boolean":
        if isinstance(value, bool):
            coerced = Result.success(value)
        elif isinstance(value, str) and value.lower() in ("true", "false"):
            coerced = Result.success(value.lower() == "true")
        else:
            return Result.failure(f"{path}: expected boolean, got {type(value).__name__}")
    elif expected == "array":
        if not isinstance(value, list):
            return Result.failure(f"{path}: expected array, got {type(value).__name__}")
        items_schema = schema.get("items")
        out = []
        if isinstance(items_schema, dict):
            for i, item in enumerate(value):
                r = _coerce_value(items_schema, item, path=f"{path}[{i}]")
                if not r.is_ok:
                    return r
                out.append(r.unwrap())
        else:
            out = list(value)
        coerced = Result.success(out)
    elif expected == "object":
        if not isinstance(value, dict):
            return Result.failure(f"{path}: expected object, got {type(value).__name__}")
        nested_props = schema.get("properties") or {}
        out: dict[str, Any] = {}
        for k, v in value.items():
            prop = nested_props.get(k)
            if prop is None:
                if schema.get("additionalProperties") is False:
                    return Result.failure(
                        f"{path}.{k}: unexpected key; allowed: {', '.join(sorted(nested_props))}"
                    )
                out[k] = v
                continue
            r = _coerce_value(prop, v, path=f"{path}.{k}")
            if not r.is_ok:
                return r
            out[k] = r.unwrap()
        for k in schema.get("required") or []:
            if k not in value:
                return Result.failure(f"{path}.{k}: missing required key")
        coerced = Result.success(out)
    else:
        return Result.failure(f"unsupported schema type: {expected!r}")

    if not coerced.is_ok:
        return coerced
    final = coerced.unwrap()
    if final is not None and "enum" in schema:
        if final not in schema["enum"]:
            return Result.failure(
                f"{path}: value {final!r} not in allowed values {schema['enum']!r}"
            )
    return Result.success(final)


def _coerce_number(value: Any, path: str, *, integer: bool) -> Result[float | int]:
    if isinstance(value, bool):
        return Result.failure(f"{path}: expected number, got boolean")
    if isinstance(value, (int, float)):
        if integer:
            if float(value) != int(value):
                return Result.failure(f"{path}: {value!r} is not an integer")
            return Result.success(int(value))
        return Result.success(float(value))
    if isinstance(value, str):
        text = value.strip()
        try:
            parsed = float(text)
        except ValueError:
            return Result.failure(f"{path}: {value!r} is not a valid number")
        if integer:
            if parsed != int(parsed):
                return Result.failure(f"{path}: {value!r} is not an integer")
            return Result.success(int(parsed))
        return Result.success(parsed)
    return Result.failure(f"{path}: expected number, got {type(value).__name__}")
