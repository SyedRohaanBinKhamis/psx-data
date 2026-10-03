"""Download 3 years of daily PSX prices for all listed companies.

Uses the psx-dps library, which handles PSX's broken server nodes
(some return 404 for data routes). Run: python fetch_psx.py
"""
import csv
import socket
import time
from datetime import date, timedelta
from pathlib import Path

from psx_dps import Client, CoolingDown, NoData, PSXError

YEARS = 3
socket.setdefaulttimeout(30)  # never hang forever on a stalled connection
DATA = Path("data")


def main():
    DATA.mkdir(exist_ok=True)
    since = (date.today() - timedelta(days=365 * YEARS)).isoformat()

    with Client(user_agent="psx-personal-analysis/1.0") as psx:
        symbols = psx.symbols()  # excludes debt instruments
        with open(DATA / "symbols.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["symbol", "name", "sector", "is_etf"])
            for s in symbols:
                w.writerow([s.get("symbol"), s.get("name"), s.get("sectorName"), s.get("isETF")])

        rows, failed = [], []
        for i, s in enumerate(symbols, 1):
            sym = s["symbol"]
            bars = None
            for attempt in range(3):
                try:
                    bars = psx.eod(sym, since=since)
                    break
                except CoolingDown as e:
                    print("PSX asked us to slow down, stopping early:", e)
                    bars = None
                    attempt = 99
                    break
                except NoData:
                    break
                except (PSXError, OSError):
                    time.sleep(3)
            if attempt == 99:
                break
            if bars is None:
                failed.append(sym)
                continue
            rows.extend((sym, b["date"], b["open"], b["close"], b["volume"]) for b in bars)
            if i % 50 == 0:
                print(f"{i}/{len(symbols)} done", flush=True)

    if not rows:
        raise SystemExit("No data downloaded, keeping existing files")

    rows.sort()
    with open(DATA / "psx_eod.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "date", "open", "close", "volume"])
        w.writerows(rows)

    print(f"Wrote {len(rows)} rows for {len({r[0] for r in rows})} symbols")
    if failed:
        print("No data for:", ", ".join(failed))


if __name__ == "__main__":
    main()
