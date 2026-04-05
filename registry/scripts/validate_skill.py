#!/usr/bin/env python3
"""Validate a skill directory against the Android Agent skill schema.

Usage:
    python scripts/validate_skill.py registry/tiktok/
    python scripts/validate_skill.py /path/to/my-skill/

Exit codes:
    0 = valid
    1 = invalid (with detailed error messages)
"""

import sys
from pathlib import Path

import yaml


REQUIRED_SKILL_FIELDS = ["name", "description", "version", "app_package"]
RECOMMENDED_SKILL_FIELDS = ["display_name", "author", "license", "exports", "tested_on"]
DANGEROUS_PATTERNS = ["os.system(", "eval(", "exec(", "subprocess.call(", "__import__"]


class ValidationResult:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str):
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0

    def print_report(self):
        if self.errors:
            print(f"\n  ERRORS ({len(self.errors)}):")
            for e in self.errors:
                print(f"    [x] {e}")
        if self.warnings:
            print(f"\n  WARNINGS ({len(self.warnings)}):")
            for w in self.warnings:
                print(f"    [!] {w}")
        if self.valid:
            print("\n  RESULT: VALID")
        else:
            print("\n  RESULT: INVALID")


def validate_skill_yaml(skill_dir: Path, result: ValidationResult):
    """Validate skill.yaml schema and content."""
    skill_path = skill_dir / "skill.yaml"
    if not skill_path.exists():
        result.error("skill.yaml not found")
        return None

    try:
        data = yaml.safe_load(skill_path.read_text())
    except yaml.YAMLError as e:
        result.error(f"skill.yaml is not valid YAML: {e}")
        return None

    if not isinstance(data, dict):
        result.error("skill.yaml must be a YAML mapping (dict)")
        return None

    # Required fields
    for field in REQUIRED_SKILL_FIELDS:
        if field not in data:
            result.error(f"skill.yaml missing required field: '{field}'")
        elif not data[field] and field != "app_package":
            result.error(f"skill.yaml field '{field}' is empty")

    # Recommended fields
    for field in RECOMMENDED_SKILL_FIELDS:
        if field not in data:
            result.warn(f"skill.yaml missing recommended field: '{field}'")

    # Name format
    name = data.get("name", "")
    if name and not name.replace("-", "").replace("_", "").isalnum():
        result.error(f"skill name '{name}' must be alphanumeric (hyphens and underscores allowed)")

    # Version format
    version = str(data.get("version", ""))
    if version and not all(p.isdigit() for p in version.split(".")):
        result.warn(f"version '{version}' does not follow semver format (e.g. 1.0.0)")

    # Exports structure
    exports = data.get("exports", {})
    if exports and not isinstance(exports, dict):
        result.error("exports must be a mapping with 'actions' and/or 'workflows' keys")

    return data


def validate_elements_yaml(skill_dir: Path, result: ValidationResult):
    """Validate elements.yaml if present."""
    elements_path = skill_dir / "elements.yaml"
    if not elements_path.exists():
        return  # elements.yaml is optional

    try:
        data = yaml.safe_load(elements_path.read_text())
    except yaml.YAMLError as e:
        result.error(f"elements.yaml is not valid YAML: {e}")
        return

    if data is not None and not isinstance(data, dict):
        result.error("elements.yaml must be a YAML mapping (dict)")


def validate_python_files(skill_dir: Path, result: ValidationResult):
    """Validate Python files in actions/ and workflows/ directories."""
    for folder_name in ["actions", "workflows"]:
        folder = skill_dir / folder_name
        if not folder.exists():
            continue

        for py_file in folder.glob("*.py"):
            if py_file.name == "__init__.py":
                continue

            # Check syntax
            content = py_file.read_text()
            try:
                compile(content, str(py_file), "exec")
            except SyntaxError as e:
                result.error(f"{folder_name}/{py_file.name}: syntax error — {e}")
                continue

            # Check for dangerous imports
            for pattern in DANGEROUS_PATTERNS:
                if pattern in content:
                    result.error(f"{folder_name}/{py_file.name}: dangerous call '{pattern}' found")


def validate_readme(skill_dir: Path, result: ValidationResult):
    """Check for README.md presence."""
    readme = skill_dir / "README.md"
    if not readme.exists():
        result.warn("README.md not found — recommended for skill documentation")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/validate_skill.py <skill_directory>")
        print("Example: python scripts/validate_skill.py registry/tiktok/")
        sys.exit(1)

    skill_dir = Path(sys.argv[1]).resolve()
    if not skill_dir.is_dir():
        print(f"ERROR: '{skill_dir}' is not a directory")
        sys.exit(1)

    print(f"Validating skill: {skill_dir.name}")
    print(f"  Path: {skill_dir}")

    result = ValidationResult()

    validate_skill_yaml(skill_dir, result)
    validate_elements_yaml(skill_dir, result)
    validate_python_files(skill_dir, result)
    validate_readme(skill_dir, result)

    result.print_report()
    sys.exit(0 if result.valid else 1)


if __name__ == "__main__":
    main()
