#!/usr/bin/env python3
"""Augment upstream-authored pages and build only genuinely missing surfaces."""

from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATH = ROOT / "surface_source.json"
RECEIPT_PATH = ROOT / "surface-build.json"
SURFACES = ("index", "support", "privacy")
ALLOWED_EMAIL = "hourstag.app@gmail.com"


def x_default_url(source: dict, surface: str) -> str:
    """Root-level English equivalent of a surface, per upstream convention."""
    base = source["base_url"].rstrip("/") + "/"
    return base + source.get("x_default_targets", {}).get(surface, "")


def read_source() -> dict:
    source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    locales = source.get("official_locales", [])
    if source.get("schema") != "support-required-surfaces/v1":
        raise SystemExit("unsupported surface_source.json schema")
    if len(locales) != 50 or len(set(locales)) != 50:
        raise SystemExit("surface_source.json must declare exactly 50 locales")
    if set(source.get("locale_names", {})) != set(locales):
        raise SystemExit("locale_names must exactly match official_locales")
    required = {
        f"{locale}/{filename(surface)}"
        for locale in locales
        for surface in SURFACES
    }
    preserved = set(source.get("preserved_surfaces", []))
    generated = set(source.get("generated_surfaces", []))
    if preserved & generated or preserved | generated != required:
        raise SystemExit("preserved_surfaces and generated_surfaces must partition 150 routes")
    if set(source.get("preserved_surface_sha256", {})) != preserved:
        raise SystemExit("preserved surface SHA map mismatch")
    if set(source.get("surface_decisions", {})) != required:
        raise SystemExit("surface_decisions must cover every required route")
    return source


def filename(surface: str) -> str:
    return "index.html" if surface == "index" else f"{surface}.html"


def relative_path(locale: str, surface: str) -> str:
    return f"{locale}/{filename(surface)}"


def route_path(locale: str, surface: str) -> Path:
    return ROOT / relative_path(locale, surface)


def direction(source: dict, locale: str) -> str:
    return "rtl" if locale in set(source["rtl_locales"]) else "ltr"


def canonical_url(source: dict, locale: str, surface: str) -> str:
    suffix = "" if surface == "index" else filename(surface)
    return f"{source['base_url'].rstrip('/')}/{locale}/{suffix}"


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_if_changed(path: Path, value: str) -> None:
    if path.exists() and path.read_text(encoding="utf-8") == value:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def og_locale(locale: str) -> str:
    explicit = {
        "zh-Hans": "zh_CN",
        "zh-Hant": "zh_TW",
        "ca": "ca_ES",
        "hr": "hr_HR",
        "cs": "cs_CZ",
        "da": "da_DK",
        "fi": "fi_FI",
        "el": "el_GR",
        "he": "he_IL",
        "hi": "hi_IN",
        "hu": "hu_HU",
        "id": "id_ID",
        "it": "it_IT",
        "ja": "ja_JP",
        "ko": "ko_KR",
        "ms": "ms_MY",
        "no": "nb_NO",
        "pl": "pl_PL",
        "ro": "ro_RO",
        "ru": "ru_RU",
        "sk": "sk_SK",
        "sv": "sv_SE",
        "th": "th_TH",
        "tr": "tr_TR",
        "uk": "uk_UA",
        "vi": "vi_VN",
    }
    if locale in explicit:
        return explicit[locale]
    parts = locale.split("-", 1)
    return parts[0] if len(parts) == 1 else f"{parts[0]}_{parts[1].upper()}"


def alternate_links(source: dict, surface: str) -> str:
    rows = ["<!-- surface-contract-hreflang:start -->"]
    for locale in source["official_locales"]:
        rows.append(
            '<link rel="alternate" hreflang="{}" href="{}">'.format(
                html.escape(locale, quote=True),
                html.escape(canonical_url(source, locale, surface), quote=True),
            )
        )
    rows.append(
        '<link rel="alternate" hreflang="x-default" href="{}">'.format(
            html.escape(x_default_url(source, surface), quote=True)
        )
    )
    rows.append("<!-- surface-contract-hreflang:end -->")
    return "\n".join(rows)


