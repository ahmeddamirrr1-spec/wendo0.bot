"""هل فلتر الارتباط (BTC vs ناسداك/ذهب) بيحسّن إشارات السيولة؟
بيقسّم نفس الإشارات حسب حالة الارتباط ويقارن النتايج.
شغّله: python backtest_corr.py            (ناسداك)
       python backtest_corr.py GC=F       (ذهب)
محتاج: pip install yfinance  + ملف strategy.py في نفس المجلد."""
import sys
import numpy as np
import pandas as pd
import yfinance as yf
from strategy import fetch_history, build_signals

HIGH = 0.5     # حد الارتباط العالي
WINDOW = 30    # نافذة الارتباط المتحرك (أيام تداول)
H = 12         # أفق الخروج (12 شمعة = 3 ساعات على 15 دقيقة). أفق واحد عمدا لتقليل التلاعب بالنتايج
FEE = 0.001


def daily_corr(other):
    px = yf.download(["BTC-USD", other], period="2y", auto_adjust=True)["Close"].dropna()
    px.index = pd.to_datetime(px.index).tz_localize(None)
    ret = np.log(px / px.shift(1)).dropna()
    # shift(1): قيمة اليوم محسوبة من بيانات لحد امبارح فقط (بدون تلصص على المستقبل)
    return ret["BTC-USD"].rolling(WINDOW).corr(ret[other]).shift(1).dropna()


def attach_corr(df, corr):
    dates = df["time"].dt.normalize()
    cal = pd.date_range(corr.index.min(), dates.max())
    df["corr"] = dates.map(corr.reindex(cal).ffill())  # أيام العطلة تاخد آخر قيمة معروفة
    return df


def evaluate(df, s, mask, a, b):
    entry = df.o.shift(-1)
    rng = (df.index >= a) & (df.index < b)
    sel = mask & rng
    rows = []
    for name in s.columns:
        d = 1 if name.endswith("long") else -1
        ret = d * (df.c.shift(-H) / entry - 1) - FEE
        base = ret[sel].mean()
        r = ret[s[name] & sel].dropna()
        if len(r) < 10:
            continue
        rows.append({
            "signal": name, "n": len(r),
            "win%": round((r > 0).mean() * 100, 1),
            "avg%": round(r.mean() * 100, 3),
            "edge%": round((r.mean() - base) * 100, 3),
        })
    return pd.DataFrame(rows).sort_values("edge%", ascending=False) if rows else pd.DataFrame()


if __name__ == "__main__":
    other = sys.argv[1] if len(sys.argv) > 1 else "^IXIC"
    df = fetch_history("BTCUSDT", "15m", 180)
    df = attach_corr(df, daily_corr(other))
    s = build_signals(df)

    regimes = {
        f"ارتباط عالي (>= {HIGH})": df["corr"] >= HIGH,
        f"ارتباط ضعيف (< {HIGH})": df["corr"] < HIGH,
    }
    cut = int(len(df) * 0.7)
    for part, (a, b) in {"تدريب": (0, cut), "اختبار": (cut, len(df))}.items():
        for rname, mask in regimes.items():
            print(f"\n=== BTC vs {other} | {part} | {rname} | شموع: {int((mask & (df.index >= a) & (df.index < b)).sum())} ===")
            out = evaluate(df, s, mask, a, b)
            print(out.to_string(index=False) if not out.empty else "(إشارات قليلة جدا)")
