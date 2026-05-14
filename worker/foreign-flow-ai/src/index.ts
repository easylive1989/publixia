/**
 * publixia-foreign-flow-ai
 *
 * Cron Trigger:  18:30 Asia/Taipei daily (10:30 UTC)
 * Manual fetch:  POST <worker-url>/ with X-Worker-Token header
 *
 * Flow:
 *   1. GET  {API_BASE_URL}/api/futures/tw/foreign-flow/markdown   (X-Worker-Token)
 *   2. env.AI.run("@cf/qwen/qwen3-30b-a3b-fp8", { messages })
 *   3. POST {API_BASE_URL}/api/futures/tw/foreign-flow/ai-report   (X-Worker-Token)
 *   4. POST Discord webhook (chunked text)
 */
import { chunkForDiscord, postDiscord } from "./discord";

export interface Env {
  AI: Ai;
  API_BASE_URL: string;
  WORKER_TOKEN: string;
  DISCORD_WEBHOOK_URL: string;
}

const MODEL = "@cf/qwen/qwen3-30b-a3b-fp8";
const PROMPT_VERSION = "v1";
const TIME_RANGE = "1M"; // 30-day window; markdown slices the trailing 5.

const SYSTEM_PROMPT =
  "你是個人交易者,擅長台指期短線技術分析。你會收到一份 markdown 表格 " +
  "(包含 TX 期貨日線、外資現貨、外資期貨多空、TXO 三大法人、各履約價 OI、" +
  "散戶多空比)。請輸出繁體中文交易分析,涵蓋:" +
  "(1) 外資多空動向解讀,(2) TXO 選擇權三大法人布局,(3) 散戶多空比觀察," +
  "(4) 隔週技術面交易計畫 (進場/停損/停利),(5) 主要風險訊號。" +
  "請保持精簡、條列清楚、用客觀語氣,避免過度自信。";

function todayInTaipei(): string {
  // 'en-CA' formats as 'YYYY-MM-DD' which matches our DB schema.
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Taipei",
    year:  "numeric",
    month: "2-digit",
    day:   "2-digit",
  }).format(new Date());
}

async function fetchInputMarkdown(env: Env): Promise<string> {
  const url = `${env.API_BASE_URL}/api/futures/tw/foreign-flow/markdown?time_range=${TIME_RANGE}`;
  const resp = await fetch(url, {
    headers: { "X-Worker-Token": env.WORKER_TOKEN },
  });
  if (!resp.ok) {
    throw new Error(
      `markdown fetch failed ${resp.status}: ${(await resp.text()).slice(0, 200)}`,
    );
  }
  return await resp.text();
}

/** Workers AI hands back two different shapes depending on the model:
 *
 * - OpenAI chat-completions: ``{choices: [{message: {content}}]}``
 *   (Qwen 3, GPT-OSS, Llama 4, and most newer instruct models)
 * - Legacy:                  ``{response: string}``
 *   (Llama 3.x, Mistral, older catalog entries)
 *
 * We try both so swapping ``MODEL`` doesn't force a worker change. */
function extractLLMText(result: unknown): string {
  const r = result as {
    choices?: { message?: { content?: string } }[];
    response?: string;
  } | null;
  const choice = r?.choices?.[0]?.message?.content;
  if (typeof choice === "string" && choice.trim()) return choice.trim();
  if (typeof r?.response === "string" && r.response.trim())
    return r.response.trim();
  return "";
}

async function runLLM(env: Env, inputMarkdown: string): Promise<string> {
  const result = await env.AI.run(MODEL as any, {
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user",   content: inputMarkdown },
    ],
  } as any);
  const out = extractLLMText(result);
  if (!out) {
    // Last-resort dump so tail can show what we got when no known shape matched.
    try { console.error("ai_unknown_shape", JSON.stringify(result).slice(0, 1500)); }
    catch { console.error("ai_unstringifiable", typeof result); }
    throw new Error("LLM returned empty response");
  }
  return out;
}

async function writeReportBack(
  env: Env,
  body: {
    report_date:     string;
    model:           string;
    prompt_version:  string;
    input_markdown:  string;
    output_markdown: string;
  },
): Promise<void> {
  const resp = await fetch(
    `${env.API_BASE_URL}/api/futures/tw/foreign-flow/ai-report`,
    {
      method:  "POST",
      headers: {
        "Content-Type":   "application/json",
        "X-Worker-Token": env.WORKER_TOKEN,
      },
      body: JSON.stringify(body),
    },
  );
  if (!resp.ok) {
    throw new Error(
      `writeback failed ${resp.status}: ${(await resp.text()).slice(0, 200)}`,
    );
  }
}

async function generateAndDeliver(env: Env): Promise<{ report_date: string }> {
  const reportDate = todayInTaipei();
  const inputMarkdown  = await fetchInputMarkdown(env);
  const outputMarkdown = await runLLM(env, inputMarkdown);

  await writeReportBack(env, {
    report_date:     reportDate,
    model:           MODEL,
    prompt_version:  PROMPT_VERSION,
    input_markdown:  inputMarkdown,
    output_markdown: outputMarkdown,
  });

  // Discord delivery is best-effort; failures only log.
  await postDiscord(
    env.DISCORD_WEBHOOK_URL,
    `**今日外資動向 AI 分析 (${reportDate})**\n模型: \`${MODEL}\``,
  );
  for (const chunk of chunkForDiscord(outputMarkdown)) {
    await postDiscord(env.DISCORD_WEBHOOK_URL, chunk);
  }

  return { report_date: reportDate };
}

/** Post an error notice to Discord. Best-effort — swallows its own
 *  failures so we never mask the original error. */
async function notifyDiscordError(
  env: Env,
  source: "cron" | "manual",
  err: unknown,
): Promise<void> {
  const msg = err instanceof Error ? err.message : String(err);
  // Discord's 2000-char ceiling — leave room for the prefix.
  const trimmed = msg.length > 1800 ? msg.slice(0, 1800) + "…" : msg;
  await postDiscord(
    env.DISCORD_WEBHOOK_URL,
    `:warning: 外資動向 AI 報告生成失敗 (${source})\n\`\`\`\n${trimmed}\n\`\`\``,
  ).catch(() => undefined);
}

export default {
  async scheduled(_event: ScheduledController, env: Env): Promise<void> {
    try {
      const r = await generateAndDeliver(env);
      console.log("scheduled_ok", r);
    } catch (e) {
      console.error("scheduled_failed", e instanceof Error ? e.message : e);
      await notifyDiscordError(env, "cron", e);
    }
  },

  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.headers.get("X-Worker-Token") !== env.WORKER_TOKEN) {
      return new Response("unauthorized", { status: 401 });
    }
    try {
      const r = await generateAndDeliver(env);
      return Response.json({ ok: true, ...r });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error("manual_failed", msg);
      await notifyDiscordError(env, "manual", e);
      return Response.json({ ok: false, error: msg }, { status: 500 });
    }
  },
};
