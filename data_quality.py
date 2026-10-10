"""Flag suspicious one-day price jumps (likely splits, unit changes or bad data).

Writes data/suspect_jumps.csv with every day where a close moved more than 25%
from the previous close. PSX daily limits are about 10% (or Re 1 for low-priced
shares), so bigger moves are usually corporate actions that were not adjusted. Run: python data_quality.py
"""
import csv
from pathlib import Path

THRESHOLD = 25.0
src = Path("data/psx_eod.csv")
out = Path("data/suspect_jumps.csv")

prev = {}
flagged = []
with open(src, newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        sym, close = r["symbol"], float(r["close"])
        p = prev.get(sym)
        if p and p > 0:
            chg = (close / p - 1) * 100
            if abs(chg) > THRESHOLD and abs(close - p) > 1.01:
                flagged.append((sym, r["date"], p, close, round(chg, 1), r["volume"]))
        prev[sym] = close

with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["symbol", "date", "prev_close", "close", "change_pct", "volume"])
    w.writerows(flagged)
print(f"{len(flagged)} suspicious jumps across {len({x[0] for x in flagged})} symbols")
