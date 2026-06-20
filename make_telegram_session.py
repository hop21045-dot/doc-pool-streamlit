from __future__ import annotations

import asyncio
import os

from telethon import TelegramClient
from telethon.sessions import StringSession


def load_env_file(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


async def main() -> None:
    load_env_file()
    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    if not api_id or not api_hash:
        raise SystemExit(".env에 TELEGRAM_API_ID와 TELEGRAM_API_HASH를 먼저 입력하세요.")

    session_name = os.getenv("TELEGRAM_SESSION", "doc_pool.session").strip() or "doc_pool.session"
    async with TelegramClient(session_name, int(api_id), api_hash) as client:
        me = await client.get_me()
        print(f"Telegram 로그인 완료: {getattr(me, 'username', None) or me.id}")

        string_session = StringSession.save(client.session)
        print("\nStreamlit Cloud 배포용 TELEGRAM_STRING_SESSION 값:")
        print(string_session)
        print("\n로컬 실행만 할 때는 생성된 doc_pool.session 파일을 사용해도 됩니다.")


if __name__ == "__main__":
    asyncio.run(main())
