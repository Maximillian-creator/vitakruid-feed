"""
Prijsrem voor de eigen leveranciersfeeds (gedeelde module, 30-10-2026)
=====================================================================
Op 27-10-2026 ging kalahealth.nl prijzen zonder btw tonen aan bezoekers buiten de EU. De
GitHub-runners staan in de VS, dus de Kala-feed kreeg alle prijzen ÷1,09 en Stock Sync zette ze
op 28-10 08:00 zo in de winkel: 163 producten 8,3% te goedkoop, drie dagen lang. Vanaf de VPS en
vanaf Max' laptop gaf dezelfde API gewoon de prijs incl. btw. Geen van onze scrapers had een rem
op de prijs; wel op de omvang (een halve feed laat Stock Sync archiveren).

Deze module zit vlak vóór `save_xml()` in elke eigen scraper en vergelijkt elke regel met de
vorige feed (het bestand dat in het repo staat, dus wat Stock Sync het laatst las):

    tot 3% verschil                      → gewone prijswijziging, gaat door
    precies ÷1,09 of ÷1,21, bij ≥ 30%    → de bron toont zonder btw: terugrekenen (×1,09 / ×1,21)
      van de vergeleken regels
    precies ×1,09 of ×1,21               → de bron toont weer incl. na een btw-loze feed: gaat door
    al het andere (> 3%)                 → de prijs uit de vorige feed blijft staan, met een logregel

Beschikbaarheid, voorraad en alle andere velden gaan altijd mee: de rem raakt alleen `<price>`.
Een nieuwe SKU zonder vorige prijs gaat door zoals hij binnenkomt.

Een SKU die in de vorige feed vaker voorkomt, vergelijken we op SKU + handle (05-11-2026:
Vitakruid geeft drie bundels elk dezelfde code, bv. `zwangerschap` voor "Zwangerschap Bundel"
€ 69,64 én "Zwangerschap Bundel Basis" € 42,14). Op SKU alleen pakte de rem de prijs van het
andere product en "hield" die vast, zodat de basisbundel € 69,64 zou worden. Is het ook met de
handle nog dubbelzinnig, dan gaat de regel door zonder vergelijking (telt als "zonder vorige"). `FORCE_PRIJZEN=1` zet de rem
uit voor één run (bewust, bv. na een echte prijsronde van een leverancier).

Gebruik in scraper.py, vlak vóór save_xml:

    import prijsrem
    print(prijsrem.verslag(prijsrem.pas_toe(root, OUTPUT_FILE)))

Alleen stdlib. Dezelfde file staat in elk feed-repo; de bron is
`Claude Code Projecten/leveranciers-feeds/prijsrem.py`. Test: `python test_prijsrem.py`.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET

MARGE = 0.03                 # tot 3% verschil met de vorige feed is een gewone prijswijziging
BTW_SPELING = 0.006          # ÷1,09 of ÷1,21 herkennen we op 0,6% nauwkeurig (afronding op centen)
BTW_MINIMUM = 0.30           # btw-correctie alleen als ≥ 30% van de vergeleken regels dat patroon heeft
BTW_FACTOREN = (1.09, 1.21)  # de twee Nederlandse tarieven; welk tarief een product heeft, weten we niet zeker


HANDLE_TAG = "handle"


def _sleutels(el: ET.Element, sku_tag: str) -> tuple[str, tuple[str, str]]:
    sku = (el.findtext(sku_tag) or "").strip()
    return sku, (sku, (el.findtext(HANDLE_TAG) or "").strip())


def lees_vorige(pad: str, item_tag: str = "product", sku_tag: str = "sku", price_tag: str = "price") -> dict:
    """Prijzen uit de vorige feed: `sku` → prijs, of `(sku, handle)` → prijs als de SKU vaker
    voorkomt. Dubbelzinnige sleutels staan er niet in. Leeg als er geen (leesbare) vorige feed is."""
    try:
        root = ET.parse(pad).getroot()
    except (OSError, ET.ParseError):
        return {}
    rijen = []
    for el in root.iter(item_tag):
        sku, sku_handle = _sleutels(el, sku_tag)
        try:
            prijs = float((el.findtext(price_tag) or "").replace(",", "."))
        except ValueError:
            continue
        if sku and prijs > 0:
            rijen.append((sku, sku_handle, prijs))
    per_sku = {}
    for sku, _, _ in rijen:
        per_sku[sku] = per_sku.get(sku, 0) + 1
    per_paar = {}
    for _, paar, _ in rijen:
        per_paar[paar] = per_paar.get(paar, 0) + 1
    uit = {}
    for sku, paar, prijs in rijen:
        if per_sku[sku] == 1:
            uit[sku] = prijs
        elif per_paar[paar] == 1:
            uit[paar] = prijs
    return uit


def _vorige_prijs(vorige: dict, el: ET.Element, sku_tag: str):
    sku, paar = _sleutels(el, sku_tag)
    return vorige.get(sku) if sku in vorige else vorige.get(paar)


def _klasse(ratio: float) -> tuple[str, float]:
    if abs(ratio - 1) <= MARGE:
        return "ok", 1.0
    for f in BTW_FACTOREN:
        if abs(ratio - 1 / f) <= BTW_SPELING:
            return "btw_eraf", f
        if abs(ratio - f) <= BTW_SPELING:
            return "btw_terug", f
    return "afwijkend", 1.0


def pas_toe(root: ET.Element, vorig_pad: str, item_tag: str = "product", sku_tag: str = "sku",
            price_tag: str = "price") -> dict:
    """Past `<price>` in de nieuwe feed ter plekke aan volgens de regels hierboven. Geeft een verslag."""
    r = {"vergeleken": 0, "nieuw_zonder_vorige": 0, "ok": 0, "btw_eraf": 0, "btw_terug": 0,
         "gecorrigeerd": [], "vastgehouden": [], "uit": os.environ.get("FORCE_PRIJZEN") == "1"}
    if r["uit"]:
        return r
    vorige = lees_vorige(vorig_pad, item_tag, sku_tag, price_tag)
    if not vorige:
        r["nieuw_zonder_vorige"] = sum(1 for _ in root.iter(item_tag))
        return r
    rijen = []                                       # (price-element, sku, nieuw, oud, klasse, factor)
    for el in root.iter(item_tag):
        sku = (el.findtext(sku_tag) or "").strip()
        pel = el.find(price_tag)
        try:
            nieuw = float((pel.text or "").replace(",", ".")) if pel is not None else 0.0
        except ValueError:
            nieuw = 0.0
        oud = _vorige_prijs(vorige, el, sku_tag)
        if not sku or pel is None or nieuw <= 0 or not oud:
            r["nieuw_zonder_vorige"] += 1
            continue
        r["vergeleken"] += 1
        klasse, factor = _klasse(nieuw / oud)
        rijen.append((pel, sku, nieuw, oud, klasse, factor))
    n = max(r["vergeleken"], 1)
    btw_systeem = sum(1 for *_, k, _ in rijen if k == "btw_eraf") / n >= BTW_MINIMUM
    for pel, sku, nieuw, oud, klasse, factor in rijen:
        if klasse == "btw_eraf" and btw_systeem:
            hersteld = round(nieuw * factor, 2)
            pel.text = f"{hersteld:.2f}"
            r["gecorrigeerd"].append((sku, nieuw, hersteld))
            r["btw_eraf"] += 1
        elif klasse in ("ok", "btw_terug"):
            r[klasse] += 1
        else:
            pel.text = f"{oud:.2f}"
            r["vastgehouden"].append((sku, oud, nieuw))
    return r


def verslag(r: dict) -> str:
    if r.get("uit"):
        return "   PRIJSREM uit (FORCE_PRIJZEN=1): alle prijzen gaan door zoals ze binnenkomen"
    regels = [f"   PRIJSREM {r['vergeleken']} regels vergeleken met de vorige feed, {r['nieuw_zonder_vorige']} zonder "
              f"vorige prijs: {r['ok']} gelijk of < 3% anders"]
    if r["btw_eraf"]:
        s, van, naar = r["gecorrigeerd"][0]
        regels.append(f"   !  BTW-CORRECTIE: {r['btw_eraf']} prijzen kwamen zonder btw binnen (÷1,09 of ÷1,21) en zijn "
                      f"teruggerekend, bv. {s}: {van:.2f} → {naar:.2f}. De bron toont prijzen excl. btw aan dit adres.")
    if r["btw_terug"]:
        regels.append(f"   !  {r['btw_terug']} prijzen zijn precies de btw hoger dan de vorige feed: de bron toont weer incl.")
    if r["vastgehouden"]:
        voorbeeld = ", ".join(f"{s}: {o:.2f} → {n:.2f}" for s, o, n in r["vastgehouden"][:5])
        regels.append(f"   !  VASTGEHOUDEN: {len(r['vastgehouden'])} prijzen wijken > 3% af zonder btw-patroon; de prijs uit "
                      f"de vorige feed blijft staan tot Max ernaar kijkt (FORCE_PRIJZEN=1 laat ze door): {voorbeeld}")
    return "\n".join(regels)
