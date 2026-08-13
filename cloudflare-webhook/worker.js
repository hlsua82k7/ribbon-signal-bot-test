/**
 * Ribbon Signal Bot - Telegram Webhook 轉發器
 *
 * 只做一件事：Telegram 一收到訊息就會立刻 POST 到這裡，
 * 我們馬上叫 GitHub Actions 觸發一次 workflow_dispatch，把訊息內容(chat_id + text)
 * 當成 inputs 帶過去，讓 scanner.py 立即處理這一則指令並回覆——不用等15分鐘排程。
 *
 * 完整市場掃描完全不受影響，還是照原本的 schedule 每15分鐘跑，這裡只負責「指令」這條路。
 */

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("ribbon-signal-bot webhook is alive", { status: 200 });
    }

    // 驗證這則請求真的是Telegram送來的，不是隨便誰對著這個URL亂打
    const secretHeader = request.headers.get("X-Telegram-Bot-Api-Secret-Token");
    if (env.TG_WEBHOOK_SECRET && secretHeader !== env.TG_WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 403 });
    }

    let update;
    try {
      update = await request.json();
    } catch (e) {
      return new Response("bad request", { status: 400 });
    }

    const msg = update.message || update.edited_message;
    const text = msg && msg.text;
    const chatId = msg && msg.chat && msg.chat.id;

    // 只轉發「/開頭的指令」，其他訊息(閒聊、貼圖...)直接忽略，避免每則訊息都去觸發GitHub Actions
    if (text && chatId && text.startsWith("/")) {
      const dispatchUrl =
        `https://api.github.com/repos/${env.GH_OWNER}/${env.GH_REPO}` +
        `/actions/workflows/${env.GH_WORKFLOW_FILE}/dispatches`;

      const resp = await fetch(dispatchUrl, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "User-Agent": "ribbon-signal-bot-webhook",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ref: env.GH_BRANCH || "main",
          inputs: {
            tg_chat_id: String(chatId),
            tg_text: text,
          },
        }),
      });

      if (!resp.ok) {
        console.log(`GitHub workflow_dispatch 失敗: ${resp.status} ${await resp.text()}`);
      }
    }

    // 一定要回200給Telegram，不然它會把這則更新當失敗、之後一直重送
    return new Response("OK", { status: 200 });
  },
};
