# Ribbon MTF Signal Scanner

把你的 TradingView 指標「Ribbon MTF Signal (Alpha-Algo Style)」的 EMA Ribbon 進場訊號邏輯
搬到 Python，跑在 GitHub Actions 上做多市場、多商品、多週期掃描，訊號出現就發 Telegram 通知。

## 這套系統做什麼

- **訊號邏輯**：EMA1 x EMA6 交叉(對應原指標的 longSig/shortSig)，只認已收盤的K棒
- **市場**：加密貨幣(OKX)、美股、外匯、台股(yfinance)，各自可獨立開關、自訂商品清單
- **週期**：可自選要在哪些週期上判斷訊號(15m/1h/4h/1d/1w)
- **多週期趨勢共振**：對應原指標的 T(60)/T(240)/T(D)/T(W) 面板，用 EMA快線/慢線判斷各週期 Bull/Bear
- **停損停利**：ATR 倍數停損 + 分層 ATR 停利，跟原指標的風險群組參數一致
- **不重複通知**：每個「商品+週期」記住上一次通知過的K棒時間，同一根不會重複發
- **可以直接在 Telegram 設定想看的市場/週期**：不用改 config.yaml，傳指令給機器人就好(見下方「用 Telegram 指令調整訂閱」)

**這是訊號通知系統，不會下真單、不做回測績效保證，僅供你自己交易時參考。**

## 用 Telegram 指令調整訂閱

直接傳訊息給你的機器人即可，排程下次執行時會自動讀取並套用：

| 指令 | 說明 |
|---|---|
| `/markets crypto,us_stocks,forex,tw_stocks` | 只看指定市場(可用值: `crypto` `us_stocks` `forex` `tw_stocks`) |
| `/markets all` | 恢復成 config.yaml 裡 enabled 的全部市場 |
| `/timeframes 1h,4h` | 只看指定週期(可用值: `15m` `1h` `4h` `1d` `1w`) |
| `/timeframes all` | 恢復成 config.yaml 的 `signal_timeframes` 全部週期 |
| `/status` | 查看目前訂閱設定 |
| `/help` | 顯示指令說明 |

設定存在 repo 的 `subscriptions.json`，套用範圍**只影響你收到的通知**，不影響 `config.yaml` 本身；
如果你想真的改變預設商品清單(例如新增/移除某支股票)，還是要改 `config.yaml`。

⚠️ **預設(polling模式)指令不是即時生效**——排程每15分鐘才跑一次，你傳指令後最多要等到下次排程執行
才會套用、才會收到確認回覆。想要幾秒內就生效，見下面「即時指令(Webhook模式)」。

## 即時指令(Webhook模式，選用)

預設的 polling 模式最多要等15分鐘，如果想要「傳指令後幾秒內就生效」，需要多部署一個免費的
**Cloudflare Worker** 當「即時轉發器」：Telegram 一收到你的訊息就會立刻通知這個 Worker，
Worker 馬上叫 GitHub Actions 觸發一次，只處理這一則指令(不做完整市場掃描，很快)。
完整市場掃描完全不受影響，還是照原本排程每15分鐘跑一次。

程式碼在 `cloudflare-webhook/` 資料夾，步驟：

### 1. 準備 Cloudflare 帳號

沒有的話先到 [dash.cloudflare.com/sign-up](https://dash.cloudflare.com/sign-up) 免費註冊(不用信用卡)。

### 2. 建立 GitHub Personal Access Token

到 GitHub **Settings → Developer settings → Personal access tokens → Fine-grained tokens →
Generate new token**：
- **Repository access**: 只選這個 repo(`ribbon-signal-bot-test`)
- **Permissions**: `Actions` 設成 **Read and write**，其他都不用開
- 設個到期日(例如1年)，到期前記得回來重新產生一組

產生後複製起來，等一下第4步要用——這是敏感金鑰，**不要貼到 config.yaml 或任何會commit的檔案裡**。

### 3. 登入 Cloudflare CLI

```bash
cd cloudflare-webhook
npx wrangler login
```

會跳出瀏覽器要你登入 Cloudflare 帳號並授權，在瀏覽器裡完成就好。

### 4. 設定 Worker 的密鑰

```bash
npx wrangler secret put GITHUB_TOKEN
```
貼上第2步產生的 GitHub Token。

```bash
npx wrangler secret put TG_WEBHOOK_SECRET
```
貼上這組隨機字串(用來驗證請求真的是Telegram送來的，不是隨便誰打這個網址)：

```
vuxxh46-BhOfgkvHIgzgWmeCu9ChGU5d01BNN9sim_0
```

(這組是幫你先產生好的，你也可以自己換一組任意長字串，只要記得跟第6步用的是同一組)

### 5. 部署 Worker

```bash
npx wrangler deploy
```

成功後會印出一個網址，長得像：
```
https://ribbon-signal-bot-webhook.<你的subdomain>.workers.dev
```
複製起來，下一步要用。

### 6. 告訴 Telegram 把訊息送到這個 Worker

瀏覽器打開這個網址(把 `<TOKEN>`、`<WORKER網址>`、`<SECRET>` 換成你的值)：

```
https://api.telegram.org/bot<TOKEN>/setWebhook?url=<WORKER網址>&secret_token=<SECRET>
```

看到 `"ok":true` 就代表設定成功。

### 7. 把 command_mode 切換成 webhook

打開 `config.yaml`，把：
```yaml
telegram:
  command_mode: polling
```
改成：
```yaml
telegram:
  command_mode: webhook
```
`git add config.yaml && git commit -m "切換成webhook即時指令" && git push`

### 8. 測試

傳 `/status` 給機器人，應該幾秒內就會收到回覆(GitHub Actions 頁面會多一次很快結束的執行紀錄)。

### 想改回 polling 模式？

1. 瀏覽器打開 `https://api.telegram.org/bot<TOKEN>/deleteWebhook` 取消 Telegram 端的 webhook
2. `config.yaml` 的 `command_mode` 改回 `polling`，commit、push

## 檔案結構

```
config.yaml           # 市場/商品/週期/風險參數，全部設定都在這裡改
ribbon_core.py         # 核心運算(EMA、ATR、交叉偵測、停損停利、訊息格式)
data_providers.py      # 抓資料(ccxt / yfinance)
telegram_notify.py      # 發送/接收 Telegram(sendMessage / getUpdates)
telegram_commands.py    # 解析 /markets /timeframes 等指令、管理訂閱設定
scanner.py              # 主程式，跑一次做一次完整掃描
state.json               # 記錄每個商品+週期最後通知過的K棒(掃描時自動更新)
subscriptions.json       # 每個 chat_id 的市場/週期訂閱設定(掃描時自動更新)
telegram_offset.json     # 記錄處理到第幾則Telegram訊息，避免重複處理同一則指令
requirements.txt
.github/workflows/scan.yml   # GitHub Actions 排程設定(每15分鐘跑一次)
.env.example             # 本機測試用的環境變數範例
```

## 部署步驟(GitHub Actions，電腦關機也會繼續跑)

### 1. 建立 GitHub Repository

去 https://github.com/new 建一個新 repo(建議設成 **Public**，Actions 執行時間完全免費不限額；
設 Private 的話免費額度是每月2000分鐘，這套系統一天跑96次、大概還是夠用，但保守起見公開較安心)。

