# Watershed Ledger

One Health dashboard for urban freshwater. Each station is scored by the rules of its own kind of water (still or flowing), then explained for people, pets and wildlife, and the stream. Real readings come from the USGS Water Data API.

## Run it

```
python3 server.py
```

Open http://localhost:8000 and press **Refresh from USGS**. No packages to install (Python 3.8+).

The server runs only on your computer. The button calls `fetch_usgs_to_ledger.py`, which asks USGS for the newest sensor values, saves `data/readings.csv`, appends `data/history.json` (this feeds the trend line), and the page updates itself. On the next visit the page loads the last saved readings automatically.

Optional: a free USGS API key raises request limits. `export USGS_API_KEY=your_key` before starting the server.

## Files

| File | What it does |
| --- | --- |
| `index.html` | The dashboard (all scoring logic, map, quick-entry, export) |
| `server.py` | Local server and the Refresh endpoint |
| `fetch_usgs_to_ledger.py` | Reads USGS stations; also works alone: `python3 fetch_usgs_to_ledger.py > readings.csv` |

## Honest limits

- USGS values are provisional. These sensors report temperature, conductivity, oxygen and pH, not bacteria, blooms or flow speed. The dashboard shows those as "not measured" and prompts a person to check.
- Scoring thresholds are starting points from public guidance, not yet validated against past events.
- Add stations by USGS number in the box on the page; check that a station reports oxygen and pH first.

## Public page (GitHub Pages)

`update_live.py` runs on GitHub every 30 minutes (`.github/workflows/update-data.yml`), reads the station numbers in `stations.txt`, and writes `live/readings.csv` and `live/history.json`. The same `index.html` loads those files when no local server is running, so the public page updates itself. To change the stations, edit `stations.txt` on GitHub.
