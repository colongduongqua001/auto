"""AI tự vận hành browser — wrapper mỏng quanh `browser-use`.

Ví dụ chạy:

    uv run python main.py "Tìm trên Google: thời tiết Hà Nội hôm nay, trả về nhiệt độ"
    uv run python main.py --headless "Vào https://news.ycombinator.com và tóm tắt 3 bài top"

Chạy không tham số sẽ vào REPL — gõ task, AI sẽ thực thi.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from browser_use import Agent, BrowserProfile, BrowserSession, ChatOpenAI


def _load_env() -> tuple[str, str, str]:
    load_dotenv(Path(__file__).parent / ".env")

    base_url = os.getenv("LLM_BASE_URL") or os.getenv("CUSTOM_LLM_BASE_URL")
    api_key = os.getenv("LLM_API_KEY") or os.getenv("CUSTOM_LLM_API_KEY")
    model = os.getenv("LLM_MODEL") or os.getenv("CUSTOM_LLM_MODEL")

    missing = [
        name
        for name, val in [
            ("LLM_BASE_URL", base_url),
            ("LLM_API_KEY", api_key),
            ("LLM_MODEL", model),
        ]
        if not val
    ]
    if missing:
        sys.exit(
            "Thiếu biến môi trường: "
            + ", ".join(missing)
            + ".\nCopy .env.example -> .env và điền vào, hoặc export trực tiếp."
        )

    assert base_url and api_key and model
    return base_url, api_key, model


def _build_llm() -> ChatOpenAI:
    base_url, api_key, model = _load_env()
    # Một số gateway / proxy chặn User-Agent mặc định của OpenAI SDK
    # ("OpenAI/Python ...") và các header `x-stainless-*` đi kèm. Cho phép
    # override qua biến môi trường, mặc định dùng 1 UA trung tính.
    user_agent = os.getenv("LLM_USER_AGENT", "auto-browser-agent/0.1")
    default_headers = {"User-Agent": user_agent}
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        default_headers=default_headers,
    )


def _build_browser(headless: bool) -> BrowserSession:
    profile = BrowserProfile(
        headless=headless,
        # Cho cửa sổ đủ to để xem AI thao tác
        window_size={"width": 1280, "height": 900},
    )
    return BrowserSession(browser_profile=profile)


async def run_task(task: str, *, headless: bool, max_steps: int) -> str:
    llm = _build_llm()
    browser = _build_browser(headless=headless)
    agent = Agent(task=task, llm=llm, browser_session=browser)
    history = await agent.run(max_steps=max_steps)
    final = history.final_result() if hasattr(history, "final_result") else None
    return final or "(agent kết thúc, không có final_result)"


async def _repl(headless: bool, max_steps: int) -> None:
    print("AI Browser Agent — gõ task, Enter để chạy. Ctrl+C để thoát.\n")
    while True:
        try:
            task = input("task> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not task:
            continue
        result = await run_task(task, headless=headless, max_steps=max_steps)
        print(f"\n=== KẾT QUẢ ===\n{result}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="AI tự vận hành browser")
    parser.add_argument("task", nargs="*", help="Task cho AI (để trống -> REPL)")
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=os.getenv("HEADLESS", "").lower() in {"1", "true", "yes"},
        help="Chạy browser ẩn (mặc định: hiện cửa sổ)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=25,
        help="Số bước tối đa AI được phép thực hiện (mặc định 25)",
    )
    args = parser.parse_args()

    if args.task:
        task = " ".join(args.task)
        result = asyncio.run(
            run_task(task, headless=args.headless, max_steps=args.max_steps)
        )
        print(f"\n=== KẾT QUẢ ===\n{result}")
    else:
        asyncio.run(_repl(headless=args.headless, max_steps=args.max_steps))


if __name__ == "__main__":
    main()
