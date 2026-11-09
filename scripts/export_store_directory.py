"""Export official Israeli supermarket store catalogs for autocomplete.

Only retailer-public store metadata; never include customer/location data or secrets.
The collector continues to fetch price files independently.
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import israeli_prices as ilp

PRIORITY = ("rami-levy", "shufersal", "osher-ad", "maayan-2000", "victory", "yochananof", "mahsanei-hashuk", "carrefour")

def string(value):
    return str(value or "").strip()

def export(destination: Path, limit: int = 31) -> int:
    all_chains = [c for c in ilp.list_chains() if c.implemented]
    chains = sorted(all_chains, key=lambda c: (0 if c.slug in PRIORITY else 1, PRIORITY.index(c.slug) if c.slug in PRIORITY else 999, c.slug))[:limit]
    stores, reports, seen = [], [], set()
    for chain in chains:
        report = {"chain": chain.slug, "name": string(getattr(chain, "name_he", None) or chain.name), "status": "failed", "count": 0}
        try:
            inventory = ilp.get_stores(chain.slug)
            for store in inventory.stores:
                store_id = string(getattr(store, "store_id", ""))
                subchain = string(getattr(store, "sub_chain_id", "")) or "0"
                if not store_id:
                    continue
                key = "|".join([chain.slug, subchain, store_id])
                if key in seen:
                    continue
                seen.add(key)
                locality = string(getattr(store, "city", None))
                name = string(getattr(store, "name", None))
                subchain_name = string(getattr(store, "sub_chain_name", None))
                city = "ירושלים" if locality == "3000" or locality.lower() in ("jerusalem", "ירושלים") else locality
                stores.append({
                    "key": key, "chainId": chain.slug,
                    "chainName": report["name"], "storeId": store_id,
                    "subChainId": subchain, "subChainName": subchain_name,
                    "name": name, "city": city,
                    "cityCode": locality, "address": string(getattr(store, "address", None)),
                    "lat": getattr(store, "latitude", None), "lon": getattr(store, "longitude", None)
                })
            report["count"] = sum(s["chainId"] == chain.slug for s in stores)
            report["status"] = "success"
        except Exception as e:
            report["error"] = str(e)[:200]
        reports.append(report)
        print(f'{chain.slug}: {report["status"]} ({report["count"]})', flush=True)
    stores.sort(key=lambda s: (s["chainName"], s["city"], s["name"], s["key"]))
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "scope": "official stores inventory (NOT price coverage)",
        "chainCount": len({s["chainId"] for s in stores}),
        "storeCount": len(stores),
        "stores": stores,
        "reports": reports,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str), encoding="utf-8")
    print(f"Wrote {len(stores)} stores; {len(reports)} chains inspected", flush=True)
    return 0 if stores else 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/stores.json")
    parser.add_argument("--limit", type=int, default=31)
    args = parser.parse_args()
    sys.exit(export(Path(args.output), args.limit))
