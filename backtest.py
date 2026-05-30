#!/usr/bin/env python3
"""
GAUSS FLEX $180 — Backtest Local
Busca candles da MEXC e simula a estrategia FLEX completa.

Uso:
  python backtest.py BTCUSDT --tf 15m --limit 1000
  python backtest.py ETHUSDT --tf 1h  --capital 500
  python backtest.py SOLUSDT --tf 4h  --score 50 --adx 20 --no-short

Dependencias:
  pip install requests pandas numpy matplotlib
"""

import argparse
import math
import sys

import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec

# ─────────────────────────────────────────────────────────────────────────────
# DEFAULTS
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_CAPITAL     = 180.0
DEFAULT_RISK_PCT    = 0.02    # 2% por trade
DEFAULT_COMMISSION  = 0.001   # 0.1% por lado
DEFAULT_STOP_MULT   = 1.5
DEFAULT_TP1_MULT    = 2.0
DEFAULT_TP2_MULT    = 3.5
DEFAULT_TP1_FRAC    = 0.5     # fecha 50% no TP1
DEFAULT_SCORE       = 50
DEFAULT_ADX         = 20.0
DEFAULT_USE_SHORT   = True
DEFAULT_USE_BE      = True    # move stop para breakeven apos TP1


# ─────────────────────────────────────────────────────────────────────────────
# DADOS — MEXC REST API
# ─────────────────────────────────────────────────────────────────────────────
MEXC_IV = {
    "1m":"1m","3m":"3m","5m":"5m","15m":"15m","30m":"30m",
    "1h":"60m","4h":"240m","1d":"1d","1w":"1w",
}

def fetch_mexc(symbol: str, interval: str, limit: int = 1000) -> pd.DataFrame:
    iv = MEXC_IV.get(interval, interval)
    r  = requests.get(
        "https://api.mexc.com/api/v3/klines",
        params={"symbol": symbol, "interval": iv, "limit": limit},
        timeout=15,
    )
    r.raise_for_status()
    df = pd.DataFrame(r.json(), columns=[
        "ts","open","high","low","close","volume",
        "close_time","quote_vol","trades","tb","tq","ign",
    ])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    for col in ("open","high","low","close","volume"):
        df[col] = df[col].astype(float)
    return df.set_index("ts")[["open","high","low","close","volume"]]


