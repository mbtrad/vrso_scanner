"""
VRSO SCANNER — DIAGNOSE SCRIPT
===============================
Draai dit om te zien waar de scanner vastloopt.
Toont per stap hoeveel tickers overleven.

Gebruik:
  python diagnose.py

Of via GitHub Actions: voeg toe als workflow_dispatch job.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

# ── Test tickers (kleine set voor snelle diagnose) ──────────
TEST_TICKERS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
    "META", "TSLA", "JPM", "V", "UNH",
    "COST", "HD", "MA", "AVGO", "LLY"
]

CONFIG = {
    "ema_fast": 21, "ema_slow": 50, "ema_trend": 200,
    "rsi_period": 14, "rsi_min": 30, "rsi_max": 70,
    "vol_ma_period": 50, "atr_period": 14, "rs_period": 63,
    "vol_dry_threshold": 0.85, "pullback_max_pct": 0.05,
    "rs_slope_weak": 0.0, "atr_multiplier": 2.0,
    "max_stop_pct": 0.10, "min_score": 5.0,
}

def calc_ema(s, p): return s.ewm(span=p, adjust=False).mean()
def calc_rsi(s, p=14):
    d = s.diff()
    g = d.clip(lower=0).rolling(p).mean()
    l = (-d.clip(upper=0)).rolling(p).mean()
    return 100 - (100 / (1 + g / l.replace(0, np.nan)))
def calc_atr(h, l, c, p=14):
    tr = pd.concat([(h-l), (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(p).mean()

def sep(title=""):
    print(f"\n{'─'*55}")
    if title: print(f"  {title}")
    print('─'*55)

# ══════════════════════════════════════════════════════════
sep("STAP 1 — DATA DOWNLOAD")
# ══════════════════════════════════════════════════════════

start = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")

print(f"\nSPY ophalen...")
spy_raw = yf.download("SPY", start=start, progress=False, auto_adjust=True)
print(f"  SPY rijen: {len(spy_raw)}")
print(f"  SPY kolommen: {list(spy_raw.columns)}")
spy_close = spy_raw["Close"].squeeze()
print(f"  SPY close type: {type(spy_close).__name__}, shape: {spy_close.shape}")

print(f"\nTest tickers downloaden ({len(TEST_TICKERS)} tickers)...")
raw = yf.download(
    TEST_TICKERS, start=start, progress=False,
    auto_adjust=True, group_by="ticker", threads=True
)
print(f"  Raw columns type: {type(raw.columns).__name__}")
print(f"  Raw shape: {raw.shape}")
if hasattr(raw.columns, 'levels'):
    print(f"  MultiIndex levels: {[list(l) for l in raw.columns.levels]}")
else:
    print(f"  Columns: {list(raw.columns)[:10]}")

# ══════════════════════════════════════════════════════════
sep("STAP 2 — TICKER PARSING")
# ══════════════════════════════════════════════════════════

parsed = {}
parse_errors = []

for ticker in TEST_TICKERS:
    try:
        if isinstance(raw.columns, pd.MultiIndex):
            # Probeer beide methoden
            try:
                df = raw[ticker].copy()
                df.dropna(subset=["Close"], inplace=True)
                if len(df) > 10:
                    parsed[ticker] = df
                    print(f"  ✅ {ticker}: {len(df)} rijen via raw[ticker]")
                else:
                    parse_errors.append((ticker, f"Te weinig rijen: {len(df)}"))
                    print(f"  ⚠️  {ticker}: slechts {len(df)} rijen")
            except Exception as e1:
                # Alternatieve methode: xs
                try:
                    df = raw.xs(ticker, axis=1, level=0).copy()
                    df.dropna(subset=["Close"], inplace=True)
                    parsed[ticker] = df
                    print(f"  ✅ {ticker}: {len(df)} rijen via xs()")
                except Exception as e2:
                    parse_errors.append((ticker, str(e2)))
                    print(f"  ❌ {ticker}: {e2}")
        else:
            # Enkele ticker of flat columns
            df = raw.copy()
            df.dropna(subset=["Close"], inplace=True)
            if len(df) > 10:
                parsed[ticker] = df
                print(f"  ✅ {ticker}: {len(df)} rijen (flat)")
            else:
                parse_errors.append((ticker, "Te weinig rijen"))
    except Exception as e:
        parse_errors.append((ticker, str(e)))
        print(f"  ❌ {ticker}: {e}")

print(f"\n  Succesvol geparsed: {len(parsed)}/{len(TEST_TICKERS)}")
if parse_errors:
    print(f"  Parse fouten:")
    for t, e in parse_errors: print(f"    {t}: {e}")

# ══════════════════════════════════════════════════════════
sep("STAP 3 — INDICATOREN")
# ══════════════════════════════════════════════════════════

with_indicators = {}
indicator_errors = []

for ticker, df in parsed.items():
    try:
        c = df["Close"].squeeze()
        h = df["High"].squeeze()
        l = df["Low"].squeeze()
        o = df["Open"].squeeze()
        v = df["Volume"].squeeze()

        df["ema21"]  = calc_ema(c, 21)
        df["ema50"]  = calc_ema(c, 50)
        df["ema200"] = calc_ema(c, 200)
        df["rsi"]    = calc_rsi(c, 14)
        df["atr"]    = calc_atr(h, l, c, 14)
        df["vol_ma"] = v.rolling(50).mean()

        spy_al = spy_close.reindex(df.index, method="ffill").squeeze()
        df["rs"] = c.pct_change(63) - spy_al.pct_change(63)
        df["rs_slope"] = df["rs"].diff(5)
        df["vcp_ratio"] = df["atr"] / df["atr"].rolling(20).mean()
        df.dropna(inplace=True)

        if len(df) > 5:
            with_indicators[ticker] = df
            row = df.iloc[-1]
            print(f"  ✅ {ticker}: close=${float(row['Close']):.2f}  "
                  f"ema50=${float(row['ema50']):.2f}  ema200=${float(row['ema200']):.2f}  "
                  f"rsi={float(row['rsi']):.1f}  rs={float(row['rs'])*100:.2f}%")
        else:
            indicator_errors.append((ticker, "Te weinig rijen na dropna"))
            print(f"  ⚠️  {ticker}: te weinig rijen na dropna")
    except Exception as e:
        indicator_errors.append((ticker, str(e)))
        print(f"  ❌ {ticker}: {e}")

print(f"\n  Met indicatoren: {len(with_indicators)}/{len(parsed)}")

# ══════════════════════════════════════════════════════════
sep("STAP 4 — KNOCKOUT FILTERS (per knockout tellen)")
# ══════════════════════════════════════════════════════════

knocked = {
    "ema50_boven_ema200": 0,
    "prijs_boven_ema50": 0,
    "te_ver_onder_ema50": 0,
    "rs_negatief": 0,
    "geslaagd": 0,
}

for ticker, df in with_indicators.items():
    row = df.iloc[-1]
    price = float(row["Close"])
    e50   = float(row["ema50"])
    e200  = float(row["ema200"])
    rs    = float(row["rs"])

    print(f"\n  {ticker}:")
    print(f"    Prijs=${price:.2f}  EMA50=${e50:.2f}  EMA200=${e200:.2f}  RS={rs*100:.2f}%")

    if not (e50 > e200):
        knocked["ema50_boven_ema200"] += 1
        print(f"    ❌ KNOCKOUT: EMA50 ({e50:.2f}) NIET boven EMA200 ({e200:.2f})")
        continue
    print(f"    ✅ EMA50 boven EMA200")

    if not (price > e50):
        knocked["prijs_boven_ema50"] += 1
        print(f"    ❌ KNOCKOUT: Prijs ({price:.2f}) NIET boven EMA50 ({e50:.2f})")
        continue
    print(f"    ✅ Prijs boven EMA50")

    if price < e50 * (1 - 0.05):
        knocked["te_ver_onder_ema50"] += 1
        print(f"    ❌ KNOCKOUT: Prijs te ver onder EMA50")
        continue

    if rs <= 0:
        knocked["rs_negatief"] += 1
        print(f"    ❌ KNOCKOUT: RS negatief ({rs*100:.2f}%)")
        continue
    print(f"    ✅ RS positief")

    knocked["geslaagd"] += 1
    print(f"    🎯 DOOR ALLE KNOCKOUTS")

sep("STAP 5 — SCORE ANALYSE")

for ticker, df in with_indicators.items():
    row  = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(row["Close"])
    e50   = float(row["ema50"])
    e200  = float(row["ema200"])
    rs    = float(row["rs"])

    # Sla knockouts over
    if not (e50 > e200 and price > e50 and rs > 0):
        continue

    rsi      = float(row["rsi"])
    vol      = float(row["Volume"])
    vol_ma   = float(row["vol_ma"])
    vol_prev = float(prev["Volume"])
    rs_slope = float(row["rs_slope"])
    vcp      = float(row["vcp_ratio"])
    hl       = float(row["higher_low"]) if "higher_low" in row else 0
    o        = float(row["Open"])
    body_pct = (price - o) / o

    scores = {}
    scores["RSI"]       = 2.0 if 30 <= rsi <= 70 else (1.0 if 25 <= rsi <= 75 else 0.0)
    scores["Volume"]    = 2.0 if vol < vol_ma * 0.85 else (1.0 if vol < vol_ma * 0.95 else 0.0)
    scores["RS"]        = 2.0 if rs_slope > 0 else (1.0 if rs_slope > -0.001 else 0.0)
    scores["Body"]      = 1.0 if body_pct > 0.002 else (0.5 if body_pct > 0 else 0.0)
    scores["VolRising"] = 1.0 if vol > vol_prev else 0.0
    scores["HigherLow"] = 0.0  # higher_low berekend in scanner, hier 0
    scores["VCP"]       = 1.0 if vcp < 0.80 else (0.5 if vcp < 0.95 else 0.0)

    total = sum(scores.values())
    print(f"\n  {ticker} — totaalscore: {total:.1f}/10 {'✅' if total >= 5 else '❌'}")
    for k, v in scores.items():
        bar = "█" * int(v * 4) + "░" * (8 - int(v * 4))
        print(f"    {k:12s} {bar} {v:.1f}")

sep("SAMENVATTING")
print(f"\n  Gescande tickers:      {len(TEST_TICKERS)}")
print(f"  Download geslaagd:     {len(parsed)}")
print(f"  Indicatoren ok:        {len(with_indicators)}")
print(f"\n  Knockout analyse:")
for k, v in knocked.items():
    print(f"    {k:25s}: {v}")
print()
print("  → Als 'geslaagd' = 0: knockouts zijn te streng of dataprobeem")
print("  → Als geslaagd > 0 maar scores laag: scoring parameters aanpassen")
print()
