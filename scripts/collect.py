"""City-first price ingestion from official Israeli retailer price files.

Bounded pilot: all 31 implemented adapters are inspected, Jerusalem is prioritized.
Store/file success and failures are published separately; never claim full coverage.
"""
from __future__ import annotations
import argparse
import gzip
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import israeli_prices as ilp

TZ = ZoneInfo("Asia/Jerusalem")
MAX_AGE = timedelta(days=7)

def iso(value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=TZ)
    return value.isoformat()

def city_match(store, city):
    """Prefer the Israeli locality code. Never mistake a street named ירושלים for the city."""
    city = str(city or "").strip()
    locality = str(getattr(store, "city", None) or "").strip()
    branch = str(getattr(store, "name", None) or "").strip()
    if city == "ירושלים":
        if locality == "3000" or locality in ("ירושלים", "Jerusalem"):
            return True
        # A known numeric code for another town takes priority over the street/address.
        if locality.isdecimal() and locality != "0":
            return False
        # City code 0 means unknown; only trust the branch name, not its address.
        other_places = ["ראשל", "ראשון לציון", "רמלה", "יפו", "תל אביב", "רעננה", "מודיעין", "פתח תקווה", "חולון", "חיפה", "נתניה", "אשדוד", "באר שבע"]
        return ("ירושלים" in branch or "Jerusalem" in branch) and not any(place in branch for place in other_places)
    return locality.casefold() == city.casefold()

