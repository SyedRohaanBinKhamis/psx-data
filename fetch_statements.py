"""Weekly: full financial statements for the companies in watchlist.txt.

Source: stockanalysis.com (income statement, balance sheet, cash flow; annual and
quarterly; amounts in millions of PKR). Writes data/statements.csv in long format:
symbol, statement, frequency, period, metric, value, fetched_on

Run: python fetch_statements.py
Debug one page: python fetch_statements.py --debug KML
Coverage test: python fetch_statements.py --coverage 40   (random sample of traded companies)
"""
import csv
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://stockanalysis.com/quote/psx/{sym}/financials/{page}/"
STATEMENTS = {"income": "income-statement", "balance": "balance-sheet",
              "cashflow": "cash-flow-statement"}
FREQS = {"annual": "", "quarterly": "?p=quarterly"}
DELAY = 3.0
HEADERS = {"User-Agent": "Mozilla/5.0 (personal research script; contact via GitHub repo)"}
OUT = Path("data/statements.csv")


def clean(t):
    return re.sub(r"\s+", " ", t or "").strip()


def to_num(s):
    s = clean(s).replace(",", "")
    if s in ("", "-", "--", "n/a", "N/A"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()%")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def parse_statement(html):
    """Return list of (period, metric, value) from the main financial table."""
    soup = BeautifulSoup(html, "lxml")
    best = []
    for table in soup.find_all("table"):
        head_rows = table.find("thead").find_all("tr") if table.find("thead") else []
        periods = []
        if head_rows:
            periods = [clean(th.get_text(" ")) for th in head_rows[0].find_all(["th", "td"])][1:]
        body = table.find("tbody") or table
        rows = []
        for tr in body.find_all("tr"):
            cells = [clean(c.get_text(" ")) for c in tr.find_all(["th", "td"])]
            if len(cells) >= 2:
                rows.append(cells)
        if not periods and rows:
            periods = rows[0][1:]
            rows = rows[1:]
        out = []
        for cells in rows:
            label = cells[0]
            if not label or label.lower().startswith("period ending"):
                continue
            for period, val in zip(periods, cells[1:]):
                num = to_num(val)
                if num is not None:
                    out.append((period, label, num))
        if len(out) > len(best):
            best = out
    return best


def get(url):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                return r.text
            if r.status_code in (403, 404):
                return None
        except requests.RequestException:
            pass
        time.sleep(5 * (attempt + 1))
    return None


def load_watchlist():
    syms = []
    for line in Path("watchlist.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip().upper()
        if line:
            syms.append(line)
    return syms


def coverage(n):
    import random
    prices = {}
    with open("data/psx_eod.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            prices[r["symbol"]] = r["date"]
    last = max(prices.values())
    active = sorted(s for s, d in prices.items()
                    if d == last and not re.search(r"(ETF|R\d?|PS|CPS)$", s))
    random.seed(7)
    sample = random.sample(active, min(n, len(active)))
    results = []
    for sym in sample:
        html = get(BASE.format(sym=sym, page=STATEMENTS["income"]))
        time.sleep(DELAY)
        rows = parse_statement(html) if html else []
        results.append((sym, 1 if rows else 0, len(rows)))
        print(f"{sym}: {'OK' if rows else 'missing'} ({len(rows)} values)", flush=True)
    Path("data").mkdir(exist_ok=True)
    with open("data/_coverage.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "has_income_statement", "values"])
        w.writerows(results)
    ok = sum(r[1] for r in results)
    print(f"Coverage: {ok} of {len(results)} sampled companies ({ok / len(results):.0%}); "
          f"~{round(ok / len(results) * len(active))} of {len(active)} traded companies")


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--coverage":
        coverage(int(sys.argv[2]))
        return
    if len(sys.argv) > 2 and sys.argv[1] == "--debug":
        sym = sys.argv[2].upper()
        html = get(BASE.format(sym=sym, page=STATEMENTS["income"]))
        if not html:
            raise SystemExit("Page could not be downloaded (blocked or not found)")
        Path("data").mkdir(exist_ok=True)
        Path(f"data/_debug_{sym}_income.html").write_text(html, encoding="utf-8")
        rows = parse_statement(html)
        print("parsed rows:", len(rows))
        print(rows[:8])
        return

    symbols = load_watchlist()
    today = date.today().isoformat()
    rows, failed = [], []
    for sym in symbols:
        got = 0
        for stmt, page in STATEMENTS.items():
            for freq, query in FREQS.items():
                html = get(BASE.format(sym=sym, page=page) + query)
                time.sleep(DELAY)
                if not html:
                    continue
                for period, metric, value in parse_statement(html):
                    rows.append((sym, stmt, freq, period, metric, value, today))
                    got += 1
        print(f"{sym}: {got} values", flush=True)
        if not got:
            failed.append(sym)

    if not rows:
        raise SystemExit("No statement data downloaded; keeping existing file. "
                         "Run: python fetch_statements.py --debug KML")

    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "statement", "frequency", "period", "metric", "value", "fetched_on"])
        w.writerows(rows)
    print(f"Wrote {len(rows)} values for {len(symbols) - len(failed)} of {len(symbols)} companies")
    if failed:
        print("No data for:", ", ".join(failed))


if __name__ == "__main__":
    main()
