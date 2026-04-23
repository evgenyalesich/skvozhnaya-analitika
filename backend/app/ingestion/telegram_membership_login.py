import asyncio
import base64
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings

ROOT_DIR = Path(__file__).resolve().parents[3]


def _display_qr(url: str) -> None:
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=1, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        print("\033[2J\033[H", end="")
        print("=" * 50)
        print("  АВТОРИЗАЦИЯ ЧЕРЕЗ QR-КОД")
        print("=" * 50)
        print()
        print("  1. Открой Telegram на телефоне")
        print("  2. Настройки → Устройства → Подключить устройство")
        print("  3. Отсканируй QR-код ниже")
        print()
        qr.print_ascii(invert=True)
        print()
        print("  Ожидание сканирования...")
    except ImportError:
        print(f"QR URL (установи qrcode для отображения): {url}")


async def _qr_login(client) -> None:
    from telethon.tl.functions.auth import ExportLoginTokenRequest, ImportLoginTokenRequest
    from telethon.tl.types import auth
    from telethon.errors import SessionPasswordNeededError

    if await client.is_user_authorized():
        return

    while True:
        result = await client(ExportLoginTokenRequest(
            api_id=settings.telegram_api_id,
            api_hash=settings.telegram_api_hash,
            except_ids=[],
        ))

        if isinstance(result, auth.LoginTokenSuccess):
            break

        if isinstance(result, auth.LoginTokenMigrateTo):
            await client._switch_dc(result.dc_id)
            result = await client(ImportLoginTokenRequest(token=result.token))
            if isinstance(result, auth.LoginTokenSuccess):
                break
            continue

        token_b64 = base64.urlsafe_b64encode(result.token).decode()
        url = f"tg://login?token={token_b64}"
        _display_qr(url)

        expires_in = (result.expires - datetime.now(timezone.utc)).total_seconds()
        for _ in range(int(max(expires_in, 5))):
            await asyncio.sleep(1)
            try:
                check = await client(ExportLoginTokenRequest(
                    api_id=settings.telegram_api_id,
                    api_hash=settings.telegram_api_hash,
                    except_ids=[],
                ))
                if isinstance(check, auth.LoginTokenSuccess):
                    print("\n  QR-код отсканирован!")
                    return
                if isinstance(check, auth.LoginTokenMigrateTo):
                    await client._switch_dc(check.dc_id)
                    migrated = await client(ImportLoginTokenRequest(token=check.token))
                    if isinstance(migrated, auth.LoginTokenSuccess):
                        print("\n  QR-код отсканирован!")
                        return
            except SessionPasswordNeededError:
                password = input("\n  Аккаунт с 2FA. Введи пароль: ")
                await client.sign_in(password=password)
                return
            except Exception:
                pass

    try:
        await client.get_me()
    except Exception:
        from telethon.errors import SessionPasswordNeededError
        try:
            await client.get_me()
        except SessionPasswordNeededError:
            password = input("\n  Аккаунт с 2FA. Введи пароль: ")
            await client.sign_in(password=password)


async def _main() -> None:
    try:
        from telethon import TelegramClient
    except ImportError as exc:
        raise RuntimeError("Telethon is not installed. Run pip install -r backend/requirements.txt") from exc

    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise RuntimeError("TELEGRAM_API_ID/TELEGRAM_API_HASH are not configured")

    session_path = str(ROOT_DIR / settings.telegram_mtproto_session_name)
    client = TelegramClient(session_path, settings.telegram_api_id, settings.telegram_api_hash)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"Сессия уже авторизована: user_id={me.id} username={getattr(me, 'username', None)}")
        await client.disconnect()
        return

    await _qr_login(client)
    me = await client.get_me()
    print(f"\nАвторизация успешна: user_id={me.id} username={getattr(me, 'username', None)}")
    print(f"Сессия сохранена: {session_path}.session")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(_main())
