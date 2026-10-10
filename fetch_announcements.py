"""Append recent PSX company announcements to data/announcements.csv.

Run daily. Pulls the last 14 days (market-wide), merges with the existing file,
removes duplicates. Run: python fetch_announcements.py
"""
import csv
import socket
from datetime import date, timedelta
from pathlib import Path

from psx_dps import Client, NoData, PSXError

socket.setdefaulttimeout(30)
OUT = Path("data/announcements.csv")
DAYS_BACK = 14
PAGE = 100
MAX_PAGES = 30


def main():
    start = (date.today() - timedelta(days=DAYS_BACK)).isoformat()
    end = date.today().isoformat()
    new = []
    with Client(user_agent="psx-personal-analysis/1.0") as psx:
        for page in range(MAX_PAGES):
            try:
                rows = psx.announcements(kind="companies", date_from=start,
                                         date_to=end, count=PAGE, offset=page * PAGE)
            except NoData:
                break
            except PSXError as e:
                print("Announcements fetch failed:", e)
                break
            new.extend(rows)
            if len(rows) < PAGE:
                break

    if not new:
        print("No announcements fetched; keeping existing file")
        return

    old = []
    if OUT.exists():
        with open(OUT, newline="", encoding="utf-8") as f:
            old = list(csv.DictReader(f))

    fields = []
    for r in old + new:
        for k in r:
            if k not in fields:
                fields.append(k)

    seen, merged = set(), []
    for r in new + old:  # new first so fresh rows win
        key = tuple(str(r.get(k, "")) for k in fields)
        if key not in seen:
            seen.add(key)
            merged.append(r)

    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(merged)
    print(f"Fetched {len(new)} rows, file now has {len(merged)}")


if __name__ == "__main__":
    main()
