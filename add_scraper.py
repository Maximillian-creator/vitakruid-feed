"""
Vitakruid ADD-feed
==================
Volledige productinfo om met Stock Sync NIEUWE producten aan te maken, per variant
(elke maat = eigen SKU/EAN/prijs). Verkoopprijs = Vitakruid's retail (incl. BTW).
Kostprijs (inkoop) staat niet publiek → leeg.
Output: vitakruid_add_feed.xml
"""

import time
import xml.etree.ElementTree as ET
from xml.dom import minidom
from html import escape

import vitakruid_common as vc

OUTPUT_FILE = "vitakruid_add_feed.xml"


def build_description_html(p, v):
    """
    Rijke beschrijving (al HTML) + samenstelling MÉT doseringen/%RI (per variant,
    valt terug op de kale namen) + inname-dosering + doseervorm.
    """
    parts = []
    if p.get("description_html"):
        parts.append(p["description_html"])
    samenstelling = v.get("samenstelling") or p.get("active_ingredient")
    if samenstelling:
        parts.append(f"<p><strong>Samenstelling:</strong> {escape(samenstelling)}</p>")
    if v.get("dosering"):
        parts.append(f"<p><strong>Dosering:</strong> {escape(v['dosering'])}</p>")
    if p.get("dosage_form"):
        parts.append(f"<p><strong>Doseervorm:</strong> {escape(p['dosage_form'])}</p>")
    return "\n".join(parts)


def build_xml(products):
    root = ET.Element("products")
    for p in products:
        # afbeeldingen: product-afbeeldingen gedeeld over de varianten
        base_images = p.get("images", [])
        for v in p["variants"]:
            item = ET.SubElement(root, "product")

            def add(tag, value):
                el = ET.SubElement(item, tag)
                el.text = "" if value is None else str(value)

            add("handle", p["slug"])
            add("title", p["title"])
            add("vendor", p["brand"])
            add("sku", v["sku"])
            add("barcode", v["ean"])
            add("price", f"{v['price']:.2f}")     # retail incl. BTW
            add("available", "true")
            add("quantity", "")
            add("option1_name", "Inhoud")
            add("option1", v.get("label", ""))
            add("zindex", v.get("zindex", ""))
            add("description", build_description_html(p, v))
            add("samenstelling", v.get("samenstelling") or p.get("active_ingredient", ""))
            add("dosering", v.get("dosering", ""))
            add("dosage_form", p.get("dosage_form", ""))

            # afbeeldingen: variant-afbeelding eerst, dan de productfoto's
            imgs = []
            if v.get("image"):
                imgs.append(v["image"])
            for u in base_images:
                if u not in imgs:
                    imgs.append(u)
            images_el = ET.SubElement(item, "images")
            for u in imgs:
                img = ET.SubElement(images_el, "image")
                src = ET.SubElement(img, "src")
                src.text = u
            add("image_links", ",".join(imgs))
    return root


def save_xml(root, filepath):
    xml_str = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(xml_str).toprettyxml(indent="  ")
    lines = pretty.split("\n")
    if lines[0].startswith("<?xml"):
        lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n💾 XML opgeslagen: {filepath}")


def main():
    print("🚀 Vitakruid ADD-feed gestart\n")
    start = time.time()
    session = vc.make_session()
    slugs = vc.iter_product_slugs()
    print(f"📦 {len(slugs)} producten te verwerken\n")
    products = list(vc.scrape_products(session, slugs))
    root = build_xml(products)
    save_xml(root, OUTPUT_FILE)
    n = sum(len(p["variants"]) for p in products)
    print(f"⏱️  Klaar in {time.time() - start:.0f}s — {n} varianten in de feed")
    print("\n📋 Feed-URL voor Stock Sync (Add products):")
    print("https://raw.githubusercontent.com/Maximillian-creator/vitakruid-feed/main/vitakruid_add_feed.xml")


if __name__ == "__main__":
    main()
