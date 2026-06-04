"""One-off diagnostic: does Cloudflare Workers AI extraction actually work?

Reads CF creds from backend/.env (gitignored — never commit them). Run:

    cd backend && .venv/bin/python scripts/check_cf_ai.py

It makes a REAL Workers AI call on a sample Traditional-Chinese post and
prints the extracted trades, so you can confirm the token has Workers AI
permission and the model + parsing work — without waiting for the prod cron.
"""
from core.settings import settings
from core.cloudflare_ai import CloudflareAIError
from services.trade_extraction import extract_trades, PROMPT_VERSION

SAMPLE = "我爸已經73歲系列28\n早盤重大訊息：家父持股－緯創全數售出，預計轉投其他個股。今日也加碼台積電。"


def main() -> int:
    print(f"cf_account_id set: {bool(settings.cf_account_id)}")
    print(f"cf_api_token set : {bool(settings.cf_api_token)}")
    print(f"model            : {settings.cf_ai_model}")
    print(f"prompt_version   : {PROMPT_VERSION}")
    if not settings.cf_account_id or not settings.cf_api_token:
        print("\n→ 請先在 backend/.env 填 CF_ACCOUNT_ID 與 CF_API_TOKEN")
        return 1

    print(f"\n--- sample post ---\n{SAMPLE}\n")
    try:
        trades = extract_trades(SAMPLE)
    except CloudflareAIError as e:
        print(f"✗ Workers AI 呼叫失敗: {e}")
        print("  403 → token 缺 Workers AI 權限；404 → 模型名或 account_id 有誤")
        return 2

    print(f"✓ 解析成功,抽出 {len(trades)} 筆:")
    for t in trades:
        print(f"  - {t['raw_symbol']} / {t['direction']} (confidence={t['confidence']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
