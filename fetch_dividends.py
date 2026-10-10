"""Collect PSX dividend / bonus / right announcements into data/dividends.csv.

Source: PSX data portal "Payouts" page (market-wide, all companies).
First run backfills 3 years; later runs fetch the last 45 days and merge.
Run: python fetch_dividends.py
"""
import csv
import re
import socket
from datetime import date, datetime, timedelta
from pathlib import Path

from psx_dps import Client, PSXError
from psx_dps.parsing import table_records

socket.setdefaulttimeout(30)
OUT = Path("data/dividends.csv")
PAGE = 100
MAX_PAGES = 150
FIELDS = ["symbol", "company", "sector", "announcement", "announced_at",
          "book_closure", "cash_pct", "bonus_pct", "right_pct"]
DATE_FORMATS = ["%b %d, %Y %I:%M %p", "%b %d, %Y %H:%M:%S", "%b %d, %Y %H:%M",
                "%b %d, %Y", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y", "%Y-%m-%d"]
TOKEN = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*(?:\(\s*[A-Za-z]+\s*\)\s*)*?\(\s*([DBR])\s*\)")


def parse_date(text):
    t = re.sub(r"\s+", " ", text or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt)
        except ValueError:
            continue
    return None


def parse_announcement(text):
    """Return (cash_pct, bonus_pct, right_pct); percentages of face value."""
    cash = bonus = right = 0.0
    for pct, kind in TOKEN.findall(text or ""):
        v = float(pct)
        if kind == "D":
            cash += v
        elif kind == "B":
            bonus += v
        else:
            right += v
    return cash, bonus, right


def pick(row, *names):
    for k, v in row.items():
        if any(n in k.lower() for n in names):
            return v
    return ""


def main():
    existing = []
    if OUT.exists():
        with open(OUT, newline="", encoding="utf-8") as f:
            existing = list(csv.DictReader(f))
    days_back = 45 if existing else 365 * 3
    cutoff = datetime.now() - timedelta(days=days_back)
    start = (date.today() - timedelta(days=days_back)).isoformat()
    end = date.today().isoformat()

    fresh = []
    with Client(user_agent="psx-personal-analysis/1.0") as psx:
        for page in range(MAX_PAGES):
            body = {"symbol": "", "date_from": start, "date_to": end,
                    "count": str(PAGE), "offset": str(page * PAGE), "page": "payouts"}
            try:
                html = psx._get("/payouts", 0, body=body, force_refresh=True)
                rows = table_records(html)
            except PSXError as e:
                print("Payouts fetch failed:", e)
                break
            if not rows:
                break
            dates = []
            for r in rows:
                ann = pick(r, "dividend")
                ts = pick(r, "date / time", "date")
                cash, bonus, right = parse_announcement(ann)
                dt = parse_date(ts)
                if dt:
                    dates.append(dt)
                fresh.append({
                    "symbol": pick(r, "symbol"), "company": pick(r, "company"),
                    "sector": pick(r, "sector"), "announcement": ann, "announced_at": ts,
                    "book_closure": pick(r, "book closure"),
                    "cash_pct": cash, "bonus_pct": bonus, "right_pct": right})
            if len(rows) < PAGE:
                break
            if dates and max(dates) < cutoff:  # pages are newest-first
                break

    if not fresh:
        print("No payouts fetched; keeping existing file")
        return

    seen, merged = set(), []
    for r in fresh + existing:
        key = (r["symbol"], r["announcement"], r["announced_at"], r["book_closure"])
        if key not in seen:
            seen.add(key)
            merged.append(r)

    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(merged)
    with_cash = sum(1 for r in merged if float(r["cash_pct"] or 0) > 0)
    print(f"Fetched {len(fresh)} rows; file has {len(merged)} rows, {with_cash} with cash dividends")


if __name__ == "__main__":
    main()
