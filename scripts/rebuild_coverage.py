"""Rebuild cumulative official store coverage using previously downloaded price shards."""
from pathlib import Path
from collect import load_previous, write_coverage_report
folder=Path("data/cities/jerusalem")
products=load_previous(folder)
if not products:
    raise SystemExit("No existing official prices to summarize")
summary=write_coverage_report(Path("data"),products)
print(f"Verified store coverage: {summary['uniqueStores']} stores, {summary['uniqueChains']} chains")
