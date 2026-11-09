"""Rebuild exact-barcode search shards from existing downloaded PriceFull files.

No network ingestion is necessary. The script consumes the existing city name shards,
deduplicates by product key and creates small compressed shards indexed by code prefix.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from collect import load_previous, write_barcode_shards


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--city-path", default="data/cities/jerusalem")
    args = parser.parse_args()

    folder = Path(args.city_path)
    if not folder.exists():
        raise SystemExit("Missing official price index; run collector first.")
    products = load_previous(folder)
    if not products:
        raise SystemExit("Cannot rebuild barcode search: no official products found.")
    count = write_barcode_shards(folder / "barcodes", products)
    print(f"Indexed {len(products)} products in {count} exact barcode-prefix shards.")


if __name__ == "__main__":
    main()
