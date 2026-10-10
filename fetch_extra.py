"""Weekly: financials, payouts and company profile for every PSX symbol.

Reads each company page (dps.psx.com.pk/company/SYMBOL) and writes:
  data/financials.csv  (symbol, frequency, period, metric, value)
  data/payouts.csv     (symbol + the columns PSX shows)
  data/profiles.csv    (symbol, market cap, shares, free float, risk warning)

Run: python fetch_extra.py
Debug one company: python fetch_extra.py --debug KML   (saves the raw page)
"""
import csv
import re
import socket
import sys
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup
from psx_dps import Client, CoolingDown, NoData, PSXError

socket.setdefaulttimeout(30)
DATA = Path("data")
PAGE_TTL = 6 * 3600


def clean(t):
    return re.sub(r"\s+", " ", t or "").strip()


def to_num(s):
    s = clean(s).replace(",", "")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()%")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def read_tables(soup):
    """Return a list of (headers, rows) for every table on the page."""
    out = []
    for t in soup.find_all("table"):
        headers = [clean(th.get_text(" ")) for th in t.find_all("th")]
        rows = []
        for tr in t.find_all("tr"):
            cells = [clean(td.get_text(" ")) for td in tr.find_all("td")]
            if cells:
                rows.append(cells)
        if rows:
            out.append((headers, rows))
    return out


def is_quarter(label):
    return bool(re.search(r"\bQ[1-4]\b|quarter", label, re.I))


def parse_company(html):
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n")
    lines = [clean(x) for x in text.split("\n") if clean(x)]

    fin, payouts = [], []
    for headers, rows in read_tables(soup):
        labels = [r[0].lower() for r in rows]
        joined = " ".join(labels)
        head = " ".join(headers).lower()
        if "payout" in head or "book closure" in head or "payout" in joined:
            for r in rows:
                payouts.append(dict(zip(headers, r)) if len(headers) == len(r)
                               else {f"col{i+1}": v for i, v in enumerate(r)})
        elif any(k in joined for k in ("sales", "profit after", "eps", "margin", "growth")):
            periods = headers[1:] if headers and len(headers) == len(rows[0]) else headers
            freq = "quarterly" if any(is_quarter(p) for p in periods) else "annual"
            for r in rows:
                for period, val in zip(periods, r[1:]):
                    num = to_num(val)
                    if num is not None:
                        fin.append((freq, period, r[0], num))

    def after(label_re):
        for i, ln in enumerate(lines):
            if re.fullmatch(label_re, ln, re.I) and i + 1 < len(lines):
                return lines[i + 1]
        return ""

    ff = [lines[i + 1] for i, ln in enumerate(lines)
          if re.fullmatch(r"free float( %| percentage| \(%\))?", ln, re.I) and i + 1 < len(lines)]
    ff_pct = next((v for v in ff if "%" in v), "")
    ff_shares = next((v for v in ff if "%" not in v), "")

    risk = ""
    for ln in lines:
        if re.search(r"risk warning|suspension|delist", ln, re.I):
            risk = ln[:300]
            break

    profile = {
        "market_cap": after(r"market cap(italization)?( \(.*\))?"),
        "shares": after(r"shares( outstanding)?"),
        "free_float_shares": ff_shares,
        "free_float_pct": ff_pct,
        "risk_warning": 1 if risk else 0,
        "risk_text": risk,
    }
    return fin, payouts, profile


def main():
    DATA.mkdir(exist_ok=True)
    debug = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--debug" else None
    with Client(user_agent="psx-personal-analysis/1.0") as psx:
        if debug:
            html = psx._get(f"/company/{debug}", 0, force_refresh=True)
            Path(f"data/_debug_{debug}.html").write_text(html, encoding="utf-8")
            fin, pay, prof = parse_company(html)
            print("financial rows:", len(fin), "| payouts:", len(pay))
            print("profile:", prof)
            print("first rows:", fin[:6])
            return

        symbols = [s["symbol"] for s in psx.symbols()]
        fin_rows, pay_rows, prof_rows, failed = [], [], [], []
        today = date.today().isoformat()
        for i, sym in enumerate(symbols, 1):
            try:
                html = psx._get(f"/company/{sym}", PAGE_TTL)
                fin, pay, prof = parse_company(html)
            except CoolingDown as e:
                print("PSX asked us to slow down, stopping:", e)
                break
            except (NoData, PSXError, OSError):
                failed.append(sym)
                continue
            fin_rows += [(sym, *f) for f in fin]
            pay_rows += [{"symbol": sym, **p} for p in pay]
            prof_rows.append({"symbol": sym, **prof, "fetched_on": today})
            if i % 50 == 0:
                print(f"{i}/{len(symbols)} done", flush=True)

    with_fin = len({r[0] for r in fin_rows})
    if with_fin < 0.3 * len(symbols):
        raise SystemExit(f"Only {with_fin} companies had parsable financials; "
                         "page layout probably changed. Files not overwritten. "
                         "Run: python fetch_extra.py --debug KML")

    with open(DATA / "financials.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "frequency", "period", "metric", "value"])
        w.writerows(fin_rows)

    fields = []
    for r in pay_rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with open(DATA / "payouts.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields or ["symbol"])
        w.writeheader()
        w.writerows(pay_rows)

    with open(DATA / "profiles.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["symbol", "market_cap", "shares", "free_float_shares",
                                          "free_float_pct", "risk_warning", "risk_text", "fetched_on"])
        w.writeheader()
        w.writerows(prof_rows)

    print(f"Financial rows: {len(fin_rows)} for {with_fin} companies; "
          f"payout rows: {len(pay_rows)}; profiles: {len(prof_rows)}")
    if failed:
        print("Failed:", ", ".join(failed))


if __name__ == "__main__":
    main()
