"""AI tự đăng ký + login Leonardo.ai và dump thông tin tài khoản.

Flow:
1. Tạo 1 inbox tạm trên mail.tm.
2. Sinh password random.
3. browser-use Agent mở leonardo.ai, đăng ký bằng email/password vừa tạo.
4. Khi Leonardo gửi email verify, agent gọi tool `get_verification_link()`
   để lấy link từ inbox tạm.
5. Agent mở link, hoàn tất verify.
6. Dump info account (email, plan, credits, ...) và lưu cred vào
   `.local/leonardo-account.json` để bạn dùng sau.

Nếu gặp captcha / SMS verify, agent sẽ stuck — mở browser non-headless để
bạn nhìn thấy và giải tay nếu muốn (cookies sẽ persist nhờ user_data_dir).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import string
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

from browser_use import Agent, BrowserProfile, BrowserSession, ChatOpenAI
from browser_use.tools.service import Tools

import tempmail

ROOT = Path(__file__).parent
LOCAL = ROOT / ".local"
LOCAL.mkdir(exist_ok=True)
PROFILES_DIR = LOCAL / "profiles"
PROFILES_DIR.mkdir(exist_ok=True)
ACCOUNTS_FILE = LOCAL / "leonardo-accounts.jsonl"


def _strong_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in pw)
            and any(c.isupper() for c in pw)
            and any(c.isdigit() for c in pw)
        ):
            return pw + "!Aa1"  # đảm bảo có symbol để qua mọi rule


def _build_llm() -> ChatOpenAI:
    load_dotenv(ROOT / ".env")
    base = os.getenv("LLM_BASE_URL") or os.getenv("CUSTOM_LLM_BASE_URL")
    key = os.getenv("LLM_API_KEY") or os.getenv("CUSTOM_LLM_API_KEY")
    model = os.getenv("LLM_MODEL") or os.getenv("CUSTOM_LLM_MODEL")
    if not (base and key and model):
        sys.exit("Thiếu LLM_BASE_URL / LLM_API_KEY / LLM_MODEL trong .env hoặc env.")
    ua = os.getenv("LLM_USER_AGENT", "auto-browser-agent/0.1")
    return ChatOpenAI(
        model=model,
        api_key=key,
        base_url=base,
        default_headers={"User-Agent": ua},
    )


def _build_browser(*, profile_name: str, headless: bool) -> BrowserSession:
    """Browser session với persistent profile dir → cookies survive giữa runs."""
    profile = BrowserProfile(
        headless=headless,
        user_data_dir=str(PROFILES_DIR / profile_name),
        window_size={"width": 1280, "height": 900},
        # Leonardo dùng JS nặng, nên disable_security mặc định OK
    )
    return BrowserSession(browser_profile=profile)


def _build_tools(inbox: tempmail.TempInbox) -> Tools:
    """Tools với 2 custom action: poll inbox + extract verify link."""
    tools = Tools()

    class _NoArgs(BaseModel):
        pass

    @tools.registry.action(
        "Lấy link verify email từ inbox tạm (poll mail.tm). Gọi sau khi đã "
        "submit form đăng ký Leonardo và đợi email được gửi đến.",
        param_model=_NoArgs,
    )
    async def get_verification_link(params: _NoArgs):  # type: ignore[unused-ignore]
        try:
            msg = await tempmail.wait_for_message(
                inbox,
                from_contains="leonardo",
                timeout=180.0,
                poll_interval=4.0,
            )
        except TimeoutError as e:
            return {"error": f"Không nhận được email từ Leonardo trong 180s: {e}"}
        link = tempmail.extract_first_link(msg, must_contain="leonardo")
        if not link:
            link = tempmail.extract_first_link(msg)
        return {
            "subject": msg.get("subject"),
            "from": (msg.get("from") or {}).get("address"),
            "verification_link": link,
            "snippet": (msg.get("text") or "")[:300],
        }

    @tools.registry.action(
        "Đọc tất cả email mới trong inbox tạm (debug nếu verify link không bắt được).",
        param_model=_NoArgs,
    )
    async def list_temp_inbox(params: _NoArgs):  # type: ignore[unused-ignore]
        msgs = await tempmail.list_messages(inbox)
        return [
            {
                "id": m["id"],
                "from": (m.get("from") or {}).get("address"),
                "subject": m.get("subject"),
                "intro": m.get("intro"),
            }
            for m in msgs
        ]

    return tools


def _persist_account(record: dict) -> Path:
    record = {**record, "created_at": datetime.utcnow().isoformat() + "Z"}
    with ACCOUNTS_FILE.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return ACCOUNTS_FILE


SIGNUP_TASK_TEMPLATE = """\
Mục tiêu: tự đăng ký 1 tài khoản mới trên Leonardo.ai và dump thông tin
account.

