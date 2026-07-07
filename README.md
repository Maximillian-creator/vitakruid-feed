# Vitakruid feeds → Stock Sync

Scrapt **vitakruid.nl** (Symfony-shop, geen products.json, openbaar) en levert twee
feeds voor Stock Sync. Draait automatisch via GitHub Actions.

| Feed | Script | Output | Doel | Schema |
|---|---|---|---|---|
| **Update** | `scraper.py` | `vitakruid_feed.xml` | prijs bijwerken (per variant) | 2×/dag |
| **Add** | `add_scraper.py` | `vitakruid_add_feed.xml` | nieuwe producten aanmaken | 1×/week (ma) |

## Bron & aanpak
- **Enumeratie:** sitemap → `/products/{slug}`.
- **Basis-pagina:** JSON-LD (naam, merk, EAN, actieve stof, doseervorm) + rijke
  beschrijving (`.prose--pdp`) + variant-opties (`<select>`).
- **Per variant:** `/get-variant-b2c/{code}` → SKU, **EAN**, Z-index, **prijs**,
  afbeelding. Elke maat heeft een eigen EAN + prijs.

## Prijs
- `price` = Vitakruid's eigen **retail** (incl. BTW), 1-op-1 als verkoopprijs.
- **Kostprijs (inkoop)** staat niet publiek → niet in de feed (zelf invullen of marge).

## Stock Sync mapping
- **Update** → match op `sku` of `barcode`; map `price`.
- **Add** → identifier `sku`; map `title`, `vendor`, `barcode`, `price`, `description`,
  `option1_name`/`option1` (Inhoud), `image_links` (scheidingsteken = komma).

## Lokaal testen
```bash
pip install -r requirements.txt
INSECURE_SSL=1 python add_scraper.py   # achter een SSL-onderscheppende proxy
```
