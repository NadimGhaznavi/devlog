---
title: Constants Component
lang: en
locale: en-US
language_name: English
component_id: "bmforge.constants"
spec_version: "0.1.0"
spec_status: "draft"
translation_key: bmforge-component-constants
---

**Component ID:** `{{ page.component_id }}` · **Specification:** `{{ page.spec_version }}` ({{ page.spec_status }})

## Intent

Avoid **magic strings and significant numeric literals** from the first application module. Name values by their **semantic domain**, not by generic piles of fields/defaults/labels. This is a coding standard, not a new runtime library, service, metaclass or framework. Every BMForge greenfield application installs this skill as part of its baseline.

## Approved runtime modules

| Origin | Module | Approved use |
| --- | --- | --- |
| Python stdlib | `typing` | `Final` to document fixed values, paths, ports, shape constants and immutable intended defaults |
| Python stdlib | `enum` | `StrEnum` and `IntEnum` for closed protocol, action and status vocabularies |

Use only what the chosen constant group requires. `Final` expresses intent for type checkers; it is **not a runtime immutability guarantee**. Do not introduce a custom `ConstGroup` metaclass, registry, global settings cache or third-party config framework without user approval.

## Naming and ownership

- Store classes in `<app>/constants/D<Name>.py`; one meaningful domain group per module. Use class names such as `DProject`, `DNetwork`, `DZMQ`, `DField`, `DSQL`, `DGameDef`, or `DStatus`. Prefer uppercase attribute names, module/class name agreement and explicit imports from the owning module.
- Define application identity and literal `VERSION`, CMDB metadata, deployed component paths and network listener declarations in `D<Project>` (start with `templates/project/constants/DProject.py`). Maintain the literal version so release tooling can inspect it without executing code.
- Use `Final` for fixed values: configuration keys, protocol envelope fields, action identifiers, semantic defaults, ports, timeouts, file paths and SQL column mappings. Use `StrEnum` for semantically closed text values and `IntEnum` for stable numeric codes, preserving external serialized values.
- Keep the class definitions clear and data-only. Never load environment files, perform I/O or call external services merely by importing a constants module.
- Centralize definitions **once** within their domain. Cross-reference named values where it improves clarity, but avoid circular imports and aliases that obscure ownership. Do not create a separate `DField`, `DLabel`, and `DDefault` for each feature as a reflex.
- Do **not** replace an intentional schema field, API key, status code, network method or config name with a translated value. They must remain stable across languages and are persisted as canonical identifiers.

Example:

```python
from enum import StrEnum
from typing import Final

class DNetwork:
    HTTP_PORT: Final[int] = 49700
    CONFIG_FILE: Final[str] = "conf/app.json"

class DStatus(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"
```

## Boundary with localization

A user-visible label is **not** a protocol constant. Use a stable `DText` message key and look up the localized value through [Application Localization]({{ site.baseurl }}{% link pages/component-localization.md %}). Example: `DStatus.RUNNING` remains `"running"` in MariaDB/JSON, while `localizer.text(DText.STATUS_RUNNING, locale=language)` returns the appropriate readable label. Do not build English-only `*_LABEL` constants into activities, interfaces or renderers.

Ordinary SQL queries, temporary local variables, MIME types, obvious one-off display prose and non-semantic numbers do not each require their own constants. Prioritize duplicated or behaviourally significant literals rather than replacing everything with indirection. Configurable runtime overrides belong in the existing [Runtime Configuration]({{ site.baseurl }}{% link pages/runtime-configuration.md %}) process; constant defaults are not the final deployed configuration.

## Frozen source examples

- Snake Lab `NadimGhaznavi/snake-lab` commit `52b02e054b2161701813e9231abf5db8635f3ec1`, frozen under `components/reference/snake-lab/snakelab/constants/`: `DGame.py` (`Final`, `IntEnum`, `StrEnum`), `DSQL.py` (stable column mapping), `DMyLog.py` (log-level vocabulary), `DSnakeLab.py` (app defaults and CMDB inventory).
- BMGeoIP `NadimGhaznavi/bmgeoip` commit `35c8745c7003a124dce5b5799b08b2d7c851fbfc`, frozen under `components/reference/bmgeoip/bmgeoip/constants/`: `DBMGeoIP.py`, `DGeoIp.py`, `DZMQ.py` (small app, domain and protocol groups).

The snapshots document **patterns**, not values to import into unrelated applications. No imports from Snake Lab or BMGeoIP in a generated application.

## Acceptance checks

1. Behavioral string/number literals live in domain groups or an explicitly selected standard enum; no scattered repeated message methods, schema keys, status codes or magic ports.
2. Application-wide identity and version are literal, stable and discoverable; CMDB network and persistent-data declarations agree with deployment.
3. `D` modules do not import domain activities or perform side effects. No custom constant framework or unapproved dependencies appear.
4. Changing a constant preserves wire/storage compatibility unless an explicit migration was approved.
5. Translation keys are stable `StrEnum` values; display text is looked up from locale catalogues, not embedded as English-only constants.

---

[Application Localization]({{ site.baseurl }}{% link pages/component-localization.md %}) · [Component Blueprints]({{ site.baseurl }}{% link pages/component-blueprints.md %})