def schema_json(
    source: dict,
    locale: str,
    surface: str,
    title: str,
    description: str,
) -> str:
    canonical = canonical_url(source, locale, surface)
    payload: dict = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": title,
        "description": description,
        "inLanguage": locale,
        "url": canonical,
        "isPartOf": {
            "@type": "WebSite",
            "name": source["app"]["name"],
            "url": source["base_url"],
        },
    }
    app_id = source["app"].get("app_store_id")
    if app_id:
        payload["about"] = {
            "@type": "MobileApplication",
            "name": source["app"]["name"],
            "operatingSystem": "iOS",
            "sameAs": f"https://apps.apple.com/app/id{app_id}",
        }
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).replace("</", "<\\/")


def plain_text(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def title_and_description(text: str, fallback: str) -> tuple[str, str]:
    title_match = re.search(r"<title\b[^>]*>(.*?)</title>", text, re.I | re.S)
    description_match = re.search(
        r'<meta\b(?=[^>]*\bname=["\']description["\'])'
        r'(?=[^>]*\bcontent=["\']([^"\']*)["\'])[^>]*>',
        text,
        re.I,
    )
    title = plain_text(title_match.group(1)) if title_match else fallback
    description = (
        html.unescape(description_match.group(1)).strip()
        if description_match
        else title
    )
    return title, description


def replace_href(tag: str, href: str) -> str:
    escaped = html.escape(href, quote=True)
    if re.search(r"\bhref=[\"'][^\"']*[\"']", tag, re.I):
        return re.sub(
            r"\bhref=([\"'])[^\"']*\1",
            lambda match: f'href="{escaped}"',
            tag,
            count=1,
            flags=re.I,
        )
    return tag[:-1] + f' href="{escaped}">'


def localize_privacy_links(source: dict, text: str) -> str:
    nav_match = re.search(
        r'(<nav\s+class=["\']primary-nav["\'][^>]*>)(.*?)(</nav>)',
        text,
        re.I | re.S,
    )
    if not nav_match:
        raise SystemExit("upstream page lacks primary-nav")
    nav_body = nav_match.group(2)
    anchors = list(re.finditer(r"<a\b[^>]*>.*?</a>", nav_body, re.I | re.S))
    if len(anchors) < 3:
        raise SystemExit("upstream primary-nav lacks privacy slot")
    privacy_anchor = anchors[2]
    replacement = replace_href(privacy_anchor.group(0), "privacy.html")
    nav_body = (
        nav_body[: privacy_anchor.start()]
        + replacement
        + nav_body[privacy_anchor.end() :]
    )
    text = (
        text[: nav_match.start()]
        + nav_match.group(1)
        + nav_body
        + nav_match.group(3)
        + text[nav_match.end() :]
    )
    root_privacy = f"{source['base_url'].rstrip('/')}/privacy.html"
    text = re.sub(
        r'(\bhref=["\'])' + re.escape(root_privacy) + r'(["\'])',
        r"\1privacy.html\2",
        text,
        flags=re.I,
    )
    return text


def replace_alternates(source: dict, surface: str, text: str) -> str:
    block = alternate_links(source, surface)
    managed = re.compile(
        r"\s*<!-- surface-contract-hreflang:start -->.*?"
        r"<!-- surface-contract-hreflang:end -->\s*",
        re.I | re.S,
    )
    if managed.search(text):
        return managed.sub("\n" + block + "\n", text, count=1)
    pattern = re.compile(
        r'<link\b(?=[^>]*\brel=["\']alternate["\'])[^>]*>',
        re.I,
    )
    matches = list(pattern.finditer(text))
    if matches:
        span = text[matches[0].start() : matches[-1].end()]
        if not pattern.sub("", span).strip():
            return (
                text[: matches[0].start()]
                + block
                + text[matches[-1].end() :]
            )
        token = "__SURFACE_CONTRACT_HREFLANG_BLOCK__"
        text = (
            text[: matches[0].start()]
            + token
            + text[matches[0].end() :]
        )
        text = pattern.sub("", text)
        return text.replace(token, block, 1)
    return re.sub(r"</head>", block + "\n</head>", text, count=1, flags=re.I)


def replace_schema(
    source: dict, locale: str, surface: str, text: str
) -> str:
    title, description = title_and_description(text, source["app"]["name"])
    block = (
        "<!-- surface-contract-schema:start -->\n"
        '<script type="application/ld+json">'
        + schema_json(source, locale, surface, title, description)
        + "</script>\n"
        "<!-- surface-contract-schema:end -->"
    )
    pattern = re.compile(
        r"\s*<!-- surface-contract-schema:start -->.*?"
        r"<!-- surface-contract-schema:end -->\s*",
        re.I | re.S,
    )
    if pattern.search(text):
        return pattern.sub("\n" + block + "\n", text, count=1)
    return re.sub(r"</head>", block + "\n</head>", text, count=1, flags=re.I)


def verify_upstream(source: dict, locale: str, surface: str, text: str) -> None:
    relative = relative_path(locale, surface)
    marker = (
        f"<!-- surface-contract-upstream-sha256:"
        f"{source['preserved_surface_sha256'][relative]} -->"
    )
    if marker not in text:
        actual = hashlib.sha256(text.encode("utf-8")).hexdigest()
        expected = source["preserved_surface_sha256"][relative]
        if actual != expected:
            raise SystemExit(f"{relative}: upstream SHA mismatch before augmentation")
    html_match = re.search(r"<html\b([^>]*)>", text, re.I)
    if not html_match:
        raise SystemExit(f"{relative}: missing html element")
    attrs = html_match.group(1)
    if not re.search(rf'\blang=["\']{re.escape(locale)}["\']', attrs, re.I):
        raise SystemExit(f"{relative}: upstream lang mismatch")
    expected_dir = direction(source, locale)
    if not re.search(rf'\bdir=["\']{expected_dir}["\']', attrs, re.I):
        raise SystemExit(f"{relative}: upstream dir mismatch")
    canonical = canonical_url(source, locale, surface)
    if not re.search(
        r'<link\b(?=[^>]*\brel=["\']canonical["\'])'
        rf'(?=[^>]*\bhref=["\']{re.escape(canonical)}["\'])[^>]*>',
        text,
        re.I,
    ):
        raise SystemExit(f"{relative}: upstream canonical mismatch")
    if text.count("<!-- ls-family:start -->") != 1:
        raise SystemExit(f"{relative}: upstream cross-promo missing")
    if ALLOWED_EMAIL not in text:
        raise SystemExit(f"{relative}: upstream contact missing")


def augment_upstream(source: dict, locale: str, surface: str) -> str:
    path = route_path(locale, surface)
    if not path.is_file():
        raise SystemExit(f"{relative_path(locale, surface)}: preserved file missing")
    text = path.read_text(encoding="utf-8")
    verify_upstream(source, locale, surface, text)
    sha = source["preserved_surface_sha256"][relative_path(locale, surface)]
    marker = f"<!-- surface-contract-upstream-sha256:{sha} -->"
    if marker not in text:
        text = re.sub(
            r"(<head\b[^>]*>)",
            lambda match: match.group(1) + "\n" + marker,
            text,
            count=1,
            flags=re.I,
        )
    text = replace_alternates(source, surface, text)
    text = replace_schema(source, locale, surface, text)
    text = localize_privacy_links(source, text)
    return text


def extract_required(text: str, pattern: str, label: str) -> str:
    match = re.search(pattern, text, re.I | re.S)
    if not match:
        raise SystemExit(f"template lacks {label}")
    return match.group(0)


def template_text(source: dict) -> str:
    path = ROOT / source["template_surface"]
    if not path.is_file():
        raise SystemExit(f"missing template surface {source['template_surface']}")
    return path.read_text(encoding="utf-8")


def crosspromo_template(source: dict) -> str:
    return extract_required(
        template_text(source),
        r"<!-- ls-family:start -->.*?<!-- ls-family:end -->",
        "cross-promo",
    )


def transform_crosspromo(source: dict, locale: str, block: str) -> str:
    labels = source["generated_crosspromo_labels"].get(locale)
    if not labels:
        raise SystemExit(f"{locale}: missing generated cross-promo labels")
    page_dir = direction(source, locale)

    def section_attrs(match: re.Match[str]) -> str:
        attrs = match.group(1)
        if re.search(r"\bdir=[\"'][^\"']*[\"']", attrs, re.I):
            attrs = re.sub(
                r"\bdir=([\"'])[^\"']*\1",
                f'dir="{page_dir}"',
                attrs,
                count=1,
                flags=re.I,
            )
        else:
            attrs = f' dir="{page_dir}"' + attrs
        escaped = html.escape(labels["title"], quote=True)
        attrs = re.sub(
            r"\baria-label=([\"'])[^\"']*\1",
            f'aria-label="{escaped}"',
            attrs,
            count=1,
            flags=re.I,
        )
        return "<section" + attrs + ">"

    block = re.sub(r"<section\b([^>]*)>", section_attrs, block, count=1, flags=re.I)
    block = re.sub(
        r"(<h2\b[^>]*>).*?(</h2>)",
        lambda match: match.group(1) + html.escape(labels["title"]) + match.group(2),
        block,
        count=1,
        flags=re.I | re.S,
    )

    def card_labels(match: re.Match[str]) -> str:
        return (
            match.group(1)
            + html.escape(labels["purchase"])
            + match.group(2)
            + html.escape(labels["store"])
            + match.group(3)
        )

    block = re.sub(
        r"(<strong\b[^>]*>.*?</strong>\s*<span\b[^>]*>).*?"
        r"(</span>\s*<span\b[^>]*>).*?(</span>)",
        card_labels,
        block,
        flags=re.I | re.S,
    )
    block = re.sub(
        r"(</div>\s*<p\b[^>]*>).*?(</p>\s*<p\b)",
        lambda match: match.group(1)
        + html.escape(labels["opens_store"])
        + match.group(2),
        block,
        count=1,
        flags=re.I | re.S,
    )
    block = re.sub(
        r'(<a\b(?=[^>]*\bhref=["\'][^"\']*ios-app-guide[^"\']*["\'])'
        r"[^>]*>).*?(</a>)",
        lambda match: match.group(1) + html.escape(labels["guides"]) + match.group(2),
        block,
        count=1,
        flags=re.I | re.S,
    )
    if page_dir == "rtl":
        block = block.replace("text-align:left", "text-align:right")
    else:
        block = block.replace("text-align:right", "text-align:left")
    return block


def locale_crosspromo(source: dict, locale: str, surface: str) -> str:
    index_path = route_path(locale, "index")
    if surface != "index" and index_path.is_file():
        return extract_required(
            index_path.read_text(encoding="utf-8"),
            r"<!-- ls-family:start -->.*?<!-- ls-family:end -->",
            "locale cross-promo",
        )
    return transform_crosspromo(source, locale, crosspromo_template(source))


def brand_image(source: dict) -> str:
    brand = extract_required(
        template_text(source),
        r'<a\s+class=["\']brand["\'][^>]*>.*?</a>',
        "brand",
    )
    match = re.search(r"<img\b[^>]*>", brand, re.I)
    return match.group(0) if match else ""


def language_links(source: dict, locale: str, surface: str) -> str:
    rows = []
    for candidate in source["official_locales"]:
        current = ' aria-current="true"' if candidate == locale else ""
        rows.append(
            '<a href="{}" hreflang="{}" lang="{}"{}>{}</a>'.format(
                html.escape(canonical_url(source, candidate, surface), quote=True),
                html.escape(candidate, quote=True),
                html.escape(candidate, quote=True),
                current,
                html.escape(source["locale_names"][candidate]),
            )
        )
    return "".join(rows)


def paragraphs(value: str) -> str:
    parts = [part.strip() for part in value.splitlines() if part.strip()]
    return "".join(f"<p>{html.escape(part)}</p>" for part in parts)


def normalize_description(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def render_generated(
    source: dict, locale: str, surface: str, content: dict
) -> str:
    canonical = canonical_url(source, locale, surface)
    title = normalize_description(content["title"])
    description = normalize_description(content["description"])
    app_name = content.get("app_name") or source["app"]["name"]
    labels = content["labels"]
    style = extract_required(template_text(source), r"<style\b[^>]*>.*?</style>", "style")
    image = brand_image(source)
    app_id = source["app"].get("app_store_id")
    app_url = f"https://apps.apple.com/app/id{app_id}" if app_id else ""
    current = {
        key: (' aria-current="page"' if key == surface else "")
        for key in SURFACES
    }
    nav = (
        f'<a href="index.html"{current["index"]}>{html.escape(labels["home"])}</a>'
        f'<a href="support.html"{current["support"]}>{html.escape(labels["support"])}</a>'
        f'<a href="privacy.html"{current["privacy"]}>{html.escape(labels["privacy"])}</a>'
    )
    help_info = source.get("generated_help_links", {}).get(locale)
    if help_info:
        nav += (
            f'<a href="{html.escape(help_info["href"], quote=True)}">'
            f'{html.escape(help_info["label"])}</a>'
        )
    hero_actions = ""
    if app_url:
        hero_actions += (
            f'<a class="cta" href="{app_url}">{html.escape(labels["app_store"])}</a>'
        )
    secondary_surface = "support" if surface == "index" else "privacy"
    if surface == "privacy":
        secondary_surface = "support"
    hero_actions += (
        f'<a class="cta-quiet" href="{filename(secondary_surface)}">'
        f'{html.escape(labels[secondary_surface])}</a>'
    )
    cards = []
    for index, (heading, body) in enumerate(content.get("sections", [])):
        class_name = "card wide" if index == 0 else "card"
        cards.append(
            f'<section class="{class_name}"><h2>{html.escape(heading)}</h2>'
            f"{paragraphs(body)}</section>"
        )
    cards.append(
        '<section class="card">'
        f'<h2>{html.escape(labels["contact"])}</h2>'
        f"{paragraphs(content['contact'])}"
        f'<p><a href="mailto:{ALLOWED_EMAIL}">{ALLOWED_EMAIL}</a></p>'
        "</section>"
    )
    notice = ""
    if source["app"].get("kids"):
        notice = (
            '<p class="note" data-surface-parent-notice="true">'
            f'{html.escape(source["parent_notice"][locale])}</p>'
        )
    schema = schema_json(source, locale, surface, title, description)
    crosspromo = locale_crosspromo(source, locale, surface)
    footer_links = ""
    if app_url:
        footer_links += (
            f'<a href="{app_url}">{html.escape(labels["app_store"])}</a>'
        )
    footer_links += (
        f'<a href="mailto:{ALLOWED_EMAIL}">{ALLOWED_EMAIL}</a>'
        f"<span>{html.escape(description)}</span>"
    )
    return f"""<!doctype html>
<html lang="{html.escape(locale, quote=True)}" dir="{direction(source, locale)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description, quote=True)}">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{html.escape(canonical, quote=True)}">
{alternate_links(source, surface)}
<meta property="og:type" content="website">
<meta property="og:locale" content="{html.escape(og_locale(locale), quote=True)}">
<meta property="og:title" content="{html.escape(title, quote=True)}">
<meta property="og:description" content="{html.escape(description, quote=True)}">
<meta property="og:url" content="{html.escape(canonical, quote=True)}">
{style}
<!-- surface-contract-generated -->
<!-- surface-contract-schema:start -->
<script type="application/ld+json">{schema}</script>
<!-- surface-contract-schema:end -->
</head>
<body>
<div class="shell">
<header class="site-header">
  <a class="brand" href="index.html">{image}<span>{html.escape(app_name)}</span></a>
  <nav class="primary-nav" aria-label="{html.escape(labels['support'], quote=True)}">{nav}</nav>
  <details class="language"><summary aria-label="{html.escape(labels['language'], quote=True)}">🌐 <span>{html.escape(source['locale_names'][locale])}</span></summary><div class="language-panel">{language_links(source, locale, surface)}</div></details>
</header>
<main>
<section class="page-hero"><p class="eyebrow">{html.escape(content['eyebrow'])}</p><h1><span class="gradient-text">{html.escape(content['heading'])}</span></h1><p class="lead">{html.escape(content['lead'])}</p>{hero_actions}</section>
{notice}
<div class="grid">{''.join(cards)}</div>
<p class="note">{html.escape(description)}</p>
</main>
{crosspromo}
<footer class="site-footer">
  <span>© 2026 {html.escape(app_name)}</span>
  <span class="footer-links">{footer_links}</span>
</footer>
</div>
</body>
</html>
"""


def update_sitemap(source: dict) -> None:
    path = ROOT / "sitemap.xml"
    if not path.is_file():
        raise SystemExit("sitemap.xml missing")
    text = path.read_text(encoding="utf-8")
    text = re.sub(
        r"\s*<!-- surface-contract-routes:start -->.*?"
        r"<!-- surface-contract-routes:end -->\s*",
        "\n",
        text,
        flags=re.I | re.S,
    )
    existing = {
        html.unescape(value.strip())
        for value in re.findall(r"<loc\b[^>]*>(.*?)</loc>", text, re.I | re.S)
        if value.strip()
    }
    required = [
        canonical_url(source, locale, surface)
        for locale in source["official_locales"]
        for surface in SURFACES
    ]
    missing = [url for url in required if url not in existing]
    block = ["<!-- surface-contract-routes:start -->"]
    block.extend(
        f"  <url><loc>{html.escape(url)}</loc></url>" for url in sorted(missing)
    )
    block.append("<!-- surface-contract-routes:end -->")
    rendered = "\n".join(block)
    if not re.search(r"</urlset>", text, re.I):
        raise SystemExit("sitemap.xml lacks closing urlset")
    text = re.sub(r"</urlset>", rendered + "\n</urlset>", text, count=1, flags=re.I)
    write_if_changed(path, text)


def site_digest(source: dict) -> str:
    digest = hashlib.sha256()
    rows = []
    for locale in source["official_locales"]:
        for surface in SURFACES:
            path = route_path(locale, surface)
            rows.append((relative_path(locale, surface), file_sha(path)))
    for path, sha in sorted(rows):
        digest.update(path.encode())
        digest.update(b"\n")
        digest.update(sha.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def write_receipt(source: dict) -> None:
    records = {}
    for locale in source["official_locales"]:
        for surface in SURFACES:
            relative = relative_path(locale, surface)
            records[relative] = file_sha(ROOT / relative)
    receipt = {
        "schema": "support-required-surfaces-build/v2",
        "site": source["site_key"],
        "officialLocaleCount": len(source["official_locales"]),
        "requiredSurfaceCount": len(records),
        "siteDigest": site_digest(source),
        "files": dict(sorted(records.items())),
    }
    write_if_changed(
        RECEIPT_PATH,
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def main() -> None:
    source = read_source()
    preserved = set(source["preserved_surfaces"])
    generated = set(source["generated_surfaces"])
    for locale in source["official_locales"]:
        for surface in SURFACES:
            relative = relative_path(locale, surface)
            path = ROOT / relative
            if relative in preserved:
                rendered = augment_upstream(source, locale, surface)
            elif relative in generated:
                content = source.get("content", {}).get(locale, {}).get(surface)
                if not content:
                    raise SystemExit(f"{relative}: missing localized source")
                rendered = render_generated(source, locale, surface, content)
            else:
                raise SystemExit(f"{relative}: route lacks integration decision")
            write_if_changed(path, rendered)
    update_sitemap(source)
    write_receipt(source)
    print(
        json.dumps(
            {
                "site": source["site_key"],
                "locales": 50,
                "requiredSurfaces": 150,
                "preservedUpstream": len(preserved),
                "generatedNew": len(generated),
                "digest": site_digest(source),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
