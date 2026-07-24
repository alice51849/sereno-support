#!/usr/bin/env python3
"""Build the Sereno support site's exact-50 localization catalog."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HOME = ROOT.parent
METADATA = HOME / "24_Sereno/_store/metadata.json"
APP_I18N = HOME / "24_Sereno/Resources/i18n.json"
GENERIC_I18N = HOME / "00_GrowthEngine/geo/pages/apps/hourstaglite/locales"
OUTPUT = ROOT / "locales.json"

APP_KEYS = {
    "featuresTitle": "1000+ living soundscapes",
    "soundTitle": "Sounds",
    "soundText": (
        "Every soundscape is generated live, note by note — so it never loops, "
        "no matter how long you listen."
    ),
    "soundHelp": "Add sounds from the library to start layering and tuning.",
    "mixerTitle": "Mixer",
    "mixerText": (
        "Layer rain, ocean, fire and more. Tune each track's volume, balance and "
        "warmth until it's perfectly yours."
    ),
    "scenesTitle": "Scenes",
    "scenesText": "Every scene, plus save your own",
    "scenesHelp": "Build a mix, then save it here as your own scene.",
    "timerTitle": "Sleep timer, fade-out & sunrise",
    "timerText": "Set timer",
    "privacyBadge": "100% offline · no ads · no tracking",
    "privacyText": (
        "No subscription. No ads. No account. Everything works fully offline."
    ),
    "purchaseTitle": "One-time purchase",
    "purchaseText": (
        "One quiet payment unlocks it all. No subscription, ever."
    ),
    "restore": "Restore purchases",
    "contactTitle": "Contact support",
    "privacyTitle": "Privacy Policy",
}


def app_language(locale: str) -> str:
    if locale in {"zh-Hans", "zh-Hant"}:
        return locale
    return locale.split("-")[0]


def main() -> None:
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    app_i18n = json.loads(APP_I18N.read_text(encoding="utf-8"))
    if len(metadata) != 50:
        raise RuntimeError(f"Sereno metadata must be exact-50, found {len(metadata)}")

    missing_keys = sorted(set(APP_KEYS.values()) - set(app_i18n))
    if missing_keys:
        raise RuntimeError(f"Missing Sereno app translations: {missing_keys}")

    catalog: dict[str, dict] = {}
    for locale, meta in sorted(metadata.items()):
        generic_path = GENERIC_I18N / f"{locale}.json"
        if not generic_path.is_file():
            raise RuntimeError(f"Missing generic localization: {generic_path}")
        generic = json.loads(generic_path.read_text(encoding="utf-8"))
        language = app_language(locale)

        def translated(key: str) -> str:
            value = app_i18n[APP_KEYS[key]].get(language)
            if not value:
                raise RuntimeError(
                    f"Missing Sereno translation for {locale}/{language}: {APP_KEYS[key]}"
                )
            return value

        copy = {key: translated(key) for key in APP_KEYS}
        copy.update(
            {
                "home": meta["name"],
                "support": generic["support"],
                "privacy": generic["privacy"],
                "heroTitle": meta["subtitle"],
                "hero": meta["promotionalText"],
                "supportTitle": generic["supportTitle"],
                "supportIntro": meta["promotionalText"],
                "privacyIntro": generic["privacyIntro"],
                "deviceTitle": generic["deviceTitle"],
                "deviceText": f"{translated('privacyText')} {translated('soundText')}",
                "storeTitle": generic["purchaseTitle"],
                "storeText": generic["purchaseText"],
                "metaDescription": meta["promotionalText"],
                "pageTitles": {
                    "home": f"{meta['name']} — {meta['subtitle']}",
                    "privacy": f"{translated('privacyTitle')} — {meta['name']}",
                    "support": f"{generic['support']} — {meta['name']}",
                },
            }
        )
        if any(not isinstance(value, (str, dict)) or not value for value in copy.values()):
            raise RuntimeError(f"Incomplete website localization: {locale}")
        catalog[locale] = copy

    OUTPUT.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote exact-{len(catalog)} Sereno website localizations to {OUTPUT}")


if __name__ == "__main__":
    main()
