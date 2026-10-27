---
title: Application Localization Component
lang: en
locale: en-US
language_name: English
component_id: "bmforge.localization"
spec_version: "0.1.0"
spec_status: "draft"
translation_key: bmforge-component-localization
---

**Component ID:** `{{ page.component_id }}` · **Specification:** `{{ page.spec_version }}` ({{ page.spec_status }})

## Intent

Prepare **multilingual runtime application interfaces from their first release**, without assuming any additional language has already been translated. This is **not Jekyll documentation translation**: [Multilingual Documentation]({{ site.baseurl }}{% link pages/multilingual-documentation.md %}) deliberately defers full documentation translations until content settles. By contrast, application UI, CLI and human-facing messages use stable localization keys from the beginning.

The existing Minimal Mistakes fork provides the reference for language discovery, manual choice and fallback; the blog provides the reference for translated content and display-only taxonomy labels. The application implementation is a small **Python standard-library localizer**, not a port of Liquid, Jekyll, browser redirects or site theme assets.

## Approved runtime modules

| Origin | Module | Approved use |
| --- | --- | --- |
| Python stdlib | `json` | Load application-owned UTF-8 message catalogues |
| Python stdlib | `pathlib` | Locate packaged catalogue files |
| Python stdlib | `re` | Validate locale tags and simple placeholder field names |
| Python stdlib | `string` | `Formatter` for checking named placeholders |
| Python stdlib | `enum` | `StrEnum` for stable `DText` message keys (separate constants module) |

No added pip dependencies are needed. Where an app already uses the HTTP Display Server, its approved `jinja2` renderer provides autoescaping; `jinja2` is **not** an additional dependency of the localizer. **Do not silently add Babel, gettext extensions, machine translation services, locale brokers, frontend frameworks or a translation database.** Obtain user approval and update this spec for capabilities the small contract cannot meet, such as grammatical plural categories or locale-aware date/number formatting.

## Canonical files and application responsibilities

Copy `components/templates/localization/interface/Localizer.py` **unchanged** to `<app>/interface/Localizer.py`. It carries the literal `BMFORGE_COMPONENT` marker `bmforge.localization` at specification `0.1.0`. Copy `components/templates/constants/DText.py` to `<app>/constants/DText.py` and **adapt the key list** for real application messages. Copy `components/templates/localization/locales/en.json` to `<app>/locales/en.json`, replacing example messages with the corresponding English source text.

```text
<app>/
  constants/DText.py           stable keys: app.title, timer.start, ...
  interface/Localizer.py       identical standard-library localizer
  locales/en.json              complete source-language catalogue
  locales/fr.json              optional real translations, when approved
```

Application activities and presenters request `localizer.text(DText.APP_TITLE, locale=language)`; they do **not** hardcode a visible `"Start timer"` or `"Running"` label. `DStatus.RUNNING`, persisted values, API method names, JSON field keys, SQL column names, error **codes**, URLs and command names remain canonical and untranslated. This is the same distinction used by the blog's localized *display* tags versus canonical tag IDs.

## Locale negotiation and fallback

- English (`en`) is required and supplies the complete source message-key inventory. Additional catalogues are UTF-8 JSON mapping stable keys to human text; partial translation is allowed with **per-key English fallback**.
- In a browser request, an **explicit user choice** (e.g. `?lang=fr`) wins over the request's `Accept-Language` preference list. In its absence, parse the header's ordered language tags and valid `q` values, then choose the first supported match. Unsupported preferences fall back to `en`.
- Normalize case and underscores for matching; use exact locale, then **explicit parents only** (`fr-CA` → `fr`; `zh-Hant-HK` → `zh-Hant` → `zh`). **Never substitute sibling locales** such as `zh-TW` for `zh-CN`.
- User choice is per-request, not process-global. An application may explicitly persist language preference if the user requests that feature; the core localizer does not create cookies, local-storage state or automatic redirects. A visible selector appears when multiple translated languages actually exist, not for English-only apps.
- Carry the selected language through the application's UI navigation (for example, in generated query parameters) and set the HTML `lang` attribute. Use safe DOM text APIs or Jinja2 HTML autoescaping. Do not treat translations or user-supplied substitutions as trusted HTML.

For CLI output, resolve a user-provided language option or relevant environment preference and use the same catalogue. Keep structured/API/log identifiers fixed so monitoring and consumers never depend on translated text.

## Translation integrity

- `DText` keys and the English JSON file must match; new user-facing text requires a stable key before rendering. A missing English key is an error, not a silently fabricated label.
- Translated files may be incomplete, but may **not introduce unknown keys**. Named substitutions such as `{name}` must have the same set of names as English. No attribute/index expressions or format-code execution are supported.
- The localizer performs no automatic translation. Add only translations supplied by the user or deliberately commissioned and reviewed; do not invent a multilingual release from an English-only source.
- The code includes no built-in plural grammar, localized numeric/calendar formatting or RTL layout engine. When required, define the behaviour and obtain approval for a revised component rather than pretending a text lookup solves all internationalization.

## Frozen examples

- `NadimGhaznavi/minimal-mistakes` commit `6586f5792c895fbec782ef6f510902951c9af38c`: `_includes/language-selector.html` and `assets/js/multilingual.js`. They show explicit/manual selection, browser preference, parent-language fallback and no sibling-language substitution.
- `NadimGhaznavi/blog` commit `b275f06d98ba4545de15bea392f4eb8e8a820f67`: `_data/taxonomy_translations.yml` and `es/index.md`. They show stable canonical taxonomy keys, localized display labels and explicit `lang` and `translation_key` metadata.

Pinned copies live under `components/reference/minimal-mistakes/` and `components/reference/blog/`. **These are Jekyll website examples, not runtime Python modules.** Do not import/copy Liquid templates or their JavaScript redirection logic into application handlers.

## Acceptance checks

1. An English-only application renders every user-facing message from stable `DText` keys and the bundled source catalogue, with no extra pip dependency.
2. A second catalogue can be added without changing the localizer; translated values display appropriately and missing translations fall back to English.
3. Explicit choice overrides browser preferences; `Accept-Language` quality ordering, parent fallback, invalid headers and absent preferences resolve predictably.
4. Script/region siblings remain distinct; `zh-CN` is never silently replaced with `zh-TW`.
5. Missing source keys, unknown translation keys, unsafe placeholders and placeholder-set mismatches fail clearly.
6. Concurrent requests/CLI operations can use different languages without changing a global locale; human-facing labels translate while wire/status/DB values remain stable.
7. HTML output is safely escaped, language switching respects actual published locale availability, and the UI advertises its selected `lang`. Do not infer browser rendering from HTTP health checks alone.

---

[Constants]({{ site.baseurl }}{% link pages/component-constants.md %}) · [Multilingual Documentation]({{ site.baseurl }}{% link pages/multilingual-documentation.md %}) · [Component Blueprints]({{ site.baseurl }}{% link pages/component-blueprints.md %})
