"""
讓使用者直接在 Telegram 跟機器人下指令，設定自己想看的市場/週期，
不用改 config.yaml 再 push。

支援指令：
  /markets crypto,us_stocks,forex   只看指定市場
  /markets all                      恢復成 config.yaml 裡 enabled 的全部市場
  /timeframes 1h,4h                 只看指定週期
  /timeframes all                   恢復成 config.yaml 的 signal_timeframes 全部週期
  /status                           查看目前訂閱設定
  /help / /start                    顯示說明

設定存在 subscriptions.json(每個 chat_id 一份設定)，
處理進度(避免重複處理同一則訊息)存在 telegram_offset.json，
兩個檔案都跟 state.json 一樣由 GitHub Actions workflow 自動 commit 回 repo。
"""

import json
from pathlib import Path

import telegram_notify as tg

BASE_DIR = Path(__file__).parent
SUBS_PATH = BASE_DIR / "subscriptions.json"
OFFSET_PATH = BASE_DIR / "telegram_offset.json"

VALID_TIMEFRAMES = {"15m", "1h", "4h", "1d", "1w"}


def _load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def _save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_subscriptions():
    return _load_json(SUBS_PATH, {})


def save_subscriptions(subs):
    _save_json(SUBS_PATH, subs)


def get_effective_filter(chat_id, cfg):
    """回傳這個 chat_id 目前有效的 (markets清單, timeframes清單)；
    沒特別設定過的話，就用 config.yaml 的預設值(全部enabled的市場 + 全部signal_timeframes)。"""
    subs = load_subscriptions()
    pref = subs.get(str(chat_id), {})
    all_markets = [m for m, mcfg in cfg["markets"].items() if mcfg.get("enabled")]
    all_tfs = cfg["signal_timeframes"]
    markets = pref.get("markets", all_markets)
    timeframes = pref.get("timeframes", all_tfs)
    return markets, timeframes


def _format_status(markets, timeframes):
    return (
        "📋 目前訂閱設定\n"
        f"市場: {', '.join(markets) if markets else '(無)'}\n"
        f"週期: {', '.join(timeframes) if timeframes else '(無)'}\n\n"
        "指令:\n"
        "/markets crypto,us_stocks,forex (或 /markets all)\n"
        "/timeframes 1h,4h,1d (或 /timeframes all，可選 15m/1h/4h/1d/1w)\n"
        "/status 查看目前設定\n"
        "/help 顯示這個說明"
    )


def process_commands(cfg):
    """讀取自上次以來的新訊息、處理指令、更新訂閱設定並回覆使用者。"""
    offset = _load_json(OFFSET_PATH, {"offset": 0}).get("offset", 0)
    updates = tg.get_updates(offset)
    if not updates:
        return

    subs = load_subscriptions()
    max_update_id = offset - 1

    for upd in updates:
        max_update_id = max(max_update_id, upd["update_id"])
        msg = upd.get("message") or upd.get("edited_message")
        if not msg or "text" not in msg:
            continue

        chat_id = str(msg["chat"]["id"])
        text = msg["text"].strip()
        pref = subs.setdefault(chat_id, {})

        if text.startswith("/markets"):
            arg = text[len("/markets"):].strip()
            if not arg:
                tg.send_message_to(chat_id, "用法: /markets crypto,us_stocks,forex 或 /markets all")
            elif arg.lower() == "all":
                pref.pop("markets", None)
                markets, timeframes = get_effective_filter(chat_id, cfg)
                tg.send_message_to(chat_id, "✅ 已恢復成全部市場\n\n" + _format_status(markets, timeframes))
            else:
                names = [s.strip() for s in arg.split(",") if s.strip()]
                invalid = [n for n in names if n not in cfg["markets"]]
                if invalid:
                    tg.send_message_to(
                        chat_id,
                        f"⚠️ 不認得的市場: {invalid}\n可用: {list(cfg['markets'].keys())}",
                    )
                else:
                    pref["markets"] = names
                    markets, timeframes = get_effective_filter(chat_id, cfg)
                    tg.send_message_to(chat_id, "✅ 已更新市場訂閱\n\n" + _format_status(markets, timeframes))

        elif text.startswith("/timeframes"):
            arg = text[len("/timeframes"):].strip()
            if not arg:
                tg.send_message_to(chat_id, "用法: /timeframes 1h,4h,1d 或 /timeframes all")
            elif arg.lower() == "all":
                pref.pop("timeframes", None)
                markets, timeframes = get_effective_filter(chat_id, cfg)
                tg.send_message_to(chat_id, "✅ 已恢復成全部週期\n\n" + _format_status(markets, timeframes))
            else:
                tfs = [s.strip() for s in arg.split(",") if s.strip()]
                invalid = [t for t in tfs if t not in VALID_TIMEFRAMES]
                if invalid:
                    tg.send_message_to(
                        chat_id,
                        f"⚠️ 不支援的週期: {invalid}\n可用: {sorted(VALID_TIMEFRAMES)}",
                    )
                else:
                    pref["timeframes"] = tfs
                    markets, timeframes = get_effective_filter(chat_id, cfg)
                    tg.send_message_to(chat_id, "✅ 已更新週期訂閱\n\n" + _format_status(markets, timeframes))

        elif text.startswith("/status") or text.startswith("/help") or text.startswith("/start"):
            markets, timeframes = get_effective_filter(chat_id, cfg)
            tg.send_message_to(chat_id, _format_status(markets, timeframes))

        # 其他不認得的文字/指令直接忽略，不回覆(避免群組裡雜訊)

    save_subscriptions(subs)
    _save_json(OFFSET_PATH, {"offset": max_update_id + 1})
