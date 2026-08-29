#!/usr/bin/env python3
"""Build exact-50 localized support-site surfaces from a local source contract."""

from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATH = ROOT / "surface_source.json"
BUILD_RECEIPT = ROOT / "surface-build.json"
GENERATED_CSS = ROOT / "surface-generated.css"


def read_source() -> dict:
    source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    if source.get("schema") != "support-required-surfaces/v1":
        raise SystemExit("surface_source.json has an unsupported schema")
    locales = source.get("official_locales", [])
    if len(locales) != 50 or len(set(locales)) != 50:
        raise SystemExit("surface_source.json must declare 50 unique locales")
    if set(source.get("locale_names", {})) != set(locales):
        raise SystemExit("locale_names must exactly match official_locales")
    return source


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def direction(locale: str, source: dict) -> str:
    return "rtl" if locale in set(source["rtl_locales"]) else "ltr"


def route_path(locale: str, surface: str) -> Path:
    name = "index.html" if surface == "index" else f"{surface}.html"
    return ROOT / locale / name


def canonical_url(source: dict, locale: str, surface: str) -> str:
    base = source["base_url"].rstrip("/") + "/"
    suffix = "" if surface == "index" else f"{surface}.html"
    return f"{base}{locale}/{suffix}"


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
    parts = locale.replace("-", "_").split("_", 1)
    return parts[0] if len(parts) == 1 else f"{parts[0]}_{parts[1].upper()}"


def alternates(source: dict, surface: str) -> str:
    rows = []
    for locale in source["official_locales"]:
        rows.append(
            '<link rel="alternate" hreflang="{}" href="{}">'.format(
                html.escape(locale, quote=True),
                html.escape(canonical_url(source, locale, surface), quote=True),
            )
        )
    rows.append(
        '<link rel="alternate" hreflang="x-default" href="{}">'.format(
            html.escape(canonical_url(source, "en-US", surface), quote=True)
        )
    )
    return "\n".join(rows)