# ─────────────────────────────────────────────────────────────────────────────
# INDICADORES
# ─────────────────────────────────────────────────────────────────────────────
def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def _rma(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(alpha=1 / n, adjust=False).mean()

def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"]  - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    return _rma(tr, n)

def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    return 100 - 100 / (1 + _rma(d.clip(lower=0), n) / _rma((-d).clip(lower=0), n))

def _macd(s: pd.Series, fast=12, slow=26, sig=9):
    m = _ema(s, fast) - _ema(s, slow)
    sg = _ema(m, sig)
    return m, sg, m - sg

def _dmi(df: pd.DataFrame, n: int = 14, sm: int = 14):
    up   = df["high"].diff()
    down = -df["low"].diff()
    pdm  = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    mdm  = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    tr   = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"]  - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    atr_ = _rma(tr, n)
    pdi  = 100 * _rma(pdm, n) / atr_
    mdi  = 100 * _rma(mdm, n) / atr_
    dx   = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return pdi, mdi, _rma(dx.fillna(0), sm)

def _kalman(s: pd.Series, length: int) -> pd.Series:
    m_err = 0.01 * length
    est, e_err = s.iloc[0], 1.0
    out = []
    for v in s:
        gain  = e_err / (e_err + m_err)
        est   = est + gain * (v - est)
        e_err = (1 - gain) * e_err + 0.1 / length
        out.append(est)
    return pd.Series(out, index=s.index)

def _alma(s: pd.Series, length=50, offset=0.85, sigma=6) -> pd.Series:
    m = math.floor(offset * (length - 1))
    sc = length / sigma
    w  = np.array([math.exp(-((i - m) ** 2) / (2 * sc * sc)) for i in range(length)])
    w /= w.sum()
    return s.rolling(length).apply(lambda x: (x * w).sum(), raw=True)

def _ha(df: pd.DataFrame):
    ha_c = (df["open"] + df["high"] + df["low"] + df["close"]) / 4
    ha_o = ha_c.copy()
    ha_o.iloc[0] = (df["open"].iloc[0] + df["close"].iloc[0]) / 2
    for i in range(1, len(df)):
        ha_o.iloc[i] = (ha_o.iloc[i - 1] + ha_c.iloc[i - 1]) / 2
    return ha_o, ha_c

def _obv(df: pd.DataFrame) -> pd.Series:
    return (np.sign(df["close"].diff()).fillna(0) * df["volume"]).cumsum()


# ─────────────────────────────────────────────────────────────────────────────
# CONSTRUCAO DE SINAIS
# ─────────────────────────────────────────────────────────────────────────────
def build_signals(df: pd.DataFrame) -> pd.DataFrame:
    c = df["close"]

    df["ema10"]  = _ema(c, 10)
    df["ema21"]  = _ema(c, 21)
    df["ema50"]  = _ema(c, 50)
    df["ema200"] = _ema(c, 200)

    df["kfast"] = _kalman(c, 50)
    df["kslow"]  = _kalman(c, 150)
    ksp = df["kfast"] - df["kslow"]
    df["kalman_up"]    = df["kfast"] > df["kslow"]
    df["kalman_dn"]    = df["kfast"] < df["kslow"]
    df["ka_accel_up"]  = (ksp > ksp.shift()) & (ksp > 0)
    df["ka_accel_dn"]  = (ksp < ksp.shift()) & (ksp < 0)

    pch = c.pct_change().fillna(0) * 100
    avpch = _alma(pch, 50, 0.85, 6)
    rms_t = avpch.rolling(50).apply(lambda x: math.sqrt((x ** 2).mean()), raw=True)
    df["tr_long"]  = avpch > rms_t
    df["tr_short"] = avpch < -rms_t

    ml, sl_m, hist = _macd(c)
    df["macd_bull"]  = (ml > sl_m) & (hist > hist.shift()) & (hist > 0)
    df["macd_bear"]  = (ml < sl_m) & (hist < hist.shift()) & (hist < 0)
    df["macd_bull_r"] = ml > sl_m
    df["macd_bear_r"] = ml < sl_m

    ha_o, ha_c = _ha(df)
    df["ha_bull"] = (ha_c > ha_o) & (ha_c.shift() > ha_o.shift())
    df["ha_bear"] = (ha_c < ha_o) & (ha_c.shift() < ha_o.shift())

    _, _, adx_ = _dmi(df, 14, 14)
    df["adx"] = adx_

    df["rsi"]        = _rsi(c, 14)
    df["rsi_bull"]   = (df["rsi"] > 50) & (df["rsi"] < 70)
    df["rsi_bear"]   = (df["rsi"] > 30) & (df["rsi"] < 50)
    df["rsi_ok_l"]   = df["rsi"] < 75
    df["rsi_ok_s"]   = df["rsi"] > 25

    vm = df["volume"].rolling(20).mean()
    df["v_strong"] = df["volume"] > vm * 1.1

    spread   = (df["high"] - df["low"]).clip(lower=1e-12)
    flow_raw = ((c - df["open"]) / spread) * df["volume"]
    flow_e   = _ema(flow_raw, 13)
    flow_sma = flow_e.abs().rolling(20).mean()
    df["f_bull"]   = flow_e > 0
    df["f_bear"]   = flow_e < 0
    df["f_strong"] = flow_e.abs() > flow_sma * 1.2

    obv_ = _obv(df)
    obv_e = _ema(obv_, 20)
    df["obv_bull"] = (obv_ > obv_e) & (obv_ > obv_.shift(5))
    df["obv_bear"] = (obv_ < obv_e) & (obv_ < obv_.shift(5))

    cum_pv = (c * df["volume"]).cumsum()
    cum_v  = df["volume"].cumsum()
    df["above_vwap"] = c > (cum_pv / cum_v)

    df["e200_up"] = df["ema200"] > df["ema200"].shift(4)
    df["e200_dn"] = df["ema200"] < df["ema200"].shift(4)

    df["trend_bull"] = (c > df["ema200"]) & (df["ema10"] > df["ema21"]) & (df["ema21"] > df["ema50"]) & (df["ema50"] > df["ema200"])
    df["trend_bear"] = (c < df["ema200"]) & (df["ema10"] < df["ema21"]) & (df["ema21"] < df["ema50"]) & (df["ema50"] < df["ema200"])
    df["tb_loose"]   = (df["ema10"] > df["ema21"]) & (df["ema21"] > df["ema50"])
    df["tbr_loose"]  = (df["ema10"] < df["ema21"]) & (df["ema21"] < df["ema50"])

    bc = sum((c.shift(i) > df["ema21"].shift(i)).astype(int) for i in range(5))
    df["tr_cons_bull"] = bc >= 4
    df["tr_cons_bear"] = bc <= 1

    return df


# ─────────────────────────────────────────────────────────────────────────────
# SCORE FLEX
# ─────────────────────────────────────────────────────────────────────────────
def compute_score(df: pd.DataFrame) -> pd.Series:
    s = pd.Series(0.0, index=df.index)
    s += df["trend_bull"].astype(int) * 35 - df["trend_bear"].astype(int) * 35
    s += df["f_bull"].astype(int) * 15 - df["f_bear"].astype(int) * 15
    s += df["f_strong"].astype(int) * 10
    s += df["macd_bull"].astype(int) * 20 - df["macd_bear"].astype(int) * 20
    s += np.where(df["adx"] > 30, 20, np.where(df["adx"] > 22, 10, 0))
    s += np.where(df["v_strong"], 10, -5)
    s += df["rsi_bull"].astype(int) * 10 - df["rsi_bear"].astype(int) * 10
    s += df["e200_up"].astype(int) * 10  - df["e200_dn"].astype(int) * 10
    s += df["kalman_up"].astype(int) * 10 - df["kalman_dn"].astype(int) * 10
    s += df["obv_bull"].astype(int) * 15 - df["obv_bear"].astype(int) * 15
    s += np.where(df["above_vwap"], 5, -5)
    s += df["ha_bull"].astype(int) * 10 - df["ha_bear"].astype(int) * 10
    s += df["ka_accel_up"].astype(int) * 5 - df["ka_accel_dn"].astype(int) * 5
    s += df["tr_cons_bull"].astype(int) * 5 - df["tr_cons_bear"].astype(int) * 5
    s += df["tr_long"].astype(int) * 10 - df["tr_short"].astype(int) * 10
    base = s.clip(-145, 145)
    fb = np.where(df["tb_loose"] & ~df["trend_bull"], 30, 0)
    fs = np.where(df["tbr_loose"] & ~df["trend_bear"], 30, 0)
    return base + fb - fs


# ─────────────────────────────────────────────────────────────────────────────
# MOTOR DE BACKTEST
# ─────────────────────────────────────────────────────────────────────────────
def run_backtest(
    df: pd.DataFrame,
    capital: float,
    risk_pct: float,
    commission: float,
    stop_mult: float,
    tp1_mult: float,
    tp2_mult: float,
    tp1_frac: float,
    score_thresh: int,
    adx_thresh: float,
    use_short: bool,
    use_be: bool,
) -> dict:

    df = build_signals(df.copy())
    df["score"] = compute_score(df)
    atr14 = _atr(df, 14)

    long_ok  = (df["score"] > score_thresh) & df["macd_bull_r"] & (df["adx"] > adx_thresh) & df["rsi_ok_l"] & df["tr_long"]
    short_ok = (df["score"] < -score_thresh) & df["macd_bear_r"] & (df["adx"] > adx_thresh) & df["rsi_ok_s"] & df["tr_short"]

    new_long  = long_ok  & ~long_ok.shift(fill_value=False)
    new_short = short_ok & ~short_ok.shift(fill_value=False) & use_short

    equity  = capital
    trades  = []
    eq_vals = np.full(len(df), capital)

    pos     = 0       # 0 flat | 1 long | -1 short
    entry   = 0.0
    stop_p  = 0.0
    tp1_p   = 0.0
    tp2_p   = 0.0
    qty     = 0.0     # units (base asset)
    qty_rem = 0.0
    be_set  = False
    tp1_booked = 0.0  # PnL already booked at TP1

    WARMUP = 200

    for i in range(WARMUP, len(df)):
        row   = df.iloc[i]
        ts    = df.index[i]
        h, lo, c = row["high"], row["low"], row["close"]

        # ── Manage open position ──────────────────────────────────────────
        if pos == 1:
            # TP1
            if not be_set and h >= tp1_p:
                pnl1 = (tp1_p - entry) * qty * tp1_frac * (1 - 2 * commission)
                equity     += pnl1
                tp1_booked  = pnl1
                qty_rem     = qty * (1 - tp1_frac)
                if use_be:
                    stop_p = entry
                be_set = True

            # TP2
            if h >= tp2_p:
                pnl2 = (tp2_p - entry) * qty_rem * (1 - 2 * commission)
                equity += pnl2
                trades.append({"ts": ts, "dir": "L", "entry": entry,
                                "exit": tp2_p, "pnl": tp1_booked + pnl2, "result": "TP2"})
                pos = 0; be_set = False; tp1_booked = 0.0
            # SL / BE
            elif lo <= stop_p:
                pnl_sl = (stop_p - entry) * qty_rem * (1 - 2 * commission)
                equity += pnl_sl
                res = "BE" if be_set else "SL"
                trades.append({"ts": ts, "dir": "L", "entry": entry,
                                "exit": stop_p, "pnl": tp1_booked + pnl_sl, "result": res})
                pos = 0; be_set = False; tp1_booked = 0.0

        elif pos == -1:
            # TP1
            if not be_set and lo <= tp1_p:
                pnl1 = (entry - tp1_p) * qty * tp1_frac * (1 - 2 * commission)
                equity     += pnl1
                tp1_booked  = pnl1
                qty_rem     = qty * (1 - tp1_frac)
                if use_be:
                    stop_p = entry
                be_set = True

            # TP2
            if lo <= tp2_p:
                pnl2 = (entry - tp2_p) * qty_rem * (1 - 2 * commission)
                equity += pnl2
                trades.append({"ts": ts, "dir": "S", "entry": entry,
                                "exit": tp2_p, "pnl": tp1_booked + pnl2, "result": "TP2"})
                pos = 0; be_set = False; tp1_booked = 0.0
            # SL / BE
            elif h >= stop_p:
                pnl_sl = (entry - stop_p) * qty_rem * (1 - 2 * commission)
                equity += pnl_sl
                res = "BE" if be_set else "SL"
                trades.append({"ts": ts, "dir": "S", "entry": entry,
                                "exit": stop_p, "pnl": tp1_booked + pnl_sl, "result": res})
                pos = 0; be_set = False; tp1_booked = 0.0

        # ── Nova entrada ──────────────────────────────────────────────────
        if pos == 0:
            a = atr14.iloc[i]
            if new_long.iloc[i]:
                risk_usd = equity * risk_pct
                entry    = c
                stop_p   = c - a * stop_mult
                risk_r   = c - stop_p
                if risk_r <= 0:
                    pass
                else:
                    tp1_p    = c + risk_r * tp1_mult
                    tp2_p    = c + risk_r * tp2_mult
                    qty      = risk_usd / risk_r
                    qty_rem  = qty
                    be_set   = False
                    tp1_booked = 0.0
                    pos      = 1

            elif new_short.iloc[i]:
                risk_usd = equity * risk_pct
                entry    = c
                stop_p   = c + a * stop_mult
                risk_r   = stop_p - c
                if risk_r <= 0:
                    pass
                else:
                    tp1_p    = c - risk_r * tp1_mult
                    tp2_p    = c - risk_r * tp2_mult
                    qty      = risk_usd / risk_r
                    qty_rem  = qty
                    be_set   = False
                    tp1_booked = 0.0
                    pos      = -1

        eq_vals[i] = equity

    for i in range(WARMUP):
        eq_vals[i] = capital

    eq_series = pd.Series(eq_vals, index=df.index)
    return {"trades": trades, "equity": eq_series, "df": df}


# ─────────────────────────────────────────────────────────────────────────────
# METRICAS
# ─────────────────────────────────────────────────────────────────────────────
def calc_metrics(trades: list, equity: pd.Series, capital: float) -> dict:
    if not trades:
        return {"Trades": 0}

    pnls   = [t["pnl"] for t in trades]
    wins   = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gp     = sum(wins)
    gl     = abs(sum(losses)) or 1e-9

    peak  = equity.cummax()
    dd    = (equity - peak) / peak * 100
    max_dd = dd.min()

    return {
        "Trades":         len(trades),
        "Win rate":       f"{len(wins)/len(trades)*100:.1f}%",
        "Profit factor":  f"{gp/gl:.2f}",
        "PnL liquido":    f"${sum(pnls):.2f}",
        "Retorno":        f"{(equity.iloc[-1]-capital)/capital*100:.1f}%",
        "Max drawdown":   f"{max_dd:.1f}%",
        "Media ganho":    f"${sum(wins)/len(wins):.2f}" if wins else "—",
        "Media perda":    f"${sum(losses)/len(losses):.2f}" if losses else "—",
        "TP2 atingidos":  sum(1 for t in trades if t["result"] == "TP2"),
        "Breakeven":      sum(1 for t in trades if t["result"] == "BE"),
        "Stop loss":      sum(1 for t in trades if t["result"] == "SL"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# GRAFICO
# ─────────────────────────────────────────────────────────────────────────────
BG = "#0d1117"
FG = "#c9d1d9"

def plot_results(result: dict, symbol: str, tf: str, met: dict, output: str):
    df     = result["df"]
    eq     = result["equity"]
    trades = result["trades"]
    c      = df["close"]

    fig = plt.figure(figsize=(18, 11), facecolor=BG)
    gs  = GridSpec(3, 1, figure=fig, height_ratios=[3, 1, 1.2], hspace=0.06)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2], sharex=ax1)

    for ax in (ax1, ax2, ax3):
        ax.set_facecolor(BG)
        ax.tick_params(colors=FG, labelsize=7)
        for sp in ax.spines.values():
            sp.set_color("#30363d")

    # ── Preco + EMAs ─────────────────────────────────────────────────────
    ax1.plot(df.index, c,          color="#555",    lw=0.5, label="Close")
    ax1.plot(df.index, df["ema10"],  color="#00e676", lw=0.8, alpha=0.7, label="EMA10")
    ax1.plot(df.index, df["ema21"],  color="#f44336", lw=0.8, alpha=0.7, label="EMA21")
    ax1.plot(df.index, df["ema50"],  color="#ffeb3b", lw=1.2, label="EMA50")
    ax1.plot(df.index, df["ema200"], color="#ffffff", lw=1.8, label="EMA200")
    ax1.plot(df.index, df["kfast"],  color="#00bcd4", lw=0.8, alpha=0.55, label="K-Fast")
    ax1.plot(df.index, df["kslow"],  color="#9c27b0", lw=0.8, alpha=0.55, label="K-Slow")

    for t in trades:
        if t["dir"] == "L":
            ax1.scatter(t["ts"], t["entry"], color="#00e676", marker="^", s=60, zorder=5)
        else:
            ax1.scatter(t["ts"], t["entry"], color="#f44336", marker="v", s=60, zorder=5)

    ax1.set_ylabel("Preco", color=FG, fontsize=8)
    ax1.legend(loc="upper left", fontsize=6, facecolor=BG, labelcolor=FG, framealpha=0.5, ncol=4)
    ax1.set_title(f"GAUSS FLEX — {symbol}  {tf}  |  Capital inicial: ${eq.iloc[0]:.0f}",
                  color="#e6edf3", fontsize=12, pad=6)

    # ── Score ─────────────────────────────────────────────────────────────
    score = df["score"]
    ax2.fill_between(df.index, score, 0, where=score >= 0, color="#00e676", alpha=0.35)
    ax2.fill_between(df.index, score, 0, where=score <  0, color="#f44336", alpha=0.35)
    ax2.axhline( DEFAULT_SCORE, color="#00e676", lw=0.6, ls="--", alpha=0.6)
    ax2.axhline(-DEFAULT_SCORE, color="#f44336", lw=0.6, ls="--", alpha=0.6)
    ax2.axhline(0, color="#444", lw=0.5)
    ax2.set_ylabel("Score", color=FG, fontsize=8)
    ax2.set_ylim(-160, 160)

    # ── Equity ────────────────────────────────────────────────────────────
    init    = eq.iloc[0]
    profit  = eq.iloc[-1] >= init
    eq_col  = "#00e676" if profit else "#f44336"
    ax3.fill_between(eq.index, eq, init,
                     where=eq >= init, color="#00e676", alpha=0.25)
    ax3.fill_between(eq.index, eq, init,
                     where=eq <  init, color="#f44336", alpha=0.25)
    ax3.plot(eq.index, eq, color=eq_col, lw=1.3)
    ax3.axhline(init, color="#444", lw=0.6, ls="--")
    ax3.set_ylabel("Equity ($)", color=FG, fontsize=8)
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%d/%b"))
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=30, ha="right")

    # ── Painel de metricas ────────────────────────────────────────────────
    lines = [f"{k}: {v}" for k, v in met.items()]
    col1  = "  |  ".join(lines[:6])
    col2  = "  |  ".join(lines[6:])
    fig.text(0.01, 0.005, col1 + "\n" + col2,
             fontsize=7, color=FG, family="monospace",
             ha="left", va="bottom")

    plt.tight_layout(rect=[0, 0.04, 1, 1])
    plt.savefig(output, dpi=150, bbox_inches="tight", facecolor=BG)
    print(f"\nGrafico salvo: {output}")
    plt.show()


