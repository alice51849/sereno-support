#!/usr/bin/env python3
"""Validate exact-50 index/support/privacy surfaces without network mutation."""

from __future__ import annotations

import hashlib
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent.parent
SOURCE = json.loads((ROOT / "surface_source.json").read_text(encoding="utf-8"))
LOCALES = SOURCE["official_locales"]
RTL = set(SOURCE["rtl_locales"])
ALLOWED_EMAIL = "hourstag.app@gmail.com"
ERRORS: list[str] = []
PLACEHOLDER_RE = re.compile(
    r"(?:\bTODO\s*:|\bTBD\s*:|\blorem ipsum\b|\bplaceholder content\b|"
    r"\bcoming soon\b)",
    re.I,
)
RAW_KEY_RE = re.compile(
    r"\b(?:feature|button|screen|creator|privacy|support)\.[a-z0-9_.-]+\b", re.I
)
SCRIPT_CHECKS = {
    "ar-SA": r"[\u0600-\u06ff]",
    "bn-BD": r"[\u0980-\u09ff]",
    "zh-Hans": r"[\u3400-\u9fff]",
    "zh-Hant": r"[\u3400-\u9fff]",
    "el": r"[\u0370-\u03ff]",
    "gu-IN": r"[\u0a80-\u0aff]",
    "he": r"[\u0590-\u05ff]",
    "hi": r"[\u0900-\u097f]",
    "ja": r"[\u3040-\u30ff\u3400-\u9fff]",
    "kn-IN": r"[\u0c80-\u0cff]",
    "ko": r"[\uac00-\ud7af]",
    "ml-IN": r"[\u0d00-\u0d7f]",
    "mr-IN": r"[\u0900-\u097f]",
    "or-IN": r"[\u0b00-\u0b7f]",
    "pa-IN": r"[\u0a00-\u0a7f]",
    "ru": r"[\u0400-\u04ff]",
    "ta-IN": r"[\u0b80-\u0bff]",
    "te-IN": r"[\u0c00-\u0c7f]",
    "th": r"[\u0e00-\u0e7f]",
    "uk": r"[\u0400-\u04ff]",
    "ur-PK": r"[\u0600-\u06ff]",
}


def bad(message: str) -> None:
    ERRORS.append(message)


def route_path(locale: str, surface: str) -> Path:
    filename = "index.html" if surface == "index" else f"{surface}.html"
    return ROOT / locale / filename


