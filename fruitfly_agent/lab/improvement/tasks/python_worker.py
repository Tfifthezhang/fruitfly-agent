"""Worker for a restricted Python function subset, never a general code sandbox.

Started with isolated Python, no inherited environment and bounded POSIX resources.
Only function definitions and approved syntax/builtins/method calls are accepted.
No imports, files, reflection, classes, decorators or process/network primitives.
"""
import ast
import builtins
import json
import resource
import sys

BUILTINS = (
    "abs", "all", "any", "bool", "dict", "enumerate", "float", "int", "len", "list",
    "isinstance", "max", "min", "range", "reversed", "round", "set", "sorted", "str", "sum", "tuple", "zip",
    "Exception", "ValueError", "TypeError", "KeyError", "IndexError", "ZeroDivisionError",
)
METHODS = frozenset({
    "append", "extend", "insert", "pop", "remove", "clear", "copy", "count", "index", "sort", "reverse",
    "get", "items", "keys", "values", "setdefault", "update", "add", "discard", "intersection", "union",
    "difference", "lower", "upper", "strip", "lstrip", "rstrip", "split", "rsplit", "join", "replace",
    "partition", "rpartition", "startswith", "endswith", "isdigit", "isalpha", "isalnum", "casefold", "find",
})
NODES = frozenset({
    ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Assign, ast.AugAssign,
    ast.AnnAssign, ast.Expr, ast.If, ast.For, ast.While, ast.Break, ast.Continue, ast.Pass,
    ast.Raise, ast.Try, ast.ExceptHandler, ast.Call, ast.keyword, ast.Name, ast.Load, ast.Store,
    ast.Constant, ast.List, ast.Tuple, ast.Set, ast.Dict, ast.Subscript, ast.Slice,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp, ast.Attribute,
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.comprehension, ast.Lambda,
    ast.JoinedStr, ast.FormattedValue,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.UAdd, ast.USub, ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq,
    ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot, ast.In, ast.NotIn,
})


def validate(source, entry_point):
    tree = ast.parse(source)
    if not tree.body or any(not isinstance(n, ast.FunctionDef) for n in tree.body):
        raise ValueError("return function definitions only; imports and module statements are unsupported")
    names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    if entry_point not in names:
        raise ValueError("required function is missing: " + entry_point)
    nodes = list(ast.walk(tree))
    if len(nodes) > 3000:
        raise ValueError("code exceeds the syntax limit")
    parents = {child: parent for parent in nodes for child in ast.iter_child_nodes(parent)}
    for node in nodes:
        if type(node) not in NODES:
            raise ValueError("unsupported syntax: " + type(node).__name__)
        if isinstance(node, (ast.FunctionDef, ast.arg, ast.Name)):
            name = node.name if isinstance(node, ast.FunctionDef) else node.arg if isinstance(node, ast.arg) else node.id
            if name.startswith("__"):
                raise ValueError("dunder names are forbidden")
        if isinstance(node, ast.FunctionDef) and node.decorator_list:
            raise ValueError("decorators are forbidden")
        if isinstance(node, ast.Attribute):
            parent = parents[node]
            if node.attr not in METHODS or not isinstance(parent, ast.Call) or parent.func is not node:
                raise ValueError("unsupported attribute access: " + node.attr)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in BUILTINS and node.func.id not in names:
                    raise ValueError("unsupported function call: " + node.func.id)
            elif not isinstance(node.func, ast.Attribute):
                raise ValueError("indirect function calls are forbidden")
    return compile(tree, "<generated-function>", "exec")


def equal(actual, expected):
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return actual == expected
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(equal(a, b) for a, b in zip(actual, expected))
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(equal(actual[k], expected[k]) for k in actual)
    return actual == expected


def brief(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)[:160]


def run(payload):
    code = validate(payload["code"], payload["entry_point"])
    passed, failure = 0, ""
    for index, case in enumerate(payload["tests"], 1):
        scope = {"__builtins__": {name: getattr(builtins, name) for name in BUILTINS}}
        # Fresh globals/default arguments for every check; no cross-test state.
        exec(code, scope)
        initial = json.dumps([case.get("args", []), case.get("kwargs", {})], ensure_ascii=False)
        try:
            actual = scope[payload["entry_point"]](*case.get("args", []), **case.get("kwargs", {}))
            serialized = json.dumps(actual, ensure_ascii=False, allow_nan=False)
            if len(serialized) > 10000:
                raise ValueError("result exceeds 10000 characters")
            actual = json.loads(serialized)
            ok = "raises" not in case and equal(actual, case["expected"])
            detail = "expected " + brief(case.get("expected")) + ", got " + brief(actual)
        except Exception as exc:
            ok = "raises" in case and type(exc).__name__ == case["raises"]
            detail = "expected " + case.get("raises", "a value") + ", raised " + type(exc).__name__
        if case.get("preserve_args", False):
            try:
                unchanged = initial == json.dumps([case.get("args", []), case.get("kwargs", {})], ensure_ascii=False)
            except (TypeError, ValueError):
                unchanged = False
            if not unchanged:
                ok, detail = False, "input arguments mutated"
        if ok:
            passed += 1
        elif not failure:
            failure = f"check {index}: {detail}; args={brief(case.get('args', []))}"
    total = len(payload["tests"])
    return {"score": passed / total, "feedback": f"{passed}/{total} checks passed" + ("; " + failure if failure else "")}


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (2, 3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    # Linux enforces address-space limits; macOS has different memory semantics.
    if sys.platform.startswith("linux"):
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024,) * 2)
    payload = json.loads(sys.stdin.buffer.read(100001))
    try:
        result = run(payload)
    except (SyntaxError, ValueError, TypeError, NameError, MemoryError, RecursionError) as exc:
        result = {"score": 0.0, "feedback": "code rejected/failed: " + type(exc).__name__ + ": " + str(exc)[:300]}
    sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
