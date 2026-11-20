"""Minimal import smoke test for environments without a camera."""

import importlib


MODULES = (
    "auth.dependencies",
    "execution_tracker",
    "step_recognizer",
    "sop_manager",
    "api.v1.sop",
    "main",
)


if __name__ == "__main__":
    for module_name in MODULES:
        importlib.import_module(module_name)
        print(f"OK {module_name}")
