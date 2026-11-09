# CompareSuperPrice — Israel supermarket price collector

This repository is dedicated to collecting **official Israeli price-transparency files** for PriceCompare Israel. It is not HomeStock, Recettes or Repassage.

## Why Jerusalem was missing

The current site initially relies on SalSmart, which only covers a limited set of stores. This collector discovers all 31 supported official retail-chain adapters and prioritizes **Jerusalem** stores, including Shufersal/Universe (יוניברס), Rami Levy (רמי לוי), Osher Ad (אושר עד), and Maayan 2000 (מעיין 2000) where their portals provide accessible files.

**Important:** the existence of 31 adapters does not mean every portal or branch was successfully fetched. Inspect `data/status.json` for actual successes, errors and source timestamps. GitHub-hosted runners may be blocked by geo-restricted portals.

## Architecture

- GitHub Actions hourly, with bounded collection and a separate per-store source status.
- Official `Stores` and `PriceFull` records parsed using [rxradar/israeli-prices](https://github.com/rxradar/israeli-prices), MIT.
- Compact gzip JSON product indexes under `data/cities/jerusalem`, readable by the Next.js server API.
- Real file-publication time and fetch time are kept separate from the product's last price-change time.
- Matching by GTIN for packaged products, no false cross-chain barcode joins for weighted/internal-code products.
- No fake promotions: future `PromoFull` processing must preserve quantity, club, eligibility and date restrictions.

## Limits

The first pass prioritizes up to two Jerusalem stores per accessible chain (configurable), **not the entire market**. The store-selection rules must be validated with live inventories. The site must not claim statewide coverage until verified. The repository is public: no API secrets, personal data, or credentials may be committed.

## Workflow

See GitHub Actions > `Collect official grocery prices`. It can be run manually and is scheduled hourly; check the GitHub Actions billing/quotas and the `data/status.json` report. If there is no committed data yet, the site continues to use its fallback source.

To run locally:

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/collect.py --city ירושלים --limit-per-chain 2
```

Data originates with retailers; their published prices may differ from the final checkout price. No purchases are made.
