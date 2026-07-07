"""
Vitakruid UPDATE-feed
=====================
Lichte feed om bestaande producten bij te werken: titel + verkoopprijs +
beschikbaarheid, per variant (elke maat = eigen SKU/EAN/prijs). Matcht in
Stock Sync op SKU of barcode.

Bewust GEEN beschrijving/Body HTML: die wordt in de shop door de AI-pipeline
(gfy-pd) verzorgd en mag niet door een sync worden overschreven.
Output: vitakruid_feed.xml
"""

import time
import xml.etree.ElementTree as ET
from xml.dom import minidom

import vitakruid_common as vc

OUTPUT_FILE = "vitakruid_feed.xml"


def build_xml(products):
    root = ET.Element("products")
    for p in products:
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
    print("🚀 Vitakruid UPDATE-feed gestart\n")
    start = time.time()
    session = vc.make_session()
    slugs = vc.iter_product_slugs()
    print(f"📦 {len(slugs)} producten te verwerken\n")
    products = list(vc.scrape_products(session, slugs))
    root = build_xml(products)
    save_xml(root, OUTPUT_FILE)
    n = sum(len(p["variants"]) for p in products)
    print(f"⏱️  Klaar in {time.time() - start:.0f}s — {n} varianten in de feed")
    print("\n📋 Feed-URL voor Stock Sync (Update):")
    print("https://raw.githubusercontent.com/Maximillian-creator/vitakruid-feed/main/vitakruid_feed.xml")


if __name__ == "__main__":
    main()
