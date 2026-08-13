"""
Ribbon MTF Signal - 純運算邏輯 (無 I/O)

把 Pine Script「Ribbon MTF Signal (Alpha-Algo Style)」指標的核心邏輯翻成 Python：
- EMA Ribbon 排列(Bull/Bear/Mix) 與 EMA1 x EMA(最後一條) 交叉訊號
- ATR 與 ATR% 健康區間
- 停損停利計畫(ATR倍數停損 + 分層ATR停利)
- 多週期趨勢(EMA快線 vs 慢線)

所有函式都只吃/吐 pandas DataFrame 或基本型別，方便單獨測試，不碰網路或檔案。
"""

import pandas as pd

MARKET_ZH = {"crypto": "加密貨幣", "us_stocks": "美股", "forex": "外匯"}


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def compute_ribbon(df: pd.DataFrame, ema_lengths: list) -> pd.DataFrame:
    """回傳一份新的 df，欄位: close, e1..eN, ribbon_state(Bull/Bear/Mix)"""
    out = pd.DataFrame(index=df.index)
    out["close"] = df["close"]
    n = len(ema_lengths)
    for i, length in enumerate(ema_lengths, start=1):
        out[f"e{i}"] = ema(df["close"], length)

    e_cols = [f"e{i}" for i in range(1, n + 1)]
    bull = pd.Series(True, index=out.index)
    bear = pd.Series(True, index=out.index)
    for i in range(n - 1):
        bull &= out[e_cols[i]] > out[e_cols[i + 1]]
        bear &= out[e_cols[i]] < out[e_cols[i + 1]]

    out["ribbon_state"] = "Mix"
    out.loc[bull, "ribbon_state"] = "Bull"
    out.loc[bear, "ribbon_state"] = "Bear"
    return out


def detect_cross(ribbon_df: pd.DataFrame):
    """檢查『最後一根K棒』有沒有發生 EMA1 x EMA(最後一條) 交叉(用已收盤資料)。
    回傳 (long_sig, short_sig, signal_ts)"""
    e_cols = [c for c in ribbon_df.columns if c.startswith("e")]
    fast_col, slow_col = e_cols[0], e_cols[-1]
    if len(ribbon_df) < 2:
        return False, False, None

    prev_fast, prev_slow = ribbon_df[fast_col].iloc[-2], ribbon_df[slow_col].iloc[-2]
    cur_fast, cur_slow = ribbon_df[fast_col].iloc[-1], ribbon_df[slow_col].iloc[-1]
    if pd.isna(prev_fast) or pd.isna(prev_slow) or pd.isna(cur_fast) or pd.isna(cur_slow):
        return False, False, None

    long_sig = prev_fast <= prev_slow and cur_fast > cur_slow
    short_sig = prev_fast >= prev_slow and cur_fast < cur_slow
    return long_sig, short_sig, ribbon_df.index[-1]


def compute_atr(df: pd.DataFrame, length: int):
    """回傳 (atr, atr_pct) 兩個 Series，用 Wilder's RMA 平滑，跟 Pine ta.atr 一致"""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift()
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / length, adjust=False).mean()
    atr_pct = atr / close * 100
    return atr, atr_pct


def build_trade_plan(entry: float, atr_val: float, direction: str, risk_cfg: dict):
    """direction: '多' or '空'"""
    stop_mult = risk_cfg["stop_mult"]
    step = risk_cfg["target_step"]
    cnt = risk_cfg["target_cnt"]
    if direction == "多":
        stop = entry - atr_val * stop_mult
        targets = [entry + atr_val * step * i for i in range(1, cnt + 1)]
    else:
        stop = entry + atr_val * stop_mult
        targets = [entry - atr_val * step * i for i in range(1, cnt + 1)]
    return {"entry": entry, "stop": stop, "targets": targets}


def mtf_trend(df: pd.DataFrame, fast_len: int, slow_len: int) -> str:
    if df is None or len(df) < slow_len + 2:
        return "N/A"
    f = ema(df["close"], fast_len).iloc[-1]
    s = ema(df["close"], slow_len).iloc[-1]
    if pd.isna(f) or pd.isna(s):
        return "N/A"
    return "Bull" if f > s else "Bear"


def format_alert(market, symbol, timeframe, direction, ribbon_state, sig_ts,
                  entry, plan, atr_pct, atr_ok, mtf_lines, ema_lengths):
    market_zh = MARKET_ZH.get(market, market)
    emoji = "🟢" if direction == "多" else "🔴"
    dir_zh = "做多" if direction == "多" else "做空"
    n = len(ema_lengths)
    targets = plan["targets"]
    show_n = min(3, len(targets))
    targets_str = " / ".join(f"TP{i+1} {targets[i]:.4f}" for i in range(show_n))
    if len(targets) > show_n:
        targets_str += f" ...(共{len(targets)}層)"

    lines = [
        f"{emoji} <b>[進場訊號] {symbol}</b> ({market_zh} / {timeframe})",
        f"方向: {dir_zh} (EMA1 x EMA{n} 交叉)",
        f"Ribbon 排列: {ribbon_state}",
        f"訊號K棒收盤時間: {sig_ts}",
        f"進場價: {entry:.4f}",
        f"停損: {plan['stop']:.4f}",
        f"目標: {targets_str}",
        f"ATR%: {atr_pct:.2f}% {'✅健康區間內' if atr_ok else '⚠️超出健康區間(僅供參考)'}",
        f"多週期趨勢: {' / '.join(mtf_lines)}",
    ]
    return "\n".join(lines)
