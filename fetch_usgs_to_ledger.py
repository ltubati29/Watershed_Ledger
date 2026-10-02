#!/usr/bin/env python3
"""Fetch the latest USGS sensor readings for Watershed Ledger.

Command line:  python3 fetch_usgs_to_ledger.py [station numbers] > readings.csv
Used by:       server.py (the Refresh button calls collect()).

Uses the USGS Water Data OGC API (https://api.waterdata.usgs.gov/ogcapi/v1):
  - "monitoring-locations": station name and coordinates
  - "continuous": newest sensor values (filters: monitoring_location_id,
    parameter_code, time as an ISO 8601 duration such as PT6H, limit)
Optional: set USGS_API_KEY (free: https://api.waterdata.usgs.gov/signup/) for higher limits.

These sensors do not report E. coli, cyanobacteria, turbidity (at most stations) or
flow speed, so those columns stay blank. USGS values are provisional until approved.
"""
import json
import os
import sys
import urllib.parse
import urllib.request

BASE = "https://api.waterdata.usgs.gov/ogcapi/v1"
PCODES = {"00010": "temp", "00095": "cond", "00300": "do", "00400": "ph"}
COLS = ["flow", "ecoli", "cyano", "do", "temp", "ph", "turb", "cond"]
HEADER = ["name", "lat", "lon"] + COLS + ["source", "order", "observed"]
DEFAULT_SITES = ["01638500", "01646500"]  # Potomac at Point of Rocks, MD; near Washington, DC


def get(path, **params):
    req = urllib.request.Request(f"{BASE}{path}?{urllib.parse.urlencode(params)}")
    req.add_header("Accept", "application/json")
    if os.environ.get("USGS_API_KEY"):
        req.add_header("X-Api-Key", os.environ["USGS_API_KEY"])
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def location(site):
    d = get(f"/collections/monitoring-locations/items/{site}", f="json")
    lon, lat = d["geometry"]["coordinates"][:2]
    return d["properties"].get("monitoring_location_name", site), lat, lon


def latest(site, pcode):
    d = get("/collections/continuous/items", f="json", monitoring_location_id=site,
            parameter_code=pcode, time="PT6H", limit=200)
    feats = d.get("features", [])
    if not feats:
        return "", ""
    best = max(feats, key=lambda f: f["properties"]["time"])["properties"]
    return best["value"], best["time"]


def collect(sites):
    """Return (rows, warnings). One failing station or sensor never stops the rest."""
    rows, warnings = [], []
    for raw in sites:
        site = raw if str(raw).startswith("USGS-") else f"USGS-{raw}"
        try:
            name, lat, lon = location(site)
        except Exception as e:
            warnings.append(f"{site}: could not read station ({e})")
            continue
        row = {"name": name, "lat": lat, "lon": lon, "source": "usgs",
               "order": site.split("-")[-1], "observed": ""}
        for pcode, key in PCODES.items():
            try:
                value, when = latest(site, pcode)
            except Exception as e:
                warnings.append(f"{site} {key}: {e}")
                continue
            row[key] = value
            if when and when > row["observed"]:
                row["observed"] = when
        rows.append(row)
    return rows, warnings


def to_csv(rows):
    lines = [",".join(HEADER)]
    for r in rows:
        lines.append(",".join(str(r.get(c, "")).replace(",", ";") for c in HEADER))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    out, warns = collect(sys.argv[1:] or DEFAULT_SITES)
    print(to_csv(out), end="")
    for w in warns:
        print("warning:", w, file=sys.stderr)