def select_city_stores(stores, chain_slug, city, limit):
    matches = [s for s in stores if city_match(s, city)]
    matches.sort(key=lambda s: (str(getattr(s, "sub_chain_name", "") or ""), str(s.store_id)))
    if chain_slug == "shufersal" and city == "ירושלים":
        universe = [s for s in matches if "יוניברס" in str(getattr(s, "sub_chain_name", "") or "") or "יוניברס" in str(getattr(s, "name", "") or "")]
        others = [s for s in matches if s not in universe]
        if universe:
            return (universe[:max(1, limit // 2)] + others[:max(0, limit - min(len(universe), max(1, limit // 2)))])[:limit], len(matches)
    return matches[:limit], len(matches)

def normalized_name(value):
    return " ".join(str(value or "").split())

def prefixes(value):
    parts = re.findall(r"[\u0590-\u05ffA-Za-z0-9]+", str(value or "").lower())
    return sorted({w[:2] for w in parts if len(w) >= 2})

def shard_filename(prefix):
    return "u" + "-".join(f"{ord(c):04x}" for c in prefix) + ".json.gz"

def make_key(item, chain_slug):
    gtin = getattr(item, "gtin", None)
    if gtin and str(gtin).isdigit():
        return "gtin:" + str(gtin)
    return "internal:" + chain_slug + ":" + str(item.item_code)

def product_for(item, chain_slug):
    return {
        "key": make_key(item, chain_slug),
        "barcode": str(item.item_code),
        "name": normalized_name(getattr(item, "name", None) or getattr(item, "manufacturer_description", None)),
        "manufacturer": normalized_name(getattr(item, "manufacturer", None)),
        "unit": normalized_name(getattr(item, "unit_of_measure", None)),
        "weighted": bool(getattr(item, "is_weighted", False)),
        "offers": []
    }

def valid_price(item):
    try:
        p = float(item.price)
        return p if 0 < p < 100000 else None
    except (ValueError, TypeError, OverflowError):
        return None

def load_previous(city_path):
    products = {}
    if not city_path.exists():
        return products
    for file in city_path.glob("*.json.gz"):
        try:
            with gzip.open(file, "rt", encoding="utf-8") as fh:
                data = json.load(fh)
            for row in data.get("products", []):
                key = str(row.get("key") or "")
                if key and key not in products:
                    products[key] = {**row, "offers": list(row.get("offers", []))}
                elif key:
                    current = products[key]
                    ids = {o.get("storeKey") for o in current["offers"]}
                    current["offers"].extend(o for o in row.get("offers", []) if o.get("storeKey") not in ids)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            print("Previous shard unreadable:", file.name, str(exc)[:120], file=sys.stderr)
    return products

def fetch_store(chain, store):
    store_id = str(store.store_id)
    refs = ilp.list_files(chain.slug, file_type=ilp.FileType.PRICE_FULL, store_id=store_id, limit=1)
    if not refs:
        raise FileNotFoundError(f"No PriceFull for {chain.slug}/{store_id}")
    ref = refs[0]
    parsed = ilp.parse(ilp.download(ref))
    actual = str(getattr(parsed, "store_id", None) or store_id)
    if actual.lstrip("0") != store_id.lstrip("0"):
        raise ValueError(f"Mismatched store ID: expected {store_id}, got {actual}")
    fetched = datetime.now(timezone.utc).isoformat()
    subchain = str(getattr(store, "sub_chain_id", None) or getattr(parsed, "sub_chain_id", None) or "0")
    key = f"{chain.slug}|{subchain}|{store_id}"
    label = str(getattr(store, "sub_chain_name", None) or getattr(chain, "name_he", None) or chain.name)
    city_value = str(getattr(store, "city", None) or "")
    if not city_value or city_value.isdigit():
        city_value = "ירושלים" if city_match(store, "ירושלים") else city_value
    published = iso(ref.published_at)
    offers = []
    for item in getattr(parsed, "items", []):
        if not getattr(item, "item_code", None):
            continue
        name = normalized_name(getattr(item, "name", None) or getattr(item, "manufacturer_description", None))
        if not name:
            continue
        price = valid_price(item)
        if price is None:
            continue
        p = product_for(item, chain.slug)
        offers.append((p, {
            "storeKey": key, "chainId": chain.slug, "storeId": store_id,
            "chainName": label, "storeName": str(getattr(store, "name", None) or ""),
            "city": city_value, "address": str(getattr(store, "address", None) or ""),
            "price": price, "priceChangedAt": iso(getattr(item, "price_update_time", None)),
            "sourcePublishedAt": published, "sourceFetchedAt": fetched,
            "sourceFile": ref.name, "source": "official-pricefull",
        }))
    return key, offers, {"store": store_id, "subchain": subchain, "name": str(getattr(store, "name", "") or ""), "city": city_value, "published": published, "items": len(offers), "status": "success"}

def merge_products(old, replacements, now):
    # Full snapshots replace prior rows for those specific stores, never other stores.
    touched = set(replacements)
    for p in old.values():
        p["offers"] = [o for o in p.get("offers", []) if o.get("storeKey") not in touched]
    for storekey, pairs in replacements.items():
        for product, offer in pairs:
            key = product["key"]
            row = old.setdefault(key, product)
            if not row.get("name"):
                row["name"] = product["name"]
            row["offers"].append(offer)
    expire_before = now - MAX_AGE
    final = {}
    for key, p in old.items():
        offers = []
        for o in p.get("offers", []):
            stamp = o.get("sourceFetchedAt")
            try:
                time_value = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue
            if time_value.tzinfo is None:
                time_value = time_value.replace(tzinfo=timezone.utc)
            if time_value >= expire_before:
                offers.append(o)
        if offers:
            p["offers"] = offers
            final[key] = p
    return final

def write_shards(base, products):
    shards = defaultdict(list)
    for p in products.values():
        for prefix in prefixes(p.get("name", "")) + prefixes(p.get("manufacturer", "")):
            shards[prefix].append(p)
    base.mkdir(parents=True, exist_ok=True)
    expected = set()
    for prefix, rows in shards.items():
        filename = shard_filename(prefix)
        expected.add(filename)
        blob = json.dumps({"city": "ירושלים", "products": rows}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        path = base / filename
        path.write_bytes(gzip.compress(blob, compresslevel=6, mtime=0))
    for path in base.glob("*.json.gz"):
        if path.name not in expected:
            path.unlink()
    return len(shards)

def write_barcode_shards(base, products):
    """Index exact EAN/GTIN codes separately from text search shingles.

    Each barcode prefix is its own small gzip shard; this allows exact barcode
    lookup without searching a name or downloading the entire city catalogue.
    Distinct internal product keys are not merged by barcode.
    """
    buckets = defaultdict(list)
    for product in products.values():
        code = str(product.get("barcode") or "").strip()
        if code.isascii() and code.isdigit() and 8 <= len(code) <= 14:
            buckets["b" + code[:7] + ".json.gz"].append(product)
    base.mkdir(parents=True, exist_ok=True)
    expected = set(buckets)
    for filename, rows in buckets.items():
        rows.sort(key=lambda p: str(p.get("key") or p.get("barcode")))
        blob = json.dumps({"city": "ירושלים", "products": rows},
                          ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        (base / filename).write_bytes(gzip.compress(blob, compresslevel=6, mtime=0))
    for path in base.glob("b*.json.gz"):
        if path.name not in expected:
            path.unlink()
    return len(buckets)

def collect(city, out, limit=2, delay=0.25, restrict=None):
    now = datetime.now(timezone.utc)
    city_path = out / "cities" / "jerusalem"
    try:
        previous_status = json.loads((out / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous_status = {}
    # Invalidate the first flawed city-name-only selection, which included street names.
    old = load_previous(city_path) if previous_status.get("schemaVersion") == 2 else {}
    replacements = {}
    reports = []
    registry = [chain for chain in ilp.list_chains() if chain.implemented]
    if restrict:
        registry = [chain for chain in registry if chain.slug in restrict]
    for chain in registry:
        report = {"chain": chain.slug, "name": chain.name_he or chain.name, "status": "failed", "availableCityBranches": 0, "stores": []}
        try:
            inventory = ilp.get_stores(chain.slug)
            selected, found = select_city_stores(inventory.stores, chain.slug, city, limit)
            report["availableCityBranches"] = found
            report["inventoryCount"] = len(inventory.stores)
            report["inventoryCitiesSample"] = sorted({str(getattr(s, "city", None) or "") for s in inventory.stores})[:12]
            for store in selected:
                try:
                    key, rows, store_report = fetch_store(chain, store)
                    replacements[key] = rows
                    report["stores"].append(store_report)
                except Exception as exc:
                    report["stores"].append({"store": str(store.store_id), "status": "failed", "error": str(exc)[:200]})
                if delay:
                    time.sleep(delay)
            ok = sum(st["status"] == "success" for st in report["stores"])
            report["status"] = "success" if ok and ok == len(selected) else "partial" if ok else "no_jerusalem_stores" if not selected else "failed"
        except Exception as exc:
            report["error"] = str(exc)[:250]
        reports.append(report)
        print(f'{chain.slug}: {report["status"]} (Jerusalem branches: {report["availableCityBranches"]}; fetched: {len(replacements)})', flush=True)
    merged = merge_products(old, replacements, now)
    shards = write_shards(city_path, merged)
    barcode_shards = write_barcode_shards(city_path / 'barcodes', merged)
    status = {
        "schemaVersion": 2, "generatedAt": now.isoformat(), "city": city, "adapterCount": len(registry),
        "chainsWithSuccessfulDownloads": sum(1 for x in reports if x["status"] in ("success", "partial")),
        "storesDownloadedThisRun": len(replacements), "productsStored": len(merged),
        "shards": shards, "barcodeShards": barcode_shards, "completeNationwide": False,
        "reports": reports
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return status

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--city", default="ירושלים")
    p.add_argument("--out", default="data")
    p.add_argument("--limit-per-chain", type=int, default=2)
    p.add_argument("--delay", type=float, default=0.25)
    p.add_argument("--chain", action="append", default=[])
    args = p.parse_args()
    result = collect(args.city, Path(args.out), args.limit_per_chain, args.delay, set(args.chain) if args.chain else None)
    print(json.dumps({k: result[k] for k in ("adapterCount", "chainsWithSuccessfulDownloads", "storesDownloadedThisRun", "productsStored", "shards")}))
    if not result["storesDownloadedThisRun"]:
        sys.exit(2)
