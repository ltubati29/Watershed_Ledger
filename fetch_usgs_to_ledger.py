#!/usr/bin/env python3
"""Fetch the latest USGS sensor readings for Watershed Ledger.

Command line:  python3 fetch_usgs_to_ledger.py [station numbers] > readings.csv
               python3 fetch_usgs_to_ledger.py --find [west,south,east,north]   (default: Texas)
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
PCODES = {"00010": "temp", "00095": "cond", "00300": "do", "00400": "ph", "00060": "discharge"}
TEXAS_BBOX = (-106.65, 25.84, -93.51, 36.50)  # west, south, east, north
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
    """Newest value of one sensor: the last 6 hours first, then the last 3 days."""
    for window, limit in (("PT6H", 200), ("P3D", 1000)):
        d = get("/collections/continuous/items", f="json", monitoring_location_id=site,
                parameter_code=pcode, time=window, limit=limit)
        feats = d.get("features", [])
        if feats:
            best = max(feats, key=lambda f: f["properties"]["time"])["properties"]
            return best["value"], best["time"]
    return "", ""


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
        try:  # no discharge at all means a pool, not a stream: judge it as still water
            if str(row.get("discharge", "")) != "" and float(row["discharge"]) <= 0.05:
                row["flow"] = "0"
        except ValueError:
            pass
        rows.append(row)
    return rows, warnings


def find(bbox, want=("00300", "00400"), max_sites=20):
    """Active stations inside bbox that report every parameter in `want`
    (default: dissolved oxygen and pH). Uses the time-series-metadata collection."""
    found = []
    for pcode in want:
        d = get("/collections/time-series-metadata/items", f="json", parameter_code=pcode,
                bbox=",".join(str(x) for x in bbox), end="P3D", limit=1000)
        found.append({f["properties"]["monitoring_location_id"] for f in d.get("features", [])})
    out = []
    for site in sorted(set.intersection(*found))[:max_sites]:
        try:
            name, lat, lon = location(site)
        except Exception:
            name, lat, lon = site, "", ""
        out.append({"id": site.split("-")[-1], "name": name, "lat": lat, "lon": lon})
    return out


def to_csv(rows):
    lines = [",".join(HEADER)]
    for r in rows:
        lines.append(",".join(str(r.get(c, "")).replace(",", ";") for c in HEADER))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    if sys.argv[1:2] == ["--find"]:
        box = tuple(float(x) for x in sys.argv[2].split(",")) if len(sys.argv) > 2 else TEXAS_BBOX
        for s in find(box):
            print(f'{s["id"]}  {s["name"]}')
        sys.exit(0)
    out, warns = collect(sys.argv[1:] or DEFAULT_SITES)
    print(to_csv(out), end="")
    for w in warns:
        print("warning:", w, file=sys.stderr)
