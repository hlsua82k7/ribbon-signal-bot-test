"""
Ribbon MTF Signal Scanner - 主程式

流程：讀 config.yaml -> 依市場/商品/週期逐一掃描 -> 偵測到新的 EMA1xEMA6 交叉訊號
-> 組成含停損停利與多週期趨勢的訊息 -> 傳 Telegram -> 把「這根K棒已通知過」記進 state.json。

設計成「每次執行做一次檢查」(跟 paper_trading_tick.py 同樣的模式)，
狀態存在 state.json，靠 GitHub Actions 排程重複呼叫，不用常駐程式。
"""

import json
import sys
from pathlib import Path

import yaml

# Windows 主控台預設編碼常常不是 UTF-8，訊息裡有中文+emoji 時 print 會直接炸掉；
# 強制 stdout/stderr 用 UTF-8，錯誤時用替代字元而不是整個程式中斷。GitHub Actions(Linux)不受影響。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

import data_providers as dp
import ribbon_core as rc
import telegram_notify as tg

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"
STATE_PATH = BASE_DIR / "state.json"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def save_state(state):
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def process_symbol(market, symbol, timeframe, cfg, state):
    key = f"{market}:{symbol}:{timeframe}"
    exchange = cfg["markets"][market].get("exchange", "okx")
    try:
        df = dp.fetch(market, symbol, timeframe, exchange=exchange)
    except Exception as e:
        print(f"[WARN] {key} 抓資料失敗: {e}")
        return

    min_bars = max(cfg["ribbon"]["ema_lengths"]) + 5
    if len(df) < min_bars:
        print(f"[SKIP] {key} 資料不足({len(df)}根，需要至少{min_bars}根)")
        return

    closed = df.iloc[:-1]  # 排除還沒收盤的最後一根，模擬 Pine 的 barstate.isconfirmed
    ribbon = rc.compute_ribbon(closed, cfg["ribbon"]["ema_lengths"])
    long_sig, short_sig, sig_ts = rc.detect_cross(ribbon)

    if not (long_sig or short_sig):
        print(f"[OK] {key} 無新訊號")
        return

    if state.get(key) == str(sig_ts):
        print(f"[SKIP] {key} 這根K棒({sig_ts})已經通知過了")
        return

    atr_series, atr_pct_series = rc.compute_atr(closed, cfg["risk"]["atr_len"])
    atr_val, atr_pct = atr_series.iloc[-1], atr_pct_series.iloc[-1]
    if atr_val != atr_val:  # NaN != NaN，用來判斷 ATR 是否還沒算出來(資料太短)
        print(f"[SKIP] {key} ATR 尚未算出來(資料太短)")
        return

    direction = "多" if long_sig else "空"
    entry = closed["close"].iloc[-1]
    plan = rc.build_trade_plan(entry, atr_val, direction, cfg["risk"])
    ribbon_state = ribbon["ribbon_state"].iloc[-1]

    ah = cfg["atr_health"]
    atr_ok = ah["low_pct"] <= atr_pct <= ah["high_pct"]

    mtf_lines = []
    for mtf_tf in cfg["mtf"]["timeframes"]:
        try:
            mtf_df = dp.fetch(market, symbol, mtf_tf, exchange=exchange)
            trend = rc.mtf_trend(mtf_df.iloc[:-1], cfg["mtf"]["fast_len"], cfg["mtf"]["slow_len"])
        except Exception as e:
            print(f"[WARN] {key} 抓 MTF({mtf_tf}) 失敗: {e}")
            trend = "N/A"
        mtf_lines.append(f"{mtf_tf}:{trend}")

    msg = rc.format_alert(
        market, symbol, timeframe, direction, ribbon_state, sig_ts,
        entry, plan, atr_pct, atr_ok, mtf_lines, cfg["ribbon"]["ema_lengths"],
    )
    print(f"[SIGNAL] {key}\n{msg}\n")
    tg.send_message(msg, enabled=cfg["telegram"]["enabled"])
    state[key] = str(sig_ts)


def main():
    cfg = load_config()
    state = load_state()

    for market, mcfg in cfg["markets"].items():
        if not mcfg.get("enabled"):
            continue
        for symbol in mcfg["symbols"]:
            for tf in cfg["signal_timeframes"]:
                process_symbol(market, symbol, tf, cfg, state)

    save_state(state)
    print(f"\n狀態已存: {STATE_PATH}")


if __name__ == "__main__":
    main()
