"""Telegram 通知：Token / Chat ID 一律從環境變數讀取，不寫進任何檔案。
本機測試: 建一份 .env (參考 .env.example)，會自動被載入。
GitHub Actions: 在 repo 的 Settings > Secrets and variables > Actions 設定
                TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID，由 workflow 帶進來。
"""

import os
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def send_message(text: str, enabled: bool = True):
    if not enabled:
        print("[Telegram 已停用，僅印出訊息]\n" + text)
        return

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[WARN] 缺少 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 環境變數，訊息未送出:")
        print(text)
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"[WARN] Telegram 傳送失敗: {resp.status_code} {resp.text}")
        else:
            print("[Telegram] 已送出通知")
    except requests.RequestException as e:
        print(f"[WARN] Telegram 傳送發生例外: {e}")
