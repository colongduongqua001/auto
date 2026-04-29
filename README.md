# auto — AI tự vận hành browser

Một wrapper rất mỏng quanh [`browser-use`](https://github.com/browser-use/browser-use):
bạn giao task bằng tiếng người, AI tự mở Chromium, click, gõ, đọc trang và trả lời.

Đây là alternative đơn giản hơn nhiều so với OpenHands / Claude Computer Use:
chỉ cần Python + 1 LLM endpoint OpenAI-compatible là chạy được.

## Yêu cầu

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) (hoặc `pip` / `venv` thuần)
- 1 LLM API endpoint OpenAI-compatible (OpenAI, OpenRouter, Together, Groq,
  vLLM, Ollama, hoặc provider riêng)

## Cài đặt

```bash
# 1. Cài deps Python
uv sync

# 2. Cài Chromium cho Playwright (chỉ cần làm 1 lần)
uv run playwright install chromium --with-deps

# 3. Cấu hình LLM
cp .env.example .env
# Mở .env, điền LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
```

## Chạy

### Một task duy nhất

```bash
uv run python main.py "Vào https://news.ycombinator.com và tóm tắt 3 bài top"
```

### Chế độ REPL (tương tác liên tục)

```bash
uv run python main.py
# task> Tìm giá Bitcoin hiện tại trên CoinGecko
# task> Vào VnExpress, lấy 5 tiêu đề trang nhất
```

### Headless (không hiện cửa sổ)

```bash
uv run python main.py --headless "..."
# hoặc đặt HEADLESS=true trong .env
```

### Tham số khác

| Cờ | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `--headless` / `--no-headless` | `--no-headless` | Ẩn / hiện cửa sổ browser |
| `--max-steps N` | `25` | Số bước tối đa AI được phép thực hiện |

## Cấu hình LLM

`.env`:

```env
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o
```

Một vài provider phổ biến:

| Provider | `LLM_BASE_URL` | `LLM_MODEL` ví dụ |
| --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o`, `gpt-4.1` |
| OpenRouter | `https://openrouter.ai/api/v1` | `anthropic/claude-3.5-sonnet` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| Ollama (local) | `http://localhost:11434/v1` | `llama3.1:70b` |
| vLLM (local) | `http://localhost:8000/v1` | (model bạn serve) |

Mọi provider OpenAI-compatible đều dùng được — chỉ cần endpoint expose
`/v1/chat/completions`.

> **Mẹo:** một số gateway / proxy chặn User-Agent mặc định của OpenAI SDK
> (`OpenAI/Python x.y.z`) và trả về 403 *"Your request was blocked"*. Nếu
> gặp, set `LLM_USER_AGENT=auto-browser-agent/0.1` (hoặc bất cứ chuỗi nào)
> trong `.env`. Code đã set sẵn 1 UA trung tính nên thường không cần làm gì.

## Mẹo viết task

- Càng cụ thể càng tốt: nêu URL khởi đầu nếu có, nêu rõ output cần lấy.
- Có thể dùng tiếng Việt thoải mái — LLM hiểu được.
- Với task dài, tăng `--max-steps` (vd `--max-steps 60`).

Ví dụ task tốt:

```
Vào https://news.ycombinator.com, lấy tiêu đề + URL của 5 bài top,
trả về dạng markdown bullet list.
```

```
Tìm trên Google "weather Hanoi today", click kết quả đầu tiên không
phải quảng cáo, đọc nhiệt độ hiện tại và độ ẩm, trả về 1 dòng.
```

## Cấu trúc

```
auto/
├── main.py         # Generic CLI + REPL
├── tempmail.py     # Client mail.tm (inbox tạm, không cần API key)
├── leonardo.py     # Task: tự đăng ký + login Leonardo.ai
├── run-demo.sh     # Smoke test: HN top-3
├── pyproject.toml  # uv project
├── .env.example    # Mẫu config LLM
└── README.md
```

Phần khó (parse DOM, vision, planning, function-calling) là `browser-use` lo.

## Predefined task: Leonardo.ai auto-signup

```bash
uv run python leonardo.py signup
```

Flow:
1. Tạo email tạm trên mail.tm (free, không cần signup).
2. Sinh password random mạnh.
3. AI mở leonardo.ai, đăng ký, click verify link từ inbox tạm.
4. Lưu cred vào `.local/leonardo-accounts.jsonl` (gitignored).
5. Dump info account (plan, credits, ...) ra stdout.

> **Cảnh báo:** Leonardo có thể có Cloudflare Turnstile / SMS verify — không
> phải lúc nào cũng qua được. Nếu gặp captcha agent sẽ stuck; bạn có thể
> chạy `--no-headless` (mặc định) để tự click captcha — cookies persist nhờ
> `user_data_dir`, lần sau không cần login lại.

> **ToS:** automated signup có thể vi phạm Terms of Service của Leonardo.
> Dùng cho mục đích demo / throwaway thôi.

## Tham khảo

- [browser-use docs](https://docs.browser-use.com/)
- [Playwright docs](https://playwright.dev/python/)
