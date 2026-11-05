"""Copy dependency license documents from the clean build environment."""

from __future__ import annotations

import shutil
import sys
from importlib.metadata import distributions
from pathlib import Path


def collect_licenses(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for dist in distributions():
        name = dist.metadata["Name"].lower()
        if name == "docforai":
            continue

        target = destination / f"{name}-{dist.version}"
        for path in dist.files or ():
            if path.is_absolute() or ".." in path.parts:
                continue
            directories = [part.lower() for part in path.parts[:-1]]
            in_license_directory = any(
                part.endswith(".dist-info") and next_part == "licenses"
                for part, next_part in zip(directories, directories[1:])
            )
            is_license_file = any(
                marker in path.name.lower()
                for marker in ("license", "licence", "copying", "notice", "copyright")
            )
            if in_license_directory or is_license_file:
                output = target / path
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(dist.locate_file(path), output)
        if name == "cobble":
            target.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(__file__).with_name("cobble-notices.txt"), target / "upstream-notices.txt")

    base = Path(sys.base_prefix)
    python_license = base / "LICENSE.txt"
    if python_license.is_file():
        shutil.copyfile(python_license, destination / "CPython-LICENSE.txt")
    for component in (base / "tcl").glob("*/license.terms"):
        shutil.copyfile(component, destination / f"{component.parent.name}-license.terms")


if __name__ == "__main__":
    collect_licenses(Path(sys.argv[1]))
