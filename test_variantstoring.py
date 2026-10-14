"""
Pint vast wat scrape_products doet als Vitakruid's variant-endpoint een storing geeft.

Aanleiding: sinds 08-10-2026 geeft vitakruid.nl HTTP 500 op /get-variant-b2c/91367
(Magnesium 150 Bisglycinaat, 180 tabletten). Elke run werd daardoor rood en de feed
bleef op 07-10 staan. Drie gevallen:
  1. storing + SKU in de vorige feed  -> vorige regel overgenomen, gemarkeerd
  2. storing + SKU niet in vorige feed -> maat valt weg, product blijft
  3. meer dan 5% storingen            -> run stopt (uitval, geen losse storing)

Draaien: python test_variantstoring.py
"""

import unittest
from unittest import mock

import vitakruid_common as vc

PRODUCT_HTML = """
<script type="application/ld+json">{"@type":"Product","name":"Magnesium 150 Bisglycinaat","brand":{"name":"Vitakruid"},"sku":"91350"}</script>
<select id="variantSubstanceSelect">
  <option value="91350">90 tabletten</option>
  <option value="91367">180 tabletten</option>
</select>
"""


class _Antwoord:
    def __init__(self, text):
        self.text = text


def _maak_fetch(kapot):
    """Nep-fetch: productpagina's komen, variant-codes in `kapot` geven een storing."""
    def fetch(session, url, retries=3, allow_404=False, ajax=False, verplicht=False):
        if "/products/" in url:
            return _Antwoord(PRODUCT_HTML)
        code = url.rsplit("/", 1)[-1]
        if code in kapot:
            raise RuntimeError(f"{url} kwam na 3 pogingen niet binnen (500 Server Error). De run stopt")
        raise AssertionError("parse_variant wordt in deze test gemockt")
    return fetch


def _variant(code, prijs):
    return {"code": code, "sku": code, "ean": f"871743869{code}", "zindex": "", "price": prijs,
            "image": "", "samenstelling": "", "dosering": ""}


class VariantStoringTest(unittest.TestCase):
    def setUp(self):
        self.sleep = mock.patch.object(vc.time, "sleep")
        self.sleep.start()

    def tearDown(self):
        self.sleep.stop()

    def _run(self, kapot, vorige, slugs=("magnesium-150-bisglycinaat",), max_overname=0.05):
        def parse_variant(session, code):
            if code in kapot:
                raise vc.VariantStoring(code, "500 Server Error")
            return _variant(code, 29.90)
        with mock.patch.object(vc, "fetch", _maak_fetch(kapot)), \
             mock.patch.object(vc, "parse_variant", parse_variant):
            return list(vc.scrape_products(None, list(slugs), vorige=vorige, max_overname=max_overname))

    def test_1_storing_met_vorige_regel_wordt_overgenomen(self):
        vorige = {"91367": {"sku": "91367", "barcode": "8717438691367", "price": "58.90"}}
        producten = self._run(kapot={"91367"}, vorige=vorige, max_overname=0.5)
        varianten = {v["sku"]: v for v in producten[0]["variants"]}
        self.assertEqual(set(varianten), {"91350", "91367"})
        self.assertEqual(varianten["91367"]["price"], 58.90)
        self.assertEqual(varianten["91367"]["ean"], "8717438691367")
        self.assertEqual(varianten["91367"]["label"], "180 tabletten")
        self.assertTrue(varianten["91367"].get("overgenomen"))
        self.assertFalse(varianten["91350"].get("overgenomen"))

    def test_2_storing_zonder_vorige_regel_laat_maat_wegvallen(self):
        producten = self._run(kapot={"91367"}, vorige={}, max_overname=0.5)
        self.assertEqual([v["sku"] for v in producten[0]["variants"]], ["91350"])

    def test_3_meer_dan_vijf_procent_storingen_stopt_de_run(self):
        # 1 storing op 2 varianten = 50% > 5%: uitval, geen losse storing
        vorige = {"91367": {"sku": "91367", "barcode": "x", "price": "58.90"}}
        with self.assertRaises(RuntimeError) as ctx:
            self._run(kapot={"91367"}, vorige=vorige, max_overname=0.05)
        self.assertIn("uitval", str(ctx.exception))
        # dezelfde storing binnen de grens (lat op 50%) loopt wél door
        producten = self._run(kapot={"91367"}, vorige=vorige, max_overname=0.5)
        self.assertEqual(len(producten[0]["variants"]), 2)

    def test_4_vorige_feed_lezen_op_sku(self):
        import os
        import tempfile
        xml = ('<?xml version="1.0" encoding="UTF-8"?><products><product><handle>h</handle>'
               '<sku>91367</sku><barcode>8717438691367</barcode><price>58.90</price>'
               '<option1>180 tabletten</option1><images><image><src>https://x/1.jpg</src></image></images>'
               '</product><product><sku/><price>1.00</price></product></products>')
        fd, pad = tempfile.mkstemp(suffix=".xml")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(xml)
        try:
            vorige = vc.lees_vorige_varianten(pad)
        finally:
            os.remove(pad)
        self.assertEqual(list(vorige), ["91367"])          # lege sku telt niet mee
        self.assertEqual(vorige["91367"]["images"], ["https://x/1.jpg"])
        v = vc._variant_uit_vorige("91367", "", vorige["91367"])
        self.assertEqual((v["price"], v["label"], v["image"]), (58.90, "180 tabletten", "https://x/1.jpg"))
        self.assertEqual(vc.lees_vorige_varianten("bestaat-niet.xml"), {})

    def test_5_parse_variant_vertaalt_fetch_storing(self):
        with mock.patch.object(vc, "fetch", _maak_fetch({"91367"})):
            with self.assertRaises(vc.VariantStoring) as ctx:
                vc.parse_variant(None, "91367")
        self.assertEqual(ctx.exception.code, "91367")
        self.assertIn("500", ctx.exception.oorzaak)


if __name__ == "__main__":
    unittest.main(verbosity=2)
