#!/usr/bin/env python3
"""Validate the exact-50 support-site contract and deterministic receipt."""

from __future__ import annotations

import hashlib
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent.parent
SOURCE = json.loads((ROOT / "surface_source.json").read_text(encoding="utf-8"))
LOCALES = SOURCE["official_locales"]
RTL = set(SOURCE["rtl_locales"])
SURFACES = ("index", "support", "privacy")
ALLOWED_EMAIL = "hourstag.app@gmail.com"
ERRORS: list[str] = []
PLACEHOLDER_RE = re.compile(
    r"(?:\{\{[^}]+\}\}|%\([^)]+\)s|%s|\bTODO\b|\bTBD\b|"
    r"\bLOREM\b|\bPLACEHOLDER\b|\bXXX\b|\bundefined\b|\bnull\b)"
)
RAW_KEY_RE = re.compile(
    r"\b(?:feature|button|screen|creator|privacy|support|nav|footer)"
    r"\.[a-z0-9_.-]+\b",
    re.I,
)
CLAIM_RE = re.compile(
    r"(?:\b[0-5](?:\.\d)?\s*(?:★|stars?|/5)\b|"
    r"(?:#|No\.\s*)1\b|best[- ]selling|top[- ]ranked)",
    re.I,
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


def x_default_url(surface: str) -> str:
    """Root-level English equivalent of a surface, per upstream convention."""
    base = SOURCE["base_url"].rstrip("/") + "/"
    return base + SOURCE.get("x_default_targets", {}).get(surface, "")


def bad(message: str) -> None:
    ERRORS.append(message)


def filename(surface: str) -> str:
    return "index.html" if surface == "index" else f"{surface}.html"


def relative_path(locale: str, surface: str) -> str:
    return f"{locale}/{filename(surface)}"


def route_path(locale: str, surface: str) -> Path:
    return ROOT / relative_path(locale, surface)


def canonical_url(locale: str, surface: str) -> str:
    suffix = "" if surface == "index" else filename(surface)
    return f"{SOURCE['base_url'].rstrip('/')}/{locale}/{suffix}"


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.html_attrs: dict[str, str] = {}
        self.canonicals: list[str] = []
        self.alternates: dict[str, list[str]] = {}
        self.ld_json: list[str] = []
        self.hrefs: list[str] = []
        self.visible: list[str] = []
        self._skip = 0
        self._ld = False
        self._ld_parts: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        if tag == "html":
            self.html_attrs = values
        if tag == "link":
            rel = values.get("rel", "").casefold()
            if rel == "canonical":
                self.canonicals.append(values.get("href", ""))
            elif rel == "alternate":
                hreflang = values.get("hreflang", "")
                self.alternates.setdefault(hreflang, []).append(
                    values.get("href", "")
                )
        if tag == "a" and values.get("href"):
            self.hrefs.append(values["href"])
        if tag in {"style", "script"}:
            self._skip += 1
        if (
            tag == "script"
            and values.get("type", "").casefold() == "application/ld+json"
        ):
            self._ld = True
            self._ld_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._ld:
            self.ld_json.append("".join(self._ld_parts))
            self._ld = False
            self._ld_parts = []
        if tag in {"style", "script"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._ld:
            self._ld_parts.append(data)
        if not self._skip:
            value = " ".join(data.split())
            if value:
                self.visible.append(value)


def site_digest() -> str:
    digest = hashlib.sha256()
    rows = []
    for locale in LOCALES:
        for surface in SURFACES:
            path = route_path(locale, surface)
            rows.append((relative_path(locale, surface), file_sha(path)))
    for path, sha in sorted(rows):
        digest.update(path.encode())
        digest.update(b"\n")
        digest.update(sha.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def validate_source_contract() -> None:
    if len(LOCALES) != 50 or len(set(LOCALES)) != 50:
        bad("official_locales must contain exactly 50 unique locales")
    if set(SOURCE.get("locale_names", {})) != set(LOCALES):
        bad("locale_names does not exactly match official_locales")
    expected = {
        relative_path(locale, surface)
        for locale in LOCALES
        for surface in SURFACES
    }
    preserved = set(SOURCE.get("preserved_surfaces", []))
    generated = set(SOURCE.get("generated_surfaces", []))
    if preserved & generated:
        bad("preserved_surfaces and generated_surfaces overlap")
    if preserved | generated != expected:
        bad("surface decision partition does not equal 150 required routes")
    if set(SOURCE.get("preserved_surface_sha256", {})) != preserved:
        bad("preserved_surface_sha256 keys mismatch")
    decisions = SOURCE.get("surface_decisions", {})
    if set(decisions) != expected:
        bad("surface_decisions does not cover every required route")
    for path in preserved:
        if decisions.get(path) != "AUGMENT":
            bad(f"{path}: preserved route decision must be AUGMENT")
    for path in generated:
        if decisions.get(path) != "GENERATE":
            bad(f"{path}: generated route decision must be GENERATE")


def validate_page(
    locale: str, surface: str
) -> tuple[str, PageParser, str] | None:
    relative = relative_path(locale, surface)
    path = ROOT / relative
    if not path.is_file():
        bad(f"{relative}: missing")
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        bad(f"{relative}: invalid UTF-8: {exc}")
        return None
    parser = PageParser()
    try:
        parser.feed(raw)
        parser.close()
    except Exception as exc:
        bad(f"{relative}: HTML parser failure: {exc}")
    expected_dir = "rtl" if locale in RTL else "ltr"
    if parser.html_attrs.get("lang") != locale:
        bad(f"{relative}: lang mismatch")
    if parser.html_attrs.get("dir") != expected_dir:
        bad(f"{relative}: dir mismatch")
    canonical = canonical_url(locale, surface)
    if parser.canonicals != [canonical]:
        bad(f"{relative}: canonical mismatch {parser.canonicals!r}")
    expected_hreflang = set(LOCALES) | {"x-default"}
    if set(parser.alternates) != expected_hreflang:
        bad(
            f"{relative}: hreflang set mismatch "
            f"missing={sorted(expected_hreflang-set(parser.alternates))} "
            f"extra={sorted(set(parser.alternates)-expected_hreflang)}"
        )
    for hreflang, values in parser.alternates.items():
        expected_url = (
            x_default_url(surface)
            if hreflang == "x-default"
            else canonical_url(hreflang, surface)
        )
        if values != [expected_url]:
            bad(f"{relative}: duplicate or wrong {hreflang} alternate")
    if len(parser.alternates) != 51:
        bad(f"{relative}: expected exactly 51 alternate values")
    valid_schema = False
    if not parser.ld_json:
        bad(f"{relative}: JSON-LD missing")
    for raw_schema in parser.ld_json:
        try:
            value = json.loads(raw_schema)
        except json.JSONDecodeError as exc:
            bad(f"{relative}: JSON-LD parse failure: {exc}")
            continue
        candidates = value if isinstance(value, list) else [value]
        if any(
            isinstance(candidate, dict)
            and candidate.get("@context") == "https://schema.org"
            and candidate.get("inLanguage") == locale
            and candidate.get("url") == canonical
            for candidate in candidates
        ):
            valid_schema = True
        encoded = json.dumps(value, ensure_ascii=False)
        if re.search(
            r'"(?:aggregateRating|ratingValue|reviewCount|offers|price)"\s*:',
            encoded,
        ):
            bad(f"{relative}: prohibited rating/offer field in JSON-LD")
    if not valid_schema:
        bad(f"{relative}: locale-bound JSON-LD missing")
    if raw.count("<!-- ls-family:start -->") != 1:
        bad(f"{relative}: cross-promo block missing or duplicated")
    if raw.count("<!-- ls-family:end -->") != 1:
        bad(f"{relative}: cross-promo end marker missing or duplicated")
    visible = re.sub(r"\s+", " ", " ".join(parser.visible)).strip()
    if len(visible) < 120:
        bad(f"{relative}: insufficient localized visible content")
    if PLACEHOLDER_RE.search(visible):
        bad(f"{relative}: placeholder text found")
    if RAW_KEY_RE.search(visible):
        bad(f"{relative}: raw localization key found")
    if locale in SCRIPT_CHECKS and not re.search(SCRIPT_CHECKS[locale], visible):
        bad(f"{relative}: expected native script missing")
    if ALLOWED_EMAIL not in raw:
        bad(f"{relative}: required contact email missing")
    if CLAIM_RE.search(visible):
        bad(f"{relative}: prohibited unverified price/rating/ranking claim found")
    allowed_urls = set(SOURCE.get("verified_app_store_urls", []))
    for href in parser.hrefs:
        value = html.unescape(href).strip()
        parsed = urlsplit(value)
        if parsed.netloc.casefold() == "apps.apple.com" and value not in allowed_urls:
            bad(f"{relative}: unverified App Store CTA {value}")
    if relative in set(SOURCE.get("preserved_surfaces", [])):
        sha = SOURCE["preserved_surface_sha256"][relative]
        marker = f"<!-- surface-contract-upstream-sha256:{sha} -->"
        if raw.count(marker) != 1:
            bad(f"{relative}: upstream preservation marker missing")
    else:
        if raw.count("<!-- surface-contract-generated -->") != 1:
            bad(f"{relative}: generated route marker missing")
    return raw, parser, visible


def validate_language_distinction(
    visible_by_route: dict[tuple[str, str], str]
) -> None:
    for surface in SURFACES:
        baseline = visible_by_route.get(("en-US", surface), "")
        for locale in LOCALES:
            if locale.startswith("en-"):
                continue
            current = visible_by_route.get((locale, surface), "")
            if baseline and current == baseline:
                bad(f"{locale}/{filename(surface)}: copied English fallback")


def validate_emails() -> None:
    binary_suffixes = {
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".mp3", ".pyc",
        ".ds_store",
    }
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.suffix.casefold() in binary_suffixes or path.name == ".DS_Store":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for address in set(
            re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
        ):
            if address.casefold().rstrip(".") != ALLOWED_EMAIL:
                bad(f"{path.relative_to(ROOT)}: unexpected email {address}")


def validate_sitemap() -> None:
    path = ROOT / "sitemap.xml"
    if not path.is_file():
        bad("sitemap.xml missing")
        return
    raw = path.read_text(encoding="utf-8")
    urls = [
        html.unescape(value.strip())
        for value in re.findall(r"<loc\b[^>]*>(.*?)</loc>", raw, re.I | re.S)
        if value.strip()
    ]
    for locale in LOCALES:
        for surface in SURFACES:
            expected = canonical_url(locale, surface)
            if urls.count(expected) != 1:
                bad(f"sitemap.xml expected exactly one {expected}")


def validate_receipt() -> None:
    path = ROOT / "surface-build.json"
    if not path.is_file():
        bad("surface-build.json missing")
        return
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        bad(f"surface-build.json invalid: {exc}")
        return
    expected_paths = {
        relative_path(locale, surface)
        for locale in LOCALES
        for surface in SURFACES
    }
    records = receipt.get("files", {})
    if receipt.get("officialLocaleCount") != 50:
        bad("receipt locale count mismatch")
    if receipt.get("requiredSurfaceCount") != 150:
        bad("receipt required surface count mismatch")
    if set(records) != expected_paths:
        bad("receipt files do not exactly cover 150 required surfaces")
    for relative, expected_sha in records.items():
        target = ROOT / relative
        if not target.is_file():
            bad(f"receipt references missing {relative}")
        elif file_sha(target) != expected_sha:
            bad(f"receipt mismatch for {relative}")
    if receipt.get("siteDigest") != site_digest():
        bad("receipt siteDigest mismatch")


def validate_locale_directories() -> None:
    found = set()
    for child in ROOT.iterdir():
        if not child.is_dir() or child.name in {".git", "tools"}:
            continue
        if any((child / filename(surface)).exists() for surface in SURFACES):
            found.add(child.name)
    if found != set(LOCALES):
        bad(
            f"locale directory set mismatch "
            f"missing={sorted(set(LOCALES)-found)} extra={sorted(found-set(LOCALES))}"
        )


def main() -> None:
    validate_source_contract()
    validate_locale_directories()
    visible_by_route: dict[tuple[str, str], str] = {}
    missing = 0
    for locale in LOCALES:
        for surface in SURFACES:
            result = validate_page(locale, surface)
            if result is None:
                missing += 1
            else:
                visible_by_route[(locale, surface)] = result[2]
    validate_language_distinction(visible_by_route)
    validate_emails()
    validate_sitemap()
    validate_receipt()
    if ERRORS:
        print("\n".join(ERRORS))
        raise SystemExit(1)
    print(
        json.dumps(
            {
                "site": SOURCE["site_key"],
                "locales": 50,
                "requiredSurfaces": 150,
                "missing": missing,
                "mismatch": 0,
                "digest": site_digest(),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