# ─────────────────────────────────────────────────────────────────────────────
# RELATORIO DE TRADES
# ─────────────────────────────────────────────────────────────────────────────
def print_trades(trades: list):
    if not trades:
        print("Nenhum trade executado.")
        return
    print(f"\n{'Data/Hora':<22} {'Dir':<5} {'Entrada':>10} {'Saida':>10} {'PnL $':>10} {'Resultado'}")
    print("─" * 70)
    for t in trades:
        ts_str = t["ts"].strftime("%d/%m/%Y %H:%M")
        print(f"{ts_str:<22} {t['dir']:<5} {t['entry']:>10.4f} {t['exit']:>10.4f} "
              f"{t['pnl']:>+10.2f}  {t['result']}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="GAUSS FLEX $180 — Backtest Local",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    ap.add_argument("symbol",      nargs="?", default="BTCUSDT",
                    help="Par MEXC (ex: BTCUSDT, ETHUSDT)")
    ap.add_argument("--tf",        default="15m",
                    help="Timeframe: 1m 5m 15m 1h 4h 1d  (padrao: 15m)")
    ap.add_argument("--limit",     type=int,   default=1000,
                    help="Numero de candles — max 1000  (padrao: 1000)")
    ap.add_argument("--capital",   type=float, default=DEFAULT_CAPITAL,
                    help="Capital inicial USD  (padrao: 180)")
    ap.add_argument("--risk",      type=float, default=DEFAULT_RISK_PCT,
                    help="Risco por trade 0-1  (padrao: 0.02 = 2%%)")
    ap.add_argument("--stop",      type=float, default=DEFAULT_STOP_MULT,
                    help="Stop em multiplos de ATR  (padrao: 1.5)")
    ap.add_argument("--tp1",       type=float, default=DEFAULT_TP1_MULT,
                    help="TP1 em multiplos do risco  (padrao: 2.0)")
    ap.add_argument("--tp2",       type=float, default=DEFAULT_TP2_MULT,
                    help="TP2 em multiplos do risco  (padrao: 3.5)")
    ap.add_argument("--score",     type=int,   default=DEFAULT_SCORE,
                    help="Score minimo para entrada  (padrao: 50)")
    ap.add_argument("--adx",       type=float, default=DEFAULT_ADX,
                    help="ADX minimo para entrada  (padrao: 20)")
    ap.add_argument("--no-short",  action="store_true",
                    help="Desativa operacoes SHORT")
    ap.add_argument("--no-be",     action="store_true",
                    help="Desativa breakeven apos TP1")
    ap.add_argument("--no-trades", action="store_true",
                    help="Nao imprime lista de trades")
    ap.add_argument("--output",    default="backtest_result.png",
                    help="Nome do arquivo de saida do grafico")
    args = ap.parse_args()

    sym = args.symbol.upper()
    if not sym.endswith("USDT"):
        sym += "USDT"

    print(f"\nGAUSS FLEX Backtest  —  {sym}  {args.tf}  ({args.limit} candles)")
    print(f"Capital: ${args.capital:.2f}  |  Risco: {args.risk*100:.1f}%  |  "
          f"Stop: {args.stop}xATR  |  TP1: {args.tp1}R  TP2: {args.tp2}R")
    print(f"Score min: {args.score}  |  ADX min: {args.adx}  |  "
          f"Short: {'sim' if not args.no_short else 'nao'}  |  "
          f"Breakeven: {'sim' if not args.no_be else 'nao'}")
    print("─" * 65)
    print("Buscando dados da MEXC...")

    try:
        df = fetch_mexc(sym, args.tf, args.limit)
    except Exception as e:
        print(f"Erro ao buscar dados: {e}")
        sys.exit(1)

    print(f"Candles: {len(df)}  de {df.index[0].strftime('%d/%m/%Y')} "
          f"ate {df.index[-1].strftime('%d/%m/%Y')}")
    print("Calculando indicadores...")

    result = run_backtest(
        df,
        capital=args.capital,
        risk_pct=args.risk,
        commission=DEFAULT_COMMISSION,
        stop_mult=args.stop,
        tp1_mult=args.tp1,
        tp2_mult=args.tp2,
        tp1_frac=DEFAULT_TP1_FRAC,
        score_thresh=args.score,
        adx_thresh=args.adx,
        use_short=not args.no_short,
        use_be=not args.no_be,
    )

    met = calc_metrics(result["trades"], result["equity"], args.capital)

    print(f"\n{'=' * 45}")
    print(f"  RESULTADO — {sym}  {args.tf}")
    print(f"{'=' * 45}")
    for k, v in met.items():
        print(f"  {k:<22} {v}")
    print(f"  {'Equity final':<22} ${result['equity'].iloc[-1]:.2f}")
    print(f"{'=' * 45}")

    if not args.no_trades:
        print_trades(result["trades"])

    if result["trades"]:
        plot_results(result, sym, args.tf, met, args.output)
    else:
        print("\nNenhum trade — ajuste os parametros (--score, --adx, --tf).")


if __name__ == "__main__":
    main()
