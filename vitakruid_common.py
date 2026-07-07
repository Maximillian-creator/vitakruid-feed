"""
Vitakruid — gedeelde scraper-kern
=================================
Bron: vitakruid.nl (Symfony-shop, geen products.json). Openbaar, geen login.

Per product:
  - Basis-pagina (`/products/{slug}`): JSON-LD (naam, merk, actieve stof, doseervorm,
    afbeeldingen) + rijke beschrijving (`.prose--pdp`) + variant-opties (`<select>`).
  - Per variant: `/get-variant-b2c/{code}` → JSON met HTML-templates waaruit we
    SKU, EAN, Z-index, prijs en afbeelding halen. Elke maat heeft een eigen EAN + prijs.

Prijs = Vitakruid's eigen **retail** (incl. BTW), 1-op-1 als verkoopprijs.
Kostprijs (inkoop) staat niet publiek → leeg gelaten.

Lokaal achter een SSL-onderscheppende proxy: zet INSECURE_SSL=1.
"""

import os
import re
import json
import time
from html import unescape

import requests

BASE = "https://www.vitakruid.nl"
REQUEST_DELAY = 0.5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GoodForYouFeedBot/1.0; +https://goodforyouonline.nl)",
    "Accept-Language": "nl-NL,nl;q=0.9",
}

VERIFY_SSL = os.environ.get("INSECURE_SSL") != "1"
if not VERIFY_SSL:
    import urllib3
    urllib3.disable_warnings()


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def make_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    s.verify = VERIFY_SSL
    return s


def fetch(session, url, retries=3, allow_404=False, ajax=False):
    hdr = {"X-Requested-With": "XMLHttpRequest"} if ajax else {}
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=20, headers=hdr)
            if r.status_code == 404 and allow_404:
                return None
            r.raise_for_status()
            return r
        except Exception as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status == 404 and allow_404:
                return None
            if attempt < retries - 1:
                time.sleep((attempt + 1) * 15)
            else:
                print(f"    ❌ Mislukt: {url} ({e})")
                return None


# --------------------------------------------------------------------------- #
# Enumeratie via sitemap
# --------------------------------------------------------------------------- #
def iter_product_slugs():
    session = make_session()
    r = fetch(session, f"{BASE}/sitemap.xml")
    if not r:
        return []
    slugs = []
    seen = set()
    for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text):
        m = re.match(rf"{re.escape(BASE)}/products/([^/?#]+)/?$", loc.strip())
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            slugs.append(m.group(1))
    return slugs


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def clean_text(fragment):
    if not fragment:
        return ""
    t = re.sub(r"<[^>]+>", " ", fragment)
    t = unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def _product_ld(html):
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.DOTALL):
        try:
            j = json.loads(block.strip())
        except Exception:
            continue
        types = j.get("@type") if isinstance(j, dict) else None
        types = types if isinstance(types, list) else [types]
        if isinstance(j, dict) and "Product" in types:
            return j
    return None


def _description_html(html):
    """Rijke beschrijving uit het .prose--pdp-blok (whitelist basis-tags)."""
    m = re.search(r'<div class="prose prose--pdp">(.*?)</div>\s*(?:</div>|<div class="(?!prose))', html, re.DOTALL)
    if not m:
        m = re.search(r'prose--pdp">(.*?)</div>', html, re.DOTALL)
    if not m:
        return ""
    b = m.group(1)
    b = re.sub(r'<(script|style|svg|button)[^>]*>.*?</\1>', "", b, flags=re.DOTALL | re.I)
    b = re.sub(r"<img[^>]*>", "", b, flags=re.I)
    keep = {"p", "ul", "ol", "li", "strong", "b", "em", "h2", "h3", "h4", "br"}

    def _tag(mo):
        slash = "/" if mo.group(1) else ""
        tag = mo.group(2).lower()
        return f"<{slash}{tag}>" if tag in keep else ""

    b = re.sub(r"<(/?)(\w+)[^>]*>", _tag, b)
    b = b.replace("&nbsp;", " ")
    b = re.sub(r"[ \t]+", " ", b)
    b = re.sub(r"\s*\n\s*", "", b)
    b = re.sub(r"<p>\s*</p>", "", b)
    return b.strip()


