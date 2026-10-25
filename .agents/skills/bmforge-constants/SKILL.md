---
name: bmforge-constants
description: Enforce BMForge's domain-grouped Python constants and stable programmatic identifiers from the first application module, avoiding magic strings and magic numbers.
---

# Application constants

Read `references/specification.md` and `references/engineering-contract.md`. This is a **baseline greenfield skill** installed with `bmforge-project`; no separate runtime service or dependency is introduced.

1. Bootstrap already creates `<app>/constants/D<Name>.py` from the canonical `assets/DProject.py`, with project name and subtype resolved. Use this existing literal-version file; don't overwrite or regenerate it. Create other `D<Name>.py` modules by domain only when needed.
2. Use `typing.Final` for defaults, paths, ports, protocol keys, JSON keys, timeouts, column-name mappings and fixed configuration values. Use `enum.StrEnum` (or `enum.IntEnum` for numeric codes) when a closed vocabulary is meaningful, such as statuses or actions. Do not invent a metaclass, constant registry or import of another application's code.
3. Keep names descriptive and domain grouped, such as `DNetwork.HTTP_PORT`, `DZMQ.PROTOCOL_VERSION`, `DField.RUN_ID`, `DStatus.RUNNING`. Preserve externally established literal values when replacing magic strings. Configuration overrides resolve through the existing runtime-config contract, not by changing constants at runtime.
4. Expose stable machine-facing identifiers, never translated UI text. **Human-readable labels** belong in the `bmforge-localization` message catalogues; UI uses stable `DText` keys, not English strings in activities or handlers.
5. Inspect `references/source/snake-lab/` for sophisticated constants (`Final` plus enums and SQL mappings) and `references/source/bmgeoip/` for the smaller `DGeoIp`, `DZMQ`, `DBMGeoIP` pattern. They are examples, not importable dependencies.
6. Check new source changes for repeated behavioral literals. Don't turn incidental prose, SQL statements, MIME types or everyday math constants into unnecessary abstractions; define a named group only when the value has semantic meaning or is reused.
7. Run application tests to prove request/message keys, schema values, version metadata and defaults have not changed accidentally. Do not translate IDs or change wire/schema representations.
