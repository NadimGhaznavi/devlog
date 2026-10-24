---
name: bmforge-localization
description: Build multilingual application UX from the first release using stable message keys, English source catalogues, request-scoped locale selection and explicit user choice, independent of Jekyll.
---

# Application localization

Read `references/specification.md` and `references/engineering-contract.md`, plus `bmforge-constants` for stable keys. This skill is part of the **greenfield baseline**, even if only English is initially published. Runtime application localization is distinct from BMForge's Jekyll documentation translation process.

1. Copy `assets/Localizer.py` **unchanged** to `<app>/interface/Localizer.py` and `assets/DText.py` into `<app>/constants/DText.py`; copy `assets/en.json` into `<app>/locales/en.json` and replace example keys with the application's actual user-visible messages before implementing the UI. Preserve the component marker.
2. Use `DText` `StrEnum` keys for all visible UI labels, titles, validation errors, notifications and CLI responses. The English JSON catalogue is the authoritative key list; add other UTF-8 locale JSON files only for real requested translations. Untranslated messages fall back to English; unknown keys and mismatched placeholders are errors.
3. For browser requests, select a language with `Localizer.select(explicit=..., accept_language=...)`. An explicit `?lang=` choice takes precedence; otherwise use `Accept-Language` quality and preference order. Match a region/script to its explicit parent only, never a sibling such as `zh-TW` for `zh-CN`. Persist a manual choice only if the app's requirements explicitly call for persistence.
4. Render a visible language selector when the application has multiple published locales. Retain the selected language while navigating where requested and set the HTML `lang` attribute from the actual selected catalogue. Use server-rendered Jinja2 autoescaping and pass the request-specific `locale` into a `t()`/`Localizer.text()` helper. No process-global language state.
5. For CLI commands, resolve an explicit CLI locale or environment preference, then use the **same catalogue keys**. Keep transport method names, JSON field keys, database codes, machine-status values, API error codes, URLs and logs stable; translate only human-facing descriptions.
6. Inspect pinned `references/source/minimal-mistakes/` for the browser language selector and precedence, and `references/source/blog/` for canonical tags with localized display labels. Do not copy Jekyll/Liquid code, redirects or page translation rules into a Python HTTP app.
7. Verify English-only startup, explicit override, browser negotiation, default fallback, a translated locale, placeholder consistency, escaping, no sibling-locale selection and no automatic machine translation. Locale selection must never mutate global app state.

No `Babel`, `gettext`, frontend framework or machine translation service is approved as a hidden dependency. Ask the user and revise the specification first if a feature requires one (e.g., grammatical plural rules or locale-aware number/date formatting).