repo 裡不會有任何密鑰(Token/Chat ID 都用 GitHub Secrets 管理，不會進到程式碼)，
只有交易邏輯設定和訊號紀錄，公開沒有安全疑慮。

### 2. 把這個資料夾推上去

在 `C:\Users\user\ribbon_signal_bot` 這個資料夾底下:

```bash
git init
git add .
git commit -m "init: ribbon mtf signal scanner"
git branch -M main
git remote add origin https://github.com/<你的帳號>/<repo名稱>.git
git push -u origin main
```

### 3. 設定 Telegram Secrets

Repo 頁面 -> **Settings** -> **Secrets and variables** -> **Actions** -> **New repository secret**，新增兩筆：

| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | 你的 Bot Token |
| `TELEGRAM_CHAT_ID` | 你的 Chat ID |

### 4. 啟用 Actions 並手動測試一次

Repo 頁面 -> **Actions** 分頁 -> 如果跳出提示按 **I understand my workflows, go ahead and enable them**。
點左側 **Ribbon MTF Signal Scanner** -> 右上 **Run workflow** -> 手動觸發一次，
看 log 有沒有正常抓到資料、有訊號時 Telegram 有沒有收到。

之後就會照 `.github/workflows/scan.yml` 裡的 `cron: "*/15 * * * *"` 每15分鐘自動跑，
不需要你電腦開著。

### ⚠️ GitHub Actions 排程的已知限制

- **60天沒有 push/commit 的話，GitHub 會自動停用排程**，需要你回來手動 Run workflow 一次重新啟用。
  建議每隔一段時間(例如調整 config.yaml 時)順手 commit 一下。
- 排程觸發時間**不保證準時**，尖峰時段常會晚個幾分鐘，屬 GitHub 免費排程的正常現象。
- 免費方案沒有「保證執行」的 SLA，如果你要更即時、更穩定，之後可以考慮換成雲端小主機常駐執行。

## 調整設定

打開 `config.yaml`：

- `markets.<market>.enabled` — 開關某個市場
- `markets.<market>.symbols` — 增減要掃描的商品(加密貨幣用 `BTC/USDT` 格式，美股用代號如 `AAPL`，
  外匯用 Yahoo 格式如 `EURUSD=X`，台股上市加 `.TW` 後綴、上櫃加 `.TWO`，例如 `2330.TW`)
- `signal_timeframes` — 增減要判斷訊號的週期
- `risk` / `atr_health` / `ribbon.ema_lengths` — 對應原 Pine 指標裡的同名參數

改完直接 `git add . && git commit -m "調整設定" && git push`，下次排程就會用新設定跑。

## 本機測試(選用)

```bash
pip install -r requirements.txt
copy .env.example .env   # 編輯 .env 填入你的 Token/Chat ID
python scanner.py
```

## 目前已知的簡化之處(先讓你有底)

- 美股/外匯資料來自 yfinance 免費源，盤中通常有15-20分鐘延遲；`4h` 週期是用 `1h` 資料
  resample 出來的，不是原生4h K棒，跟你在TradingView上看到的4h收盤時間可能有些微落差。
- ATR 健康區間(`atr_health`)的預設值是原指標針對單一資產調的，不同市場/週期的合理範圍
  可能差很多，建議先跑一陣子觀察 log 裡的 ATR% 再調整。
- 這套系統只做「訊號通知」，沒有像你另一套 `paper_trading` 系統一樣做資金曲線/勝率模擬，
  如果之後想要，可以把 `paper_trading_tick.py` 的部位追蹤邏輯搬過來接上。