Dữ liệu sẵn có (dùng đúng những giá trị này, KHÔNG bịa ra):
- Email: {email}
- Password: {password}

Các bước:
1. Mở https://app.leonardo.ai/auth/signup (nếu redirect, đi theo).
2. Trên form Sign up, chọn phương thức "Email" (không dùng Google/Apple/MS).
3. Điền email = {email} và password = {password}. Nếu form yêu cầu confirm
   password thì dùng cùng giá trị.
4. Nếu có checkbox "I agree to terms" / "I am 18+", tick.
5. Submit form. Nếu gặp Cloudflare Turnstile / captcha / SMS verify,
   DỪNG LẠI và báo lỗi rõ ràng (không fake).
6. Sau khi submit thành công, Leonardo sẽ gửi email verify. Gọi action
   `get_verification_link` để lấy link verify. Nếu không có link, gọi
   `list_temp_inbox` để debug.
7. Mở link verify đó (cùng tab hoặc tab mới đều được).
8. Nếu được redirect về app, hoàn tất onboarding tối thiểu (chọn 1 lựa chọn
   nhanh nhất ở mỗi step). Mục tiêu là vào được dashboard.
9. Khi đã ở dashboard, đọc và trả về dạng JSON các thông tin sau (cái nào
   không thấy thì để null):
   - username
   - plan (Free / Apprentice / ...)
   - credits / tokens hiện có
   - daily_credit_refresh (nếu có)
   - is_email_verified

Output cuối cùng phải là JSON 1 object như mô tả trên.
"""


async def signup() -> dict:
    llm = _build_llm()

    # 1. Tạo inbox tạm
    print("[*] Tạo email tạm trên mail.tm...", flush=True)
    inbox = await tempmail.create_inbox()
    print(f"    Email: {inbox.address}")

    # 2. Sinh password Leonardo
    leo_pw = _strong_password()
    print(f"    Leonardo password: {leo_pw}")

    # 3. Persist sớm phòng crash giữa chừng
    record = {
        "email": inbox.address,
        "password": leo_pw,
        "tempmail_password": inbox.password,
        "tempmail_token": inbox.token,
        "status": "pending",
    }
    _persist_account(record)

    # 4. Browser + tools
    profile_name = inbox.address.split("@", 1)[0]
    browser = _build_browser(profile_name=f"leonardo-{profile_name}", headless=False)
    tools = _build_tools(inbox)

    task = SIGNUP_TASK_TEMPLATE.format(email=inbox.address, password=leo_pw)

    agent = Agent(
        task=task,
        llm=llm,
        browser_session=browser,
        tools=tools,
        # Hide password khỏi LLM context khi log/screenshot
        sensitive_data={"leo_password": leo_pw},
    )

    print("[*] Bắt đầu signup flow (browser sẽ bật ra)...", flush=True)
    history = await agent.run(max_steps=40)
    final = history.final_result() if hasattr(history, "final_result") else None

    # 5. Persist final
    record_done = {
        **record,
        "status": "done" if final else "incomplete",
        "agent_final_result": final,
    }
    _persist_account(record_done)

    return record_done


def main() -> None:
    ap = argparse.ArgumentParser(description="Leonardo.ai auto signup demo")
    ap.add_argument(
        "command",
        choices=["signup"],
        help="signup = tự đăng ký account mới",
    )
    args = ap.parse_args()

    if args.command == "signup":
        result = asyncio.run(signup())
        print("\n=== KẾT QUẢ ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