def normalize_description(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= 180:
        return value
    prefix = value[:180]
    cut = max(prefix.rfind(mark) + 1 for mark in ".!?。！？")
    if cut < 100:
        cut = prefix.rfind(" ")
    if cut < 100:
        cut = 180
    return prefix[:cut].rstrip(" ,;:，；：")


def schema_payload(
    source: dict, locale: str, surface: str, content: dict, canonical: str
) -> dict:
    questions = [
        (heading, body)
        for heading, body in content.get("sections", [])
        if any(mark in heading for mark in ("?", "؟", "？"))
    ]
    payload: dict = {
        "@context": "https://schema.org",
        "@type": "FAQPage" if surface == "support" and questions else "WebPage",
        "name": content["title"],
        "description": content["description"],
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
    if surface == "support" and questions:
        payload["mainEntity"] = [
            {
                "@type": "Question",
                "name": heading,
                "acceptedAnswer": {"@type": "Answer", "text": body},
            }
            for heading, body in questions
        ]
    return payload


def language_links(source: dict, surface: str, current: str) -> str:
    links = []
    for locale in source["official_locales"]:
        current_attr = ' aria-current="page"' if locale == current else ""
        links.append(
            '<a hreflang="{}" lang="{}" href="{}"{}>{}</a>'.format(
                html.escape(locale, quote=True),
                html.escape(locale, quote=True),
                html.escape(canonical_url(source, locale, surface), quote=True),
                current_attr,
                html.escape(source["locale_names"][locale]),
            )
        )
    return "\n".join(links)


def render_generated_page(
    source: dict, locale: str, surface: str, content: dict
) -> str:
    canonical = canonical_url(source, locale, surface)
    title = normalize_description(content["title"])
    description = normalize_description(content["description"])
    app_name = content.get("app_name") or source["app"]["name"]
    home_label = content["labels"]["home"]
    support_label = content["labels"]["support"]
    privacy_label = content["labels"]["privacy"]
    contact_label = content["labels"]["contact"]
    locale_label = content["labels"]["language"]
    nav = (
        f'<a href="{html.escape(canonical_url(source, locale, "index"), quote=True)}">'
        f"{html.escape(home_label)}</a>"
        f'<a href="{html.escape(canonical_url(source, locale, "support"), quote=True)}">'
        f"{html.escape(support_label)}</a>"
        f'<a href="{html.escape(canonical_url(source, locale, "privacy"), quote=True)}">'
        f"{html.escape(privacy_label)}</a>"
    )
    notice = ""
    if source["app"].get("kids"):
        notice_text = source["parent_notice"][locale]
        notice = (
            '<aside class="surface-notice" data-surface-parent-notice="true">'
            f"{html.escape(notice_text)}</aside>"
        )
    sections = []
    for heading, body in content.get("sections", []):
        sections.append(
            "<section class=\"surface-card\">"
            f"<h2>{html.escape(heading)}</h2>"
            f"<p>{html.escape(body)}</p>"
            "</section>"
        )
    app_cta = ""
    app_id = source["app"].get("app_store_id")
    if app_id:
        app_cta = (
            '<a class="surface-button" data-surface-own-app="true" '
            f'href="https://apps.apple.com/app/id{app_id}" rel="noopener">'
            f'{html.escape(content["labels"]["app_store"])}</a>'
        )
    email_subject = quote(f'{source["app"]["name"]} support')
    contact = (
        '<section class="surface-card surface-contact">'
        f"<h2>{html.escape(contact_label)}</h2>"
        f"<p>{html.escape(content['contact'])}</p>"
        f'<a class="surface-mail" href="mailto:hourstag.app@gmail.com?subject={email_subject}">'
        "hourstag.app@gmail.com</a>"
        f"{app_cta}</section>"
    )
    schema_content = dict(content)
    schema_content["description"] = description
    schema = json.dumps(
        schema_payload(source, locale, surface, schema_content, canonical),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="{html.escape(locale, quote=True)}" dir="{direction(locale, source)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description, quote=True)}">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{html.escape(canonical, quote=True)}">
{alternates(source, surface)}
<meta property="og:type" content="website">
<meta property="og:locale" content="{html.escape(og_locale(locale), quote=True)}">
<meta property="og:title" content="{html.escape(title, quote=True)}">
<meta property="og:description" content="{html.escape(description, quote=True)}">
<meta property="og:url" content="{html.escape(canonical, quote=True)}">
<link rel="stylesheet" href="../surface-generated.css">
<script type="application/ld+json">{schema}</script>
</head>
<body>
<header class="surface-header">
  <a class="surface-brand" href="{html.escape(canonical_url(source, locale, 'index'), quote=True)}">{html.escape(app_name)}</a>
  <nav aria-label="Primary">{nav}</nav>
</header>
<main>
  {notice}
  <section class="surface-hero">
    <p class="surface-eyebrow">{html.escape(content["eyebrow"])}</p>
    <h1>{html.escape(content["heading"])}</h1>
    <p>{html.escape(content["lead"])}</p>
  </section>
  {"".join(sections)}
  {contact}
</main>
<details class="surface-languages">
  <summary>{html.escape(locale_label)} · {html.escape(source["locale_names"][locale])}</summary>
  <nav aria-label="{html.escape(locale_label, quote=True)}">
    {language_links(source, surface, locale)}
  </nav>
</details>
<footer>© 2026 Lumi Studio · {html.escape(app_name)}</footer>
</body>
</html>
"""


def managed_schema(source: dict, locale: str, surface: str, canonical: str) -> str:
    title_match = re.search(
        r"<title\b[^>]*>(.*?)</title>",
        route_path(locale, surface).read_text(encoding="utf-8"),
        re.I | re.S,
    )
    title = (
        re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
        if title_match
        else source["app"]["name"]
    )
    payload = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": title,
        "inLanguage": locale,
        "url": canonical,
    }
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).replace("</", "<\\/")


def normalize_head(source: dict, locale: str, surface: str, text: str) -> str:
    canonical = canonical_url(source, locale, surface)
    text = re.sub(
        r"<html\b[^>]*>",
        f'<html lang="{html.escape(locale, quote=True)}" dir="{direction(locale, source)}">',
        text,
        count=1,
        flags=re.I,
    )
    if not re.search(r"<meta\s+charset=", text, re.I):
        text = re.sub(
            r"<head\b[^>]*>",
            lambda m: m.group(0) + '\n<meta charset="utf-8">',
            text,
            count=1,
            flags=re.I,
        )
    text = re.sub(
        r"\s*<link\b(?=[^>]*\brel=[\"']alternate[\"'])[^>]*>\s*",
        "\n",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\s*<link\b(?=[^>]*\brel=[\"']canonical[\"'])[^>]*>\s*",
        "\n",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\s*<meta\b(?=[^>]*\bproperty=[\"']og:url[\"'])[^>]*>\s*",
        "\n",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\s*<meta\b(?=[^>]*\bproperty=[\"']og:locale[\"'])[^>]*>\s*",
        "\n",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\s*<!-- surface-contract-schema:start -->.*?<!-- surface-contract-schema:end -->\s*",
        "\n",
        text,
        flags=re.I | re.S,
    )
    injection = (
        f'\n<link rel="canonical" href="{html.escape(canonical, quote=True)}">\n'
        f"{alternates(source, surface)}\n"
        f'<meta property="og:locale" content="{html.escape(og_locale(locale), quote=True)}">\n'
        f'<meta property="og:url" content="{html.escape(canonical, quote=True)}">\n'
        "<!-- surface-contract-schema:start -->\n"
        '<script type="application/ld+json">'
        f"{managed_schema_from_text(source, locale, canonical, text)}"
        "</script>\n"
        "<!-- surface-contract-schema:end -->\n"
    )
    text = re.sub(r"</head>", injection + "</head>", text, count=1, flags=re.I)
    text = re.sub(
        r'(<div\s+class=["\']language-panel["\'][^>]*>).*?(</div>)',
        lambda match: (
            match.group(1)
            + language_links(source, surface, locale)
            + match.group(2)
        ),
        text,
        count=1,
        flags=re.I | re.S,
    )
    return text


def managed_schema_from_text(
    source: dict, locale: str, canonical: str, text: str
) -> str:
    match = re.search(r"<title\b[^>]*>(.*?)</title>", text, re.I | re.S)
    title = (
        html.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()
        if match
        else source["app"]["name"]
    )
    payload = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": title,
        "inLanguage": locale,
        "url": canonical,
    }
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).replace("</", "<\\/")


def inject_parent_notice(source: dict, locale: str, text: str) -> str:
    if not source["app"].get("kids"):
        return text
    text = re.sub(
        r"\s*<!-- surface-parent-notice:start -->.*?<!-- surface-parent-notice:end -->\s*",
        "\n",
        text,
        flags=re.S,
    )
    notice = (
        "\n<!-- surface-parent-notice:start -->"
        '<aside data-surface-parent-notice="true" '
        'style="max-width:1060px;margin:16px auto;padding:12px 16px;'
        'border:1px solid currentColor;border-radius:14px;opacity:.88">'
        f"{html.escape(source['parent_notice'][locale])}</aside>"
        "<!-- surface-parent-notice:end -->\n"
    )
    return re.sub(r"<body\b[^>]*>", lambda m: m.group(0) + notice, text, count=1, flags=re.I)


def patch_hourstag_faq(source: dict, locale: str, text: str) -> str:
    if source["site_key"] != "hourstag-support":
        return text
    if 'data-surface-paid-contract="true"' in text:
        return re.sub(
            r'(<details\s+class=["\']faq["\'][^>]*'
            r'data-surface-paid-contract=["\']true["\'][^>]*>.*?'
            r"<summary\b[^>]*>.*?</summary>\s*<p\b[^>]*>).*?(</p>\s*</details>)",
            lambda match: (
                match.group(1)
                + html.escape(source["hourstag_paid"][locale]["answer"])
                + match.group(2)
            ),
            text,
            count=1,
            flags=re.I | re.S,
        )
    blocks = list(
        re.finditer(
            r'<details\s+class=["\']faq["\'][^>]*>.*?</details>',
            text,
            re.I | re.S,
        )
    )
    if len(blocks) < 7:
        return text
    first, last = blocks[0].start(), blocks[-1].end()
    raw_blocks = [match.group(0) for match in blocks]
    question_match = re.search(
        r"<summary\b[^>]*>(.*?)</summary>", raw_blocks[3], re.I | re.S
    )
    question = (
        question_match.group(1)
        if question_match
        else html.escape(source["hourstag_paid"][locale]["question"])
    )
    corrected = (
        '<details class="faq" data-surface-paid-contract="true">'
        f"<summary>{question}</summary>"
        f"<p>{html.escape(source['hourstag_paid'][locale]['answer'])}</p>"
        "</details>"
    )
    kept = raw_blocks[:3] + [corrected] + raw_blocks[6:]
    return text[:first] + "".join(kept) + text[last:]


def infer_help_locale(path: Path) -> str:
    if path.name == "help.html":
        return "en-US"
    match = re.fullmatch(r"help\.([^.]+(?:-[^.]+)?)\.html", path.name)
    return match.group(1) if match else "en-US"


def patch_hourstag_help(source: dict, locale: str, text: str) -> str:
    if source["site_key"] != "hourstag-support":
        return text
    paid = source["hourstag_paid"][locale]["answer"]
    already_managed = 'data-surface-paid-contract="true"' in text
    pair_pattern = re.compile(
        r'(<p\s+class=["\']hd-q["\'][^>]*>.*?</p>)\s*'
        r'(<p\s+class=["\']hd-a["\'][^>]*>.*?</p>)',
        re.I | re.S,
    )
    pairs = list(pair_pattern.finditer(text))
    if len(pairs) >= 5:
        if already_managed:
            text = re.sub(
                r'(<p\s+class=["\']hd-a["\'][^>]*'
                r'data-surface-paid-contract=["\']true["\'][^>]*>).*?(</p>)',
                lambda match: match.group(1) + html.escape(paid) + match.group(2),
                text,
                count=1,
                flags=re.I | re.S,
            )
        else:
            first, last = pairs[0].start(), pairs[-1].end()
            raw_pairs = [match.group(0) for match in pairs]
            paid_pair = re.sub(
                r'<p\s+class=["\']hd-a["\'][^>]*>.*?</p>',
                (
                    '<p class="hd-a" data-surface-paid-contract="true">'
                    f"{html.escape(paid)}</p>"
                ),
                raw_pairs[1],
                count=1,
                flags=re.I | re.S,
            )
            kept = raw_pairs[:1] + [paid_pair] + raw_pairs[2:3] + raw_pairs[4:]
            text = text[:first] + "".join(kept) + text[last:]

    def update_schema(match: re.Match[str]) -> str:
        raw = match.group(2)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return match.group(0)
        if not isinstance(payload, dict) or payload.get("@type") != "FAQPage":
            return match.group(0)
        entities = payload.get("mainEntity")
        if not isinstance(entities, list) or len(entities) < 2:
            return match.group(0)
        answer = entities[1].get("acceptedAnswer")
        if isinstance(answer, dict):
            answer["text"] = paid
        if not already_managed and len(entities) >= 4:
            del entities[3]
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return match.group(1) + encoded.replace("</", "<\\/") + match.group(3)

    text = re.sub(
        r'(<script\s+type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)',
        update_schema,
        text,
        flags=re.I | re.S,
    )
    section_match = re.search(
        r'(<section\s+id=["\']troubleshooting["\'][^>]*>)(.*?)(</section>)',
        text,
        re.I | re.S,
    )
    if section_match:
        body = section_match.group(2)
        rows = list(
            re.finditer(r"(<h3\b[^>]*>.*?</h3>)\s*(<p\b[^>]*>.*?</p>)", body, re.I | re.S)
        )
        if rows:
            last = rows[-1]
            replacement = (
                last.group(1)
                + '<p data-surface-paid-reinstall="true">'
                + html.escape(paid)
                + "</p>"
            )
            body = body[: last.start()] + replacement + body[last.end() :]
            text = (
                text[: section_match.start()]
                + section_match.group(1)
                + body
                + section_match.group(3)
                + text[section_match.end() :]
            )
    return text


def write_css(source: dict) -> None:
    accent = source["palette"]["accent"]
    accent2 = source["palette"]["accent2"]
    GENERATED_CSS.write_text(
        f"""*{{box-sizing:border-box}}html{{color-scheme:light dark}}body{{margin:0;min-height:100vh;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",sans-serif;line-height:1.65;color:#272334;background:radial-gradient(circle at 12% 0,{accent}24,transparent 34rem),radial-gradient(circle at 90% 8%,{accent2}20,transparent 32rem),#faf9fd}}a{{color:{accent}}}.surface-header,.surface-header nav,.surface-contact,.surface-languages nav{{display:flex;align-items:center;gap:12px;flex-wrap:wrap}}.surface-header{{max-width:1040px;margin:auto;padding:22px 20px;justify-content:space-between}}.surface-brand{{font-size:1.05rem;font-weight:750;text-decoration:none;color:inherit}}.surface-header nav a{{padding:8px 10px;text-decoration:none}}main,.surface-languages,footer{{width:min(920px,calc(100% - 32px));margin:auto}}.surface-notice{{margin:4px 0 16px;padding:12px 16px;border:1px solid {accent}55;border-radius:15px;background:{accent}12}}.surface-hero{{padding:44px 0 24px}}.surface-eyebrow{{font-size:.8rem;letter-spacing:.08em;text-transform:uppercase;color:{accent};font-weight:700}}h1{{font-size:clamp(2rem,7vw,4.2rem);line-height:1.05;letter-spacing:-.035em;margin:.25em 0}}h2{{font-size:1.2rem;margin-top:0}}.surface-card{{padding:22px;margin:14px 0;border:1px solid {accent}30;border-radius:22px;background:rgba(255,255,255,.78);box-shadow:0 20px 60px {accent}12}}.surface-contact{{align-items:flex-start;flex-direction:column}}.surface-mail,.surface-button{{display:inline-flex;min-height:44px;align-items:center;padding:10px 16px;border-radius:14px;text-decoration:none;font-weight:700}}.surface-mail{{border:1px solid {accent}55}}.surface-button{{color:white;background:linear-gradient(135deg,{accent},{accent2})}}.surface-languages{{margin-top:28px;padding:16px;border:1px solid {accent}30;border-radius:18px}}.surface-languages summary{{cursor:pointer;font-weight:700}}.surface-languages nav{{padding-top:12px;align-items:stretch}}.surface-languages nav a{{padding:7px 10px;border-radius:9px;text-decoration:none;background:{accent}0d}}footer{{padding:30px 0 44px;opacity:.65}}[dir=rtl] .surface-header,[dir=rtl] .surface-contact{{text-align:right}}@media(prefers-color-scheme:dark){{body{{color:#f5f0ff;background:radial-gradient(circle at 12% 0,{accent}38,transparent 34rem),radial-gradient(circle at 90% 8%,{accent2}28,transparent 32rem),#100d17}}.surface-card{{background:rgba(28,23,39,.86)}}}}""",
        encoding="utf-8",
    )


def update_sitemap(source: dict) -> None:
    path = ROOT / "sitemap.xml"
    urls: set[str] = set()
    if path.exists():
        urls.update(
            html.unescape(value.strip())
            for value in re.findall(
                r"<loc\b[^>]*>(.*?)</loc>",
                path.read_text(encoding="utf-8", errors="replace"),
                re.I | re.S,
            )
            if value.strip()
        )
    for locale in source["official_locales"]:
        for surface in ("index", "support", "privacy"):
            urls.add(canonical_url(source, locale, surface))
    body = "\n".join(
        f"  <url><loc>{html.escape(url)}</loc></url>" for url in sorted(urls)
    )
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n</urlset>\n",
        encoding="utf-8",
    )


def main() -> None:
    source = read_source()
    write_css(source)
    outputs: list[Path] = []
    content = source.get("content", {})
    for locale in source["official_locales"]:
        locale_content = content.get(locale, {})
        for surface in ("index", "support", "privacy"):
            path = route_path(locale, surface)
            if surface in locale_content:
                path.parent.mkdir(parents=True, exist_ok=True)
                text = render_generated_page(
                    source, locale, surface, locale_content[surface]
                )
            elif path.exists():
                text = path.read_text(encoding="utf-8")
                text = normalize_head(source, locale, surface, text)
                text = inject_parent_notice(source, locale, text)
                if surface == "support":
                    text = patch_hourstag_faq(source, locale, text)
            else:
                raise SystemExit(f"missing source for {locale}/{surface}")
            path.write_text(text, encoding="utf-8")
            outputs.append(path)

    for help_path in sorted(ROOT.glob("help*.html")):
        locale = (
            "zh-Hant"
            if source["site_key"] == "hourstag-support"
            and help_path.name == "help.html"
            else infer_help_locale(help_path)
        )
        if locale not in source["official_locales"]:
            continue
        text = help_path.read_text(encoding="utf-8")
        text = inject_parent_notice(source, locale, text)
        text = patch_hourstag_faq(source, locale, text)
        text = patch_hourstag_help(source, locale, text)
        help_path.write_text(text, encoding="utf-8")
        outputs.append(help_path)

    update_sitemap(source)
    outputs.extend((GENERATED_CSS, ROOT / "sitemap.xml"))
    records = {
        str(path.relative_to(ROOT)): file_sha(path)
        for path in sorted(outputs, key=lambda item: str(item.relative_to(ROOT)))
    }
    digest = hashlib.sha256(
        json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    receipt = {
        "schema": "support-required-surfaces-build/v1",
        "site": source["site_key"],
        "officialLocaleCount": 50,
        "requiredSurfaceCount": 150,
        "contentDigest": digest,
        "files": records,
    }
    BUILD_RECEIPT.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"PASS {source['site_key']} {digest}")


if __name__ == "__main__":
    main()