def canonical_url(locale: str, surface: str) -> str:
    base = SOURCE["base_url"].rstrip("/") + "/"
    filename = "" if surface == "index" else f"{surface}.html"
    return f"{base}{locale}/{filename}"


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.html_attrs: dict[str, str] = {}
        self.canonicals: list[str] = []
        self.alternates: dict[str, list[str]] = {}
        self.descriptions: list[str] = []
        self.og_urls: list[str] = []
        self.og_locales: list[str] = []
        self.titles: list[str] = []
        self._title = False
        self._skip = 0
        self.visible: list[str] = []
        self.hrefs: list[str] = []
        self.ld_json: list[str] = []
        self._ld = False
        self._ld_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        if tag == "html":
            self.html_attrs = values
        if tag in {"style", "script"}:
            self._skip += 1
        if tag == "title":
            self._title = True
        if tag == "link":
            rel = values.get("rel", "").casefold()
            if rel == "canonical":
                self.canonicals.append(values.get("href", ""))
            elif rel == "alternate":
                key = values.get("hreflang", "")
                self.alternates.setdefault(key, []).append(values.get("href", ""))
        if tag == "meta":
            if values.get("name", "").casefold() == "description":
                self.descriptions.append(values.get("content", ""))
            if values.get("property", "").casefold() == "og:url":
                self.og_urls.append(values.get("content", ""))
            if values.get("property", "").casefold() == "og:locale":
                self.og_locales.append(values.get("content", ""))
        if tag == "a" and values.get("href"):
            self.hrefs.append(values["href"])
        if (
            tag == "script"
            and values.get("type", "").casefold() == "application/ld+json"
        ):
            self._ld = True
            self._ld_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._title = False
        if tag == "script" and self._ld:
            self.ld_json.append("".join(self._ld_parts))
            self._ld = False
            self._ld_parts = []
        if tag in {"style", "script"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._ld:
            self._ld_parts.append(data)
        if self._title:
            value = " ".join(data.split())
            if value:
                self.titles.append(value)
        if not self._skip:
            value = " ".join(data.split())
            if value:
                self.visible.append(value)


def normalized_visible(parser: PageParser) -> str:
    return re.sub(r"\s+", " ", " ".join(parser.visible)).strip()


def expected_og_locale(locale: str) -> str:
    explicit = {
        "zh-Hans": "zh_CN", "zh-Hant": "zh_TW", "ca": "ca_ES",
        "hr": "hr_HR", "cs": "cs_CZ", "da": "da_DK", "fi": "fi_FI",
        "el": "el_GR", "he": "he_IL", "hi": "hi_IN", "hu": "hu_HU",
        "id": "id_ID", "it": "it_IT", "ja": "ja_JP", "ko": "ko_KR",
        "ms": "ms_MY", "no": "nb_NO", "pl": "pl_PL", "ro": "ro_RO",
        "ru": "ru_RU", "sk": "sk_SK", "sv": "sv_SE", "th": "th_TH",
        "tr": "tr_TR", "uk": "uk_UA", "vi": "vi_VN",
    }
    if locale in explicit:
        return explicit[locale]
    parts = locale.split("-", 1)
    return parts[0] if len(parts) == 1 else f"{parts[0]}_{parts[1].upper()}"


def validate_links(path: Path, parser: PageParser) -> None:
    for href in parser.hrefs:
        value = html.unescape(href).strip()
        if not value or value.startswith(("#", "mailto:", "tel:")):
            continue
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https"}:
            if parsed.netloc == "alice51849.github.io":
                prefix = f"/{SOURCE['site_key']}/"
                if parsed.path.startswith(prefix):
                    relative = unquote(parsed.path[len(prefix) :])
                    if not relative or relative.endswith("/"):
                        relative += "index.html"
                    target = ROOT / relative
                    if not target.is_file():
                        bad(f"{path.relative_to(ROOT)}: broken same-site link {value}")
            continue
        if parsed.scheme or parsed.netloc:
            bad(f"{path.relative_to(ROOT)}: unsupported link {value}")
            continue
        relative = unquote(parsed.path)
        if not relative:
            continue
        target = (path.parent / relative).resolve()
        if ROOT not in target.parents and target != ROOT:
            bad(f"{path.relative_to(ROOT)}: link escapes repo {value}")
        elif relative.endswith("/"):
            if not (target / "index.html").is_file():
                bad(f"{path.relative_to(ROOT)}: broken directory link {value}")
        elif not target.is_file():
            bad(f"{path.relative_to(ROOT)}: broken local link {value}")


def validate_page(locale: str, surface: str) -> tuple[PageParser, str]:
    path = route_path(locale, surface)
    if not path.is_file():
        bad(f"{locale}/{surface}: missing page")
        return PageParser(), ""
    raw = path.read_text(encoding="utf-8")
    parser = PageParser()
    try:
        parser.feed(raw)
        parser.close()
    except Exception as exc:
        bad(f"{path.relative_to(ROOT)}: invalid HTML parser input: {exc}")
    canonical = canonical_url(locale, surface)
    if parser.html_attrs.get("lang") != locale:
        bad(f"{path.relative_to(ROOT)}: html lang mismatch")
    expected_dir = "rtl" if locale in RTL else "ltr"
    if parser.html_attrs.get("dir") != expected_dir:
        bad(f"{path.relative_to(ROOT)}: dir must be {expected_dir}")
    if not re.search(r"<meta\s+charset=[\"']?utf-8", raw, re.I):
        bad(f"{path.relative_to(ROOT)}: missing UTF-8 charset")
    if not parser.titles or not " ".join(parser.titles).strip():
        bad(f"{path.relative_to(ROOT)}: missing title")
    if len(parser.descriptions) != 1 or not parser.descriptions[0].strip():
        bad(f"{path.relative_to(ROOT)}: expected one meta description")
    if parser.canonicals != [canonical]:
        bad(f"{path.relative_to(ROOT)}: canonical mismatch {parser.canonicals!r}")
    if parser.og_urls != [canonical]:
        bad(f"{path.relative_to(ROOT)}: og:url mismatch {parser.og_urls!r}")
    expected_og = expected_og_locale(locale)
    if parser.og_locales != [expected_og]:
        bad(
            f"{path.relative_to(ROOT)}: og:locale must be {expected_og}, "
            f"got {parser.og_locales!r}"
        )
    expected_hreflang = set(LOCALES) | {"x-default"}
    if set(parser.alternates) != expected_hreflang:
        bad(
            f"{path.relative_to(ROOT)}: hreflang mismatch "
            f"missing={sorted(expected_hreflang-set(parser.alternates))} "
            f"extra={sorted(set(parser.alternates)-expected_hreflang)}"
        )
    for hreflang, values in parser.alternates.items():
        expected = (
            canonical_url("en-US", surface)
            if hreflang == "x-default"
            else canonical_url(hreflang, surface)
        )
        if values != [expected]:
            bad(f"{path.relative_to(ROOT)}: bad {hreflang} alternate {values!r}")
    schema_ok = False
    for raw_schema in parser.ld_json:
        try:
            value = json.loads(raw_schema)
        except json.JSONDecodeError:
            continue
        candidates = value if isinstance(value, list) else [value]
        if any(
            isinstance(candidate, dict)
            and candidate.get("@context") == "https://schema.org"
            and candidate.get("inLanguage") == locale
            and candidate.get("url") == canonical
            for candidate in candidates
        ):
            schema_ok = True
            break
    if not schema_ok:
        bad(f"{path.relative_to(ROOT)}: missing locale-bound schema.org payload")
    visible = normalized_visible(parser)
    if len(visible) < (80 if surface == "support" else 120):
        bad(f"{path.relative_to(ROOT)}: insufficient substantive visible content")
    if ALLOWED_EMAIL not in raw:
        bad(f"{path.relative_to(ROOT)}: public contact missing")
    if PLACEHOLDER_RE.search(visible):
        bad(f"{path.relative_to(ROOT)}: placeholder wording found")
    if RAW_KEY_RE.search(visible):
        bad(f"{path.relative_to(ROOT)}: raw localization key found")
    if locale in SCRIPT_CHECKS and not re.search(SCRIPT_CHECKS[locale], visible):
        bad(f"{path.relative_to(ROOT)}: expected native script not found")
    if SOURCE["app"].get("kids"):
        notice = SOURCE["parent_notice"][locale]
        if notice not in visible or 'data-surface-parent-notice="true"' not in raw:
            bad(f"{path.relative_to(ROOT)}: parent/guardian notice missing")
    app_id = SOURCE["app"].get("app_store_id")
    if app_id and surface in {"index", "support"}:
        if f"/id{app_id}" not in raw:
            bad(f"{path.relative_to(ROOT)}: own App Store ID {app_id} missing")
    if not app_id and 'data-surface-own-app="true"' in raw:
        bad(f"{path.relative_to(ROOT)}: unavailable app has an own-app CTA")
    if surface == "support" and ALLOWED_EMAIL not in visible:
        bad(f"{path.relative_to(ROOT)}: support equivalent lacks public contact")
    if SOURCE["site_key"] == "hourstag-support" and surface == "support":
        paid = SOURCE["hourstag_paid"][locale]["answer"]
        generated = surface in SOURCE.get("content", {}).get(locale, {})
        marker_ok = (
            True
            if generated
            else raw.count('data-surface-paid-contract="true"') == 1
        )
        if paid not in visible or not marker_ok:
            bad(f"{path.relative_to(ROOT)}: paid-upfront contract missing")
    validate_links(path, parser)
    return parser, visible


def validate_language_distinction(all_visible: dict[tuple[str, str], str]) -> None:
    for surface in ("index", "support", "privacy"):
        baseline = all_visible.get(("en-US", surface), "")
        for locale in LOCALES:
            if locale.startswith("en-"):
                continue
            current = all_visible.get((locale, surface), "")
            if current and baseline and current == baseline:
                bad(f"{locale}/{surface}: copied English fallback")


def validate_authority() -> None:
    for surface, anchors in SOURCE.get("authority_anchors", {}).items():
        raw = route_path("en-US", surface).read_text(encoding="utf-8").casefold()
        for anchor in anchors:
            if anchor.casefold() not in raw:
                bad(f"en-US/{surface}: missing verified authority anchor {anchor!r}")
    if SOURCE["app"].get("kids"):
        for locale in LOCALES:
            raw = route_path(locale, "privacy").read_text(encoding="utf-8")
            if "hourstag.app@gmail.com" not in raw:
                bad(f"{locale}/privacy: Kids privacy contact missing")


def validate_emails() -> None:
    for path in ROOT.rglob("*"):
        if (
            not path.is_file()
            or ".git" in path.parts
            or path.suffix.lower()
            in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".mp3", ".pyc"}
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for address in set(
            re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
        ):
            if address.casefold().rstrip(".") != ALLOWED_EMAIL:
                bad(f"{path.relative_to(ROOT)}: unexpected public email {address}")


def validate_sitemap() -> None:
    path = ROOT / "sitemap.xml"
    if not path.is_file():
        bad("sitemap.xml missing")
        return
    source = path.read_text(encoding="utf-8")
    urls = set(re.findall(r"<loc>([^<]+)</loc>", source))
    for locale in LOCALES:
        for surface in ("index", "support", "privacy"):
            expected = canonical_url(locale, surface)
            if expected not in urls:
                bad(f"sitemap.xml missing {expected}")


def infer_help_locale(path: Path) -> str:
    if path.name == "help.html":
        return (
            "zh-Hant"
            if SOURCE["site_key"] == "hourstag-support"
            else "en-US"
        )
    match = re.fullmatch(r"help\.([^.]+(?:-[^.]+)?)\.html", path.name)
    return match.group(1) if match else "en-US"


def validate_optional_help() -> None:
    for path in sorted(ROOT.glob("help*.html")):
        locale = infer_help_locale(path)
        if locale not in LOCALES:
            continue
        raw = path.read_text(encoding="utf-8")
        parser = PageParser()
        parser.feed(raw)
        parser.close()
        visible = normalized_visible(parser)
        if len(visible) < 80:
            bad(f"{path.name}: optional help lacks substantive content")
        if ALLOWED_EMAIL not in raw:
            bad(f"{path.name}: optional help lacks public contact")
        if PLACEHOLDER_RE.search(visible) or RAW_KEY_RE.search(visible):
            bad(f"{path.name}: optional help contains placeholder or raw key")
        if locale in SCRIPT_CHECKS and not re.search(SCRIPT_CHECKS[locale], visible):
            bad(f"{path.name}: optional help lacks expected native script")
        if SOURCE["app"].get("kids"):
            notice = SOURCE["parent_notice"][locale]
            if notice not in visible:
                bad(f"{path.name}: optional Kids help lacks parent notice")
        if SOURCE["site_key"] == "hourstag-support":
            paid = SOURCE["hourstag_paid"][locale]["answer"]
            if paid not in visible or 'data-surface-paid-contract="true"' not in raw:
                bad(f"{path.name}: optional help has stale payment guidance")


def validate_receipt() -> None:
    path = ROOT / "surface-build.json"
    if not path.is_file():
        bad("surface-build.json missing")
        return
    receipt = json.loads(path.read_text(encoding="utf-8"))
    records = receipt.get("files", {})
    if receipt.get("officialLocaleCount") != 50:
        bad("surface-build.json locale count mismatch")
    if receipt.get("requiredSurfaceCount") != 150:
        bad("surface-build.json surface count mismatch")
    actual: dict[str, str] = {}
    for relative, expected_sha in records.items():
        target = ROOT / relative
        if not target.is_file():
            bad(f"surface-build.json references missing {relative}")
            continue
        sha = hashlib.sha256(target.read_bytes()).hexdigest()
        actual[relative] = sha
        if sha != expected_sha:
            bad(f"surface-build.json SHA mismatch for {relative}")
    digest = hashlib.sha256(
        json.dumps(actual, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if digest != receipt.get("contentDigest"):
        bad("surface-build.json content digest mismatch")


def main() -> None:
    all_visible: dict[tuple[str, str], str] = {}
    for locale in LOCALES:
        for surface in ("index", "support", "privacy"):
            _, visible = validate_page(locale, surface)
            all_visible[(locale, surface)] = visible
    validate_language_distinction(all_visible)
    validate_authority()
    validate_emails()
    validate_sitemap()
    validate_optional_help()
    validate_receipt()
    if ERRORS:
        print("\n".join(ERRORS))
        raise SystemExit(1)
    print(
        f"PASS {SOURCE['site_key']}: "
        "50 locales × 3 required surfaces; link/schema/language/contact/privacy checks"
    )


if __name__ == "__main__":
    main()
