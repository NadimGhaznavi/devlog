#!/usr/bin/env python3
"""Check BMForge application metadata without importing project code."""

import argparse
import ast
from ipaddress import IPv4Address
from pathlib import Path, PurePosixPath
import re


NUMBER = r"(0|[1-9][0-9]*)"
PRERELEASE = r"(0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
VERSION = re.compile(rf"{NUMBER}\.{NUMBER}\.{NUMBER}(-{PRERELEASE}(\.{PRERELEASE})*)?(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?")
FIELDS = ("VERSION", "CMDB_TYPE", "CMDB_SUBTYPE", "CMDB_SUPPLIER", "CMDB_CODENAME", "BASE_DIR")


def text_value(value: object, field: str, limit: int = 255) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
            or re.search(r"__[A-Z_]+__", value)):
        raise ValueError(f"{field} must be a nonempty literal string of at most {limit} characters, without controls or placeholders")
    return value


def validate(source: str, name: str, pathname: str, codename: str | None = None,
             release_version: str | None = None) -> dict:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None or re.search(r"__[A-Z_]+__", name):
        raise ValueError("Application name must match [A-Za-z_][A-Za-z0-9_]* and contain no placeholder")
    expected = f"{name.lower()}/constants/D{name}.py"
    if pathname != expected:
        raise ValueError(f"Constants path must be {expected}")
    statements = list(ast.parse(source).body)
    assignments = {}
    for node in statements:
        if isinstance(node, ast.ClassDef):
            statements.extend(node.body)
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id in (*FIELDS, "CMDB_COMPONENTS", "CMDB_DATABASES", "CMDB_NETWORK"):
                if target.id in assignments or len(targets) != 1:
                    raise ValueError(f"{target.id} must have exactly one independent assignment")
                assignments[target.id] = value
    values = {}
    for field in FIELDS:
        node = assignments.get(field)
        if not isinstance(node, ast.Constant):
            raise ValueError(f"{field} must have one literal assignment at module or class scope")
        values[field] = text_value(node.value, field)
        if field in ("VERSION", "CMDB_CODENAME") and node.lineno != node.end_lineno:
            raise ValueError(f"{field} must be a single-line literal for release tooling")
    if VERSION.fullmatch(values['VERSION']) is None:
        raise ValueError("VERSION must be a semantic version without a leading v")
    if values['BASE_DIR'] != f"/opt/prod/{name.lower()}":
        raise ValueError(f"BASE_DIR must be /opt/prod/{name.lower()}")
    if codename is not None:
        text_value(codename, "Release codename")
    if release_version is not None:
        text_value(release_version, "Release version")
        if VERSION.fullmatch(release_version) is None:
            raise ValueError("Release version must be a semantic version without a leading v")
    for field, limit in (("CMDB_COMPONENTS", 4096), ("CMDB_DATABASES", 64)):
        if field not in assignments:
            continue
        declarations = ast.literal_eval(assignments[field])
        if not isinstance(declarations, (tuple, list)):
            raise ValueError(f"{field} must be a literal tuple or list of pairs")
        for pair in declarations:
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise ValueError(f"{field} entries must be (name, value) pairs")
            text_value(pair[0], field)
            value = text_value(pair[1], field, limit)
            if field == "CMDB_COMPONENTS" and (".." in PurePosixPath(value).parts or str(PurePosixPath(value)) == "."):
                raise ValueError("CMDB component paths must not contain parent traversal or resolve to '.'")
    if "CMDB_NETWORK" in assignments:
        declarations = ast.literal_eval(assignments["CMDB_NETWORK"])
        if not isinstance(declarations, (tuple, list)):
            raise ValueError("CMDB_NETWORK must be a literal tuple or list of listener tuples")
        uses = set()
        for listener in declarations:
            if not isinstance(listener, tuple) or len(listener) != 3:
                raise ValueError("CMDB_NETWORK entries must be (use, interface, port) tuples")
            use, interface, port = listener
            if not isinstance(use, str) or not use.strip() or use != use.strip():
                raise ValueError("CMDB_NETWORK use must be a nonempty string without surrounding whitespace")
            if use in uses:
                raise ValueError(f"CMDB_NETWORK has duplicate use: {use}")
            uses.add(use)
            if not isinstance(interface, str):
                raise ValueError("CMDB_NETWORK interface must be an IPv4 address string")
            try:
                IPv4Address(interface)
            except ValueError as error:
                raise ValueError("CMDB_NETWORK interface must be an IPv4 address string") from error
            if type(port) is not int or not 1 <= port <= 65535:
                raise ValueError("CMDB_NETWORK port must be an integer from 1 to 65535")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("constants", help="Repository-relative constants path")
    parser.add_argument("--name", required=True, help="Exact CMDB application name")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--codename", help="Also validate the proposed release message")
    parser.add_argument("--release-version", help="Also validate the proposed release version")
    args = parser.parse_args()
    try:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.name) is None:
            raise ValueError("Application name must match [A-Za-z_][A-Za-z0-9_]*")
        expected = f"{args.name.lower()}/constants/D{args.name}.py"
        if args.constants != expected:
            raise ValueError(f"Constants path must be {expected}")
        validate((args.root / args.constants).read_text(), args.name, args.constants,
                 args.codename, args.release_version)
    except (OSError, ValueError, TypeError, SyntaxError) as error:
        parser.exit(1, f"CMDB check failed: {error}\n")
    print("CMDB metadata is compliant.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
