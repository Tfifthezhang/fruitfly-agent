"""Static dependency inspection shared by architecture tests."""
import ast
from importlib.util import resolve_name
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOTS = (ROOT / "fruitfly_agent", ROOT / "eval")
DOCUMENTED_ROOTS = (*SOURCE_ROOTS, ROOT / "tests")

ALLOWED_EDGES = {
    "fruitfly_agent.core": {"fruitfly_agent.core"},
    "fruitfly_agent.lab": {"fruitfly_agent.core", "fruitfly_agent.lab"},
    "eval": {
        "fruitfly_agent.core",
        "fruitfly_agent.lab",
        "eval",
        "fruitfly_agent.providers",
    },
    "fruitfly_agent.providers": {"fruitfly_agent.core", "fruitfly_agent.providers"},
    "fruitfly_agent.interactive": {
        "fruitfly_agent.core",
        "fruitfly_agent.interactive",
    },
    "fruitfly_agent": {"fruitfly_agent.core"},
    "fruitfly_agent.run": {
        "fruitfly_agent.run",
        "fruitfly_agent.core",
        "fruitfly_agent.lab",
        "fruitfly_agent.providers",
        "fruitfly_agent.interactive",
    },
    "fruitfly_agent.__main__": {"fruitfly_agent.run"},
}

def _module_info(path: Path) -> tuple[str, bool]:
    """Return (module path, is_package). A package's __init__ is its own base."""
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    is_pkg = parts[-1] == "__init__"
    if is_pkg:
        parts = parts[:-1]
    return ".".join(parts), is_pkg

def _parent(module: str) -> str:
    return module.rsplit(".", 1)[0] if "." in module else ""

def _resolve(node: ast.ImportFrom, source_module: str, is_pkg: bool) -> list[str]:
    """Resolve an ImportFrom to absolute module targets.

    ``from x import *`` depends on module x itself (no per-name targets).
    """
    names = [alias.name for alias in node.names]
    base = source_module if is_pkg else _parent(source_module)
    if node.level > 0:
        for _ in range(node.level - 1):
            base = _parent(base)
        if node.module:
            base = f"{base}.{node.module}" if base else node.module
        return [base if n == "*" else f"{base}.{n}" for n in names]
    # absolute import
    if node.module:
        return [node.module if n == "*" else f"{node.module}.{n}" for n in names]
    return names

def _top(module: str) -> str:
    parts = module.split(".")
    if parts[0] == "eval":
        return "eval"
    if len(parts) >= 2:
        return ".".join(parts[:2])
    return parts[0]

def _is_project_module(module: str) -> bool:
    return (
        module == "eval"
        or module.startswith("eval.")
        or module == "fruitfly_agent"
        or module.startswith("fruitfly_agent.")
    )

def _project_imports(path: Path) -> list[str]:
    source, is_pkg = _module_info(path)
    return [target for target in imported_modules(path.read_text(encoding="utf-8"), source, is_pkg)
            if _is_project_module(target)]


def imported_modules(code: str, source: str, is_pkg: bool = False) -> list[str]:
    """Inspect nested/static and literal dynamic imports, including aliases.

    Computed dynamic targets are explicitly rejected by boundary_violations;
    this is a static guard, not a general Python execution sandbox.
    """
    tree = ast.parse(code)
    imports = []
    importlib_names = {"importlib"}
    importer_names = {"__import__"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    importlib_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "importlib":
            importer_names.update(alias.asname or alias.name for alias in node.names
                                  if alias.name == "import_module")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.extend(_resolve(node, source, is_pkg))
        elif isinstance(node, ast.Call):
            dynamic = (isinstance(node.func, ast.Name) and node.func.id in importer_names
                       or isinstance(node.func, ast.Attribute) and node.func.attr == "import_module"
                       and isinstance(node.func.value, ast.Name) and node.func.value.id in importlib_names)
            if not dynamic:
                continue
            target = node.args[0] if node.args else next((kw.value for kw in node.keywords if kw.arg == "name"), None)
            if not isinstance(target, ast.Constant) or not isinstance(target.value, str):
                imports.append("<computed dynamic import>")
                continue
            name = target.value
            if name.startswith("."):
                package = node.args[1] if len(node.args) > 1 else next((kw.value for kw in node.keywords if kw.arg == "package"), None)
                if not isinstance(package, ast.Constant) or not isinstance(package.value, str):
                    imports.append("<computed dynamic import>")
                    continue
                name = resolve_name(name, package.value)
            imports.append(name)
    return imports


def boundary_violations(code: str, source: str, is_pkg: bool = False) -> list[str]:
    allowed = ALLOWED_EDGES.get(_top(source))
    if allowed is None:
        return [f"{source}: unknown top-level namespace"]
    violations = []
    for target in imported_modules(code, source, is_pkg):
        if target == "<computed dynamic import>":
            violations.append(f"{source}: dynamic import target must be a literal")
        elif target == "tests" or target.startswith("tests."):
            violations.append(f"{source} imports test support {target}")
        elif _is_project_module(target) and _top(target) not in allowed:
            violations.append(f"{source} imports {target}")
        elif _top(source) == "fruitfly_agent.core" and target.split(".")[0] in {"openai", "anthropic", "harbor"}:
            violations.append(f"{source} imports provider/benchmark SDK {target}")
    return violations
