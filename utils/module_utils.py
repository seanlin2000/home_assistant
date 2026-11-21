"""Load a Python file as a module by its path, for files that cannot be imported by name: the Home Assistant component's modules, whose package
imports Home Assistant (not installed in this project's environments), and the scripts under scripts/, which are not a package."""

import importlib.util
from pathlib import Path
from types import ModuleType


def module_from_file(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
