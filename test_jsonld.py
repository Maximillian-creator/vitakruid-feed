"""
Pint vast dat parse_base de productgegevens uit beide JSON-LD-vormen van vitakruid.nl haalt.

Aanleiding: sinds ~02-11-2026 zet vitakruid.nl de JSON-LD in één `@graph` en verwijst het
merk met een `@id`. De scraper vond het Product niet meer, sloeg alle 205 producten over en
de rem hield de feed vier dagen vast (Nebula: "vitakruid: 27 u niet vers", 03-11).

Draaien: python test_jsonld.py
"""

import unittest

import vitakruid_common as vc

SELECT = """
<select id="variantSubstanceSelect">
  <option value="90988" data-subscription="false" selected>60 vegan capsules</option>
  <option value="90988-s" data-subscription="true">60 vegan capsules (herhaalgemak)</option>
  <option value="92753" data-subscription="false">90 vegan capsules</option>
</select>
"""

# Ingekort uit https://www.vitakruid.nl/products/5-htp-100mg, opgehaald 05-11-2026
GRAPH_HTML = """
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[
 {"@type":["Product","DietarySupplement"],"@id":"https://www.vitakruid.nl/products/5-htp-100mg#product",
  "name":"5-HTP 100mg","sku":"90988","gtin13":"8717438690988",
  "brand":{"@id":"https://www.vitakruid.nl/#brand"},
  "manufacturer":{"@id":"https://www.vitakruid.nl/#organization"},
  "offers":{"@id":"https://www.vitakruid.nl/products/5-htp-100mg#offers"},
  "image":"https://www.vitakruid.nl/media/x.png",
  "activeIngredient":["Griffonia simplicifolia-extract (30% 5-HTP)","5-HTP"],
  "dosageForm":"Vegan capsules"},
 {"@type":"AggregateOffer","@id":"https://www.vitakruid.nl/products/5-htp-100mg#offers","lowPrice":"24.9"},
 {"@type":"OnlineStore","@id":"https://www.vitakruid.nl/#organization","name":"Vitakruid"},
 {"@type":"Brand","@id":"https://www.vitakruid.nl/#brand","name":"Vitakruid"}
]}</script>
""" + SELECT

OUD_HTML = """
<script type="application/ld+json">{"@type":"Product","name":"5-HTP 100mg","brand":{"name":"Vitakruid"},
"sku":"90988","gtin13":"8717438690988","dosageForm":"Vegan capsules"}</script>
""" + SELECT


class TestJsonLd(unittest.TestCase):
    def test_graph_vorm_van_november_2026(self):
        b = vc.parse_base(GRAPH_HTML)
        self.assertEqual(b["title"], "5-HTP 100mg")
        self.assertEqual(b["brand"], "Vitakruid")              # via de @id-verwijzing
        self.assertEqual(b["base_sku"], "90988")
        self.assertEqual(b["base_ean"], "8717438690988")
        self.assertEqual(b["dosage_form"], "Vegan capsules")
        self.assertEqual(b["active_ingredient"], "Griffonia simplicifolia-extract (30% 5-HTP), 5-HTP")
        self.assertEqual(b["images"], ["https://www.vitakruid.nl/media/x.png"])
        # abonnement (-s) blijft eruit
        self.assertEqual(b["variant_options"], [("90988", "60 vegan capsules"), ("92753", "90 vegan capsules")])

    def test_oude_vorm_blijft_werken(self):
        b = vc.parse_base(OUD_HTML)
        self.assertEqual((b["title"], b["brand"], b["base_sku"]), ("5-HTP 100mg", "Vitakruid", "90988"))

    def test_merk_dat_niet_te_vinden_is_valt_terug_op_vitakruid(self):
        html = GRAPH_HTML.replace('"name":"Vitakruid"}\n]', '"x":1}\n]')
        self.assertEqual(vc.parse_base(html)["brand"], "Vitakruid")

    def test_geen_product_is_leeg_en_dus_overgeslagen(self):
        html = '<script type="application/ld+json">{"@graph":[{"@type":"WebPage","name":"x"}]}</script>'
        self.assertEqual(vc.parse_base(html)["title"], "")


if __name__ == "__main__":
    unittest.main()
