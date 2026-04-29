"""Lightweight mail.tm client (free, no signup required, no API key).

Cho phép:
- Tạo 1 inbox tạm (random local part trên 1 domain mail.tm cấp).
- Poll inbox để lấy message mới (lọc theo subject/from).
- Trích link đầu tiên match regex từ HTML/text body.

Đủ để verify-email cho các flow signup tự động.
"""

from __future__ import annotations

import asyncio
import re
import secrets
import string
from dataclasses import dataclass

import httpx

API = "https://api.mail.tm"


@dataclass
class TempInbox:
    address: str
    password: str
    token: str

    @property
    def auth_header(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


def _random_string(length: int, alphabet: str = string.ascii_lowercase + string.digits) -> str:
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def _get_active_domain(client: httpx.AsyncClient) -> str:
    r = await client.get(f"{API}/domains")
    r.raise_for_status()
    domains = r.json()["hydra:member"]
    active = [d["domain"] for d in domains if d.get("isActive")]
    if not active:
        raise RuntimeError("mail.tm: no active domains")
    return active[0]


async def create_inbox(local_part: str | None = None, password: str | None = None) -> TempInbox:
    async with httpx.AsyncClient(timeout=20) as client:
        domain = await _get_active_domain(client)
        local = local_part or _random_string(12)
        address = f"{local}@{domain}"
        pw = password or (
            _random_string(8, string.ascii_letters + string.digits)
            + "Aa1!"  # mail.tm requires at least 8 chars; mixed case + digit safe bet
        )

        r = await client.post(
            f"{API}/accounts",
            json={"address": address, "password": pw},
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"mail.tm create account failed: {r.status_code} {r.text}")

        # Get JWT token
        r = await client.post(
            f"{API}/token",
            json={"address": address, "password": pw},
        )
        r.raise_for_status()
        token = r.json()["token"]
        return TempInbox(address=address, password=pw, token=token)


async def list_messages(inbox: TempInbox) -> list[dict]:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{API}/messages", headers=inbox.auth_header)
        r.raise_for_status()
        return r.json()["hydra:member"]


async def get_message(inbox: TempInbox, msg_id: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{API}/messages/{msg_id}", headers=inbox.auth_header)
        r.raise_for_status()
        return r.json()


async def wait_for_message(
    inbox: TempInbox,
    *,
    subject_contains: str | None = None,
    from_contains: str | None = None,
    timeout: float = 120.0,
    poll_interval: float = 3.0,
) -> dict:
    """Poll inbox until a matching message arrives (or timeout)."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        msgs = await list_messages(inbox)
        for m in msgs:
            subj = (m.get("subject") or "").lower()
            sender = ((m.get("from") or {}).get("address") or "").lower()
            if subject_contains and subject_contains.lower() not in subj:
                continue
            if from_contains and from_contains.lower() not in sender:
                continue
            return await get_message(inbox, m["id"])
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError(
                f"No matching message after {timeout:.0f}s "
                f"(subject={subject_contains!r}, from={from_contains!r})"
            )
        await asyncio.sleep(poll_interval)


_LINK_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


def extract_first_link(message: dict, *, must_contain: str | None = None) -> str | None:
    """Trả về URL đầu tiên trong body khớp `must_contain` (substring, case-insensitive)."""
    body_parts = []
    if message.get("html"):
        body_parts.extend(message["html"] if isinstance(message["html"], list) else [message["html"]])
    if message.get("text"):
        body_parts.append(message["text"])

    for body in body_parts:
        for url in _LINK_RE.findall(body):
            url = url.rstrip(".,)>\"'")
            if must_contain and must_contain.lower() not in url.lower():
                continue
            return url
    return None


async def _demo() -> None:
    """Smoke test: tạo inbox, in info."""
    inbox = await create_inbox()
    print(f"Email: {inbox.address}")
    print(f"Password: {inbox.password}")
    print("Inbox created. Send a test mail then run wait_for_message().")


if __name__ == "__main__":
    asyncio.run(_demo())
