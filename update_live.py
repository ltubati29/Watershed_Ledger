#!/usr/bin/env python3
"""Scheduled job (runs on GitHub Actions): refresh live/readings.csv and live/history.json.

Reads the station numbers from stations.txt, asks USGS for the newest sensor values,
and writes the files the public page loads. If USGS returns nothing, it stops without
touching the old files, so the page keeps showing the last good data.
"""
from datetime import datetime, timezone
from pathlib import Path

import fetch_usgs_to_ledger as usgs
import server

ROOT = Path(__file__).resolve().parent
LIVE = ROOT / "live"


def station_list():
    f = ROOT / "stations.txt"
    ids = [line.split("#")[0].strip() for line in f.read_text().splitlines()] if f.exists() else []
    return [i for i in ids if i] or usgs.DEFAULT_SITES


def main():
    rows, warnings = usgs.collect(station_list())
    for w in warnings:
        print("warning:", w)
    if not rows:
        raise SystemExit("USGS returned nothing; keeping the previous data.")
    LIVE.mkdir(exist_ok=True)
    fetched = datetime.now(timezone.utc).isoformat()
    (LIVE / "readings.csv").write_text(usgs.to_csv(rows))
    server.save_history(rows, fetched, LIVE)
    (LIVE / "updated.txt").write_text(fetched)
    print(f"Updated {len(rows)} station(s) at {fetched}")


if __name__ == "__main__":
    main()
