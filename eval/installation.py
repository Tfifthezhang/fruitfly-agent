"""Validate the explicit package material used by Harbor task installation."""

from email.parser import Parser
import hashlib
import json
from pathlib import Path
import tomllib
import zipfile


SOURCE_FILES = ("pyproject.toml", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md")
SOURCE_PACKAGES = ("fruitfly_agent", "eval")


def installation_identity(path: Path) -> dict:
    """Identify the exact install inputs without reading workspace state."""
    path = validate_installation(path)
    files = ([path] if path.is_file() else
             [*(path / name for name in SOURCE_FILES),
              *(p for name in SOURCE_PACKAGES for p in (path / name).rglob("*.py")
                if "__pycache__" not in p.parts and not p.is_symlink())])
    rows = sorted((p.name if path.is_file() else p.relative_to(path).as_posix(),
                   hashlib.sha256(p.read_bytes()).hexdigest()) for p in files)
    digest = hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()
    return {"schema_version": 1, "project": "fruitfly-agent", "version": "0.1",
            "kind": "wheel" if path.is_file() else "source", "sha256": digest, "files": rows}


def validate_installation(path: Path) -> Path:
    path = path.expanduser().resolve()
    if path.is_dir():
        required = (*SOURCE_FILES, *(f"{name}/__init__.py" for name in SOURCE_PACKAGES))
        missing = [name for name in required if not (path / name).is_file()]
        if missing:
            raise ValueError("incomplete FruitFlyAgent source: " + ", ".join(missing))
        project = tomllib.loads((path / "pyproject.toml").read_text(encoding="utf-8")).get("project", {})
        name, version = project.get("name"), project.get("version")
    elif path.is_file() and path.suffix == ".whl":
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                metadata = [name for name in names if name.endswith(".dist-info/METADATA")]
                if len(metadata) != 1 or any(f"{name}/__init__.py" not in names for name in SOURCE_PACKAGES):
                    raise ValueError("wheel must contain FruitFlyAgent runtime, Eval, and one metadata record")
                fields = Parser().parsestr(archive.read(metadata[0]).decode("utf-8"))
                name, version = fields["Name"], fields["Version"]
        except zipfile.BadZipFile as exc:
            raise ValueError("invalid FruitFlyAgent wheel") from exc
    else:
        raise ValueError("FRUITFLY_EVAL_PACKAGE must point to a source directory or .whl file")
    if name != "fruitfly-agent" or version != "0.1":
        raise ValueError("installation material must be fruitfly-agent version 0.1")
    return path


def resolve_installation(value: str | None, *, checkout: Path) -> Path:
    if value and value.strip():
        return validate_installation(Path(value))
    try:
        return validate_installation(checkout)
    except ValueError as exc:
        raise ValueError(
            "no complete source checkout; set FRUITFLY_EVAL_PACKAGE to an explicit "
            "FruitFlyAgent source directory or wheel"
        ) from exc
