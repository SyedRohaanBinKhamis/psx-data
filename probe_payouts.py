"""Find how PSX serves dividend/payout data. Saves raw responses to data/_probe/.

Run: python probe_payouts.py
Then: git add . ; git commit -m "probe" ; git push   (Claude reads the results)
"""
import socket
from datetime import date, timedelta
from pathlib import Path

from psx_dps import Client
from psx_dps.parsing import table_records

socket.setdefaulttimeout(30)
OUT = Path("data/_probe")
OUT.mkdir(parents=True, exist_ok=True)

today = date.today()
start = (today - timedelta(days=365)).isoformat()
end = today.isoformat()

attempts = {
    "get_payouts": ("/payouts", None),
    "post_payouts_a": ("/payouts", {"symbol": "", "date_from": start, "date_to": end,
                                    "count": "100", "offset": "0", "page": "payouts"}),
    "post_payouts_b": ("/payouts", {"type": "", "symbol": "", "query": "",
                                    "count": "100", "offset": "0",
                                    "date_from": start, "date_to": end}),
    "post_payouts_c": ("/payouts", {"from": start, "to": end}),
    "get_calendar": ("/calendar", None),
    "get_company_kml": ("/company/KTML", None),
}

with Client(user_agent="psx-personal-analysis/1.0") as psx:
    for name, (path, body) in attempts.items():
        try:
            html = psx._get(path, 0, body=body, force_refresh=True)
        except Exception as e:  # noqa: BLE001
            print(f"{name}: FAILED {type(e).__name__}: {e}")
            continue
        (OUT / f"{name}.html").write_text(html, encoding="utf-8")
        try:
            rows = table_records(html)
        except Exception:  # noqa: BLE001
            rows = []
        cols = list(rows[0].keys()) if rows else []
        print(f"{name}: {len(html)} chars, {len(rows)} table rows, columns={cols}")
print("Done. Raw files are in data/_probe/")