def parse_base(html):
    """Productinfo die voor alle varianten gedeeld is."""
    ld = _product_ld(html) or {}
    brand = ld.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    active = ld.get("activeIngredient")
    if isinstance(active, list):
        active = ", ".join(str(a) for a in active)

    images = ld.get("image")
    if isinstance(images, str):
        images = [images]
    images = [i for i in (images or []) if isinstance(i, str)]

    # Variant-opties uit de <select> (code + label)
    opts = []
    sel = re.search(r'variantSubstanceSelect".*?</select>', html, re.DOTALL)
    if sel:
        # value="9059" = echte maat; value="9059-s" = abonnement (herhaalgemak) → overslaan
        for code, label in re.findall(
            r'<option[^>]*value="([0-9]+)"[^>]*>\s*([^<]*?)\s*</option>', sel.group(0), re.DOTALL
        ):
            opts.append((code, clean_text(label)))

    return {
        "title": ld.get("name") or "",
        "brand": brand or "Vitakruid",
        "description_html": _description_html(html),
        "active_ingredient": clean_text(active or ""),
        "dosage_form": ld.get("dosageForm") or "",
        "images": images,
        "variant_options": opts,       # [(code, label)]
        "base_sku": ld.get("sku") or "",
        "base_ean": ld.get("gtin13") or "",
    }


def parse_variant(session, code):
    """Per variant: SKU, EAN, Z-index, prijs (retail incl. BTW), afbeelding."""
    r = fetch(session, f"{BASE}/get-variant-b2c/{code}", allow_404=True, ajax=True)
    if not r:
        return None
    try:
        j = r.json()
    except Exception:
        return None
    nums = clean_text(j.get("numbers_string_template", ""))
    sku = (re.search(r"Artikelnr\.?\s*:\s*([0-9A-Za-z]+)", nums) or [None, code])[1]
    ean = (re.search(r"EAN\s*:\s*(\d{12,14})", nums) or [None, ""])[1]
    zindex = (re.search(r"Z-?index\s*:\s*(\d+)", nums) or [None, ""])[1]
    price_html = j.get("variant_price_template") or j.get("prices_template") or ""
    pm = re.search(r"€\s*([\d.]+,\d{2})", clean_text(price_html))
    price = float(pm.group(1).replace(".", "").replace(",", ".")) if pm else None
    img = (re.search(r'src="([^"]+)"', j.get("figure_template") or "") or [None, ""])[1]
    # Volledige samenstelling MÉT doseringen/%RI + inname-instructies (per variant)
    samenstelling = clean_text(j.get("variant_ingredient_table_template", ""))
    dosering = clean_text(j.get("variant_dosage_table_template", ""))
    return {
        "code": code, "sku": sku, "ean": ean, "zindex": zindex, "price": price,
        "image": img, "samenstelling": samenstelling, "dosering": dosering,
    }


def scrape_products(session, slugs):
    """Yield per product: gedeelde info + lijst varianten (elk met eigen EAN/prijs)."""
    total = len(slugs)
    skipped = 0
    for i, slug in enumerate(slugs, 1):
        r = fetch(session, f"{BASE}/products/{slug}", allow_404=True)
        if not r:
            continue
        base = parse_base(r.text)
        if not base["title"]:
            skipped += 1
            continue

        options = base["variant_options"] or [(base["base_sku"], "")]
        variants = []
        for code, label in options:
            v = parse_variant(session, code)
            if v and v["price"] is not None:
                v["label"] = label
                variants.append(v)
            time.sleep(REQUEST_DELAY)
        if not variants:
            skipped += 1
            continue

        print(f"  [{i}/{total}] {base['title'][:48]:48} {len(variants)} variant(en)")
        yield {**base, "slug": slug, "variants": variants}
        time.sleep(REQUEST_DELAY)

    print(f"\nℹ️  Overgeslagen: {skipped} (geen product/prijs).")
