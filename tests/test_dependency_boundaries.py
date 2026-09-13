import ast
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FEATURE_PACKAGES = {"drop", "library", "text"}


def _internal_module_names(package_root):
    names = set()
    for path in package_root.rglob("*.py"):
        relative = path.relative_to(package_root)
        if relative.name == "__init__.py":
            continue
        names.add(relative.with_suffix("").parts[0])
    return names


def _resolved_import(source_path, node):
    if not isinstance(node, ast.ImportFrom) or node.level == 0:
        return node.module or ""
    relative_parent = source_path.parent.relative_to(PROJECT_ROOT).parts
    keep = len(relative_parent) - (node.level - 1)
    prefix = relative_parent[:keep]
    suffix = tuple((node.module or "").split(".")) if node.module else ()
    return ".".join((*prefix, *suffix))


class FeatureDependencyBoundaryTests(unittest.TestCase):
    def test_feature_packages_do_not_import_each_others_internal_modules(self):
        violations = []
        internal_names = {
            package: _internal_module_names(PROJECT_ROOT / "nightwire" / package)
            for package in FEATURE_PACKAGES
        }
        for source_package in sorted(FEATURE_PACKAGES):
            package_root = PROJECT_ROOT / "nightwire" / source_package
            for source_path in sorted(package_root.rglob("*.py")):
                tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
                for node in ast.walk(tree):
                    imported_modules = []
                    if isinstance(node, ast.Import):
                        imported_modules.extend(alias.name for alias in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        imported_modules.append(_resolved_import(source_path, node))

                    for imported in imported_modules:
                        parts = imported.split(".")
                        if len(parts) < 2 or parts[0] != "nightwire":
                            continue
                        target_package = parts[1]
                        internal_import = len(parts) >= 3
                        if isinstance(node, ast.ImportFrom) and len(parts) == 2:
                            internal_import = any(
                                alias.name in internal_names[target_package]
                                for alias in node.names
                            ) if target_package in internal_names else False
                        if target_package in FEATURE_PACKAGES - {source_package} and internal_import:
                            violations.append(
                                f"{source_path.relative_to(PROJECT_ROOT)}:{node.lineno} imports {imported}"
                            )

        self.assertEqual(
            violations,
            [],
            "Feature packages must communicate through Core or another feature's public package API:\n"
            + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
