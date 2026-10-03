
import csv

rows = [r for r in csv.DictReader(open("data/psx_eod.csv", encoding="utf-8")) if r["symbol"] == "TRG"]
if not rows:
    print("TRG not found in data/psx_eod.csv")
else:
    print("symbol  date        open     close    volume")
    for r in rows[-3:]:
        print(f'{r["symbol"]:<7} {r["date"]}  {r["open"]:>7}  {r["close"]:>7}  {r["volume"]:>10}')