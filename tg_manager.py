import asyncio
import os
import random
import time
from telethon import TelegramClient, functions, types
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError, RPCError, SessionPasswordNeededError,
    PhoneNumberInvalidError, PhoneCodeInvalidError, PhoneCodeExpiredError
)

from temp_mail import get_temp_mailbox, extract_code
from device_profiles import get_random_device
import database

ENV_API_ID = int(os.getenv("TG_API_ID", "0") or 0)
ENV_API_HASH = os.getenv("TG_API_HASH", "") or ""
ENV_PROXY = os.getenv("TG_PROXY", "") or ""

ERROR_MAP = {
    "EMAIL_NOT_ALLOWED": "Telegram ne is email domain ko ban/reject kiya hai.",
    "EMAIL_NOT_SETUP": "Account par pehle se koi login email setup nahi hai.",
    "EMAIL_INVALID": "Email format invalid hai.",
    "EMAIL_UNCONFIRMED": "Purana email abhi confirmation pending me hai.",
    "PHONE_CODE_INVALID": "OTP code galat hai.",
    "PHONE_CODE_EXPIRED": "OTP expire ho gaya.",
    "AUTH_KEY_UNREGISTERED": "Session logout ho chuka hai.",
    "USER_DEACTIVATED": "Account deactivated/banned ho gaya."
}

def explain_error(e):
    err_str = str(e).upper()
    for key, explanation in ERROR_MAP.items():
        if key in err_str:
            return key, explanation
    return "UNKNOWN", str(e)

def parse_proxy_url(proxy_url):
    if not proxy_url:
        return None
    from urllib.parse import urlparse, unquote
    u = urlparse(proxy_url if "://" in proxy_url else "socks5://" + proxy_url)
    return {
        "proxy_type": u.scheme or "socks5",
        "addr": u.hostname,
        "port": int(u.port or 1080),
        "username": unquote(u.username) if u.username else None,
        "password": unquote(u.password) if u.password else None,
        "rdns": True
    }

def get_client(session_str="", phone=None):
    """
    Creates a resilient Telethon client:
    - Retries connection automatically (connection_retries=10)
    - Anti-Fingerprinting device profiles
    - API & Proxy rotation
    """
    api_id, api_hash = database.get_next_api(ENV_API_ID, ENV_API_HASH)
    proxy_str = database.get_next_proxy(ENV_PROXY)
    proxy_dict = parse_proxy_url(proxy_str)

    device = None
    if phone:
        acc = database.get_account(phone)
        if acc and acc.get("device_profile"):
            device = acc["device_profile"]
    if not device:
        device = get_random_device()
        if phone:
            database.update_account_field(phone, "device_profile", device)

    kw = {
        "device_model": device["device_model"],
        "system_version": device["system_version"],
        "app_version": device["app_version"],
        "lang_code": device["lang_code"],
        "system_lang_code": device["system_lang_code"],
        "connection_retries": 10,
        "retry_delay": 2,
        "timeout": 20
    }
    if proxy_dict:
        kw["proxy"] = proxy_dict

    return TelegramClient(StringSession(session_str), api_id, api_hash, **kw)

async def gaussian_delay(min_sec=1.5, max_sec=3.0):
    mean = (min_sec + max_sec) / 2.0
    sigma = (max_sec - min_sec) / 4.0
    delay = random.gauss(mean, sigma)
    delay = max(min_sec, min(delay, max_sec + 1.0))
    await asyncio.sleep(delay)

async def safe_call(client, request_coro, log_fn=None, max_flood_wait=1800):
    """
    Safe Request Caller with Automatic FloodWait Sleep and Seamless Resume.
    """
    while True:
        await gaussian_delay(1.5, 3.0)
        try:
            return await client(request_coro)
        except FloodWaitError as e:
            wait_sec = int(e.seconds) + 3
            if wait_sec > max_flood_wait:
                if log_fn:
                    await log_fn(f"⚠️ FloodWait `{wait_sec}s` exceeds maximum limit (`{max_flood_wait}s`).")
                raise e
            if log_fn:
                await log_fn(f"⏳ **[FLOOD-WAIT AUTO-RESUME ACTIVE]**\n"
                             f"Telegram ne `{wait_sec}s` wait karne ko kaha hai.\n"
                             f"Bot safe pause me hai. **Timer pura hote hi khud aage ka kaam karega!**")
            print(f"[FloodWait Auto-Resume] Sleeping {wait_sec}s...", flush=True)
            await asyncio.sleep(wait_sec)
            if log_fn:
                await log_fn(f"✅ FloodWait samapt! Action auto-resume ho raha hai...")
        except (ConnectionError, asyncio.TimeoutError) as net_err:
            print(f"[Network Jitter] {net_err}. Retrying in 4s...", flush=True)
            await asyncio.sleep(4)

async def fetch_account_latest_otp(phone):
    acc = database.get_account(phone)
    if not acc or not acc.get("session"):
        return {"success": False, "error": "Account not found or no session"}

    c = get_client(acc["session"], phone=phone)
    try:
        await c.connect()
        if not await c.is_user_authorized():
            database.update_account_field(phone, "status", "unauthorized")
            return {"success": False, "error": "Session unauthorized/expired"}

        messages = await c.get_messages(777000, limit=5)
        if not messages:
            async for dialog in c.iter_dialogs(limit=10):
                if dialog.entity and getattr(dialog.entity, "id", None) == 777000:
                    messages = await c.get_messages(dialog.entity, limit=5)
                    break

        if not messages:
            return {
                "success": True,
                "phone": phone,
                "pass_2fa": acc.get("password_2fa") or "None",
                "code": "No service messages yet",
                "text": "Telegram official chat 777000 is empty.",
                "date": "N/A"
            }

        latest_msg = messages[0]
        text = latest_msg.text or ""
        date_str = latest_msg.date.strftime("%Y-%m-%d %H:%M:%S UTC")
        code = extract_code(text, 5) or extract_code(text, 6) or extract_code(text)
        
        if code:
            database.update_account_field(phone, "last_otp", code)
            database.update_account_field(phone, "last_otp_time", date_str)

        return {
            "success": True,
            "phone": phone,
            "pass_2fa": acc.get("password_2fa") or "None",
            "code": code or "Code not detected",
            "text": text,
            "date": date_str
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        try:
            await c.disconnect()
        except Exception:
            pass

async def change_email_for_account(phone, mode="login", log_callback=None):
    async def log(msg):
        if log_callback:
            try:
                await log_callback(f"[{phone}] {msg}")
            except Exception:
                pass
        print(f"[{phone}] {msg}", flush=True)

    acc = database.get_account(phone)
    if not acc or not acc.get("session"):
        await log("❌ Account session missing!")
        return {"success": False, "error": "No session"}

    c = get_client(acc["session"], phone=phone)
    try:
        await c.connect()
        if not await c.is_user_authorized():
            await log("❌ Session expired or unauthorized!")
            database.update_account_field(phone, "status", "unauthorized")
            return {"success": False, "error": "Unauthorized"}

        me = await c.get_me()
        device = acc.get("device_profile") or {}
        await log(f"👤 Connected: **{me.first_name}** (@{me.username or '-'}) | 🎭 Device: `{device.get('device_model', 'Default')}`")

        max_email_attempts = 4
        proxy_str = database.get_next_proxy(ENV_PROXY)

        for attempt in range(1, max_email_attempts + 1):
            try:
                await log(f"📧 Generating fresh Temp Email (Attempt {attempt}/{max_email_attempts})...")
                prov = get_temp_mailbox(proxy=proxy_str or None)
                new_email = prov.address
                await log(f"📫 Provider: `{prov.name}` | Mailbox: `{new_email}`")

                await log("📨 Telegram se verification code mangwa raha hoon...")
                if mode == "login":
                    req = functions.account.SendVerifyEmailCodeRequest(
                        purpose=types.EmailVerifyPurposeLoginChange(),
                        email=new_email
                    )
                else:
                    pwd_req = await safe_call(c, functions.account.GetPasswordRequest(), log_fn=log)
                    pwd_2fa = acc.get("password_2fa") or ""
                    from telethon.utils import compute_password_check
                    pwd_hash = compute_password_check(pwd_req, pwd_2fa) if pwd_req.has_password else b""
                    req = functions.account.SetRecoveryEmailRequest(email=new_email, password=pwd_hash)

                sent = await safe_call(c, req, log_fn=log)
                expected_len = getattr(sent, "length", 0) or 6
                await log(f"📩 Telegram code bheja gaya! Length: {expected_len} digits. Live Inbox Watch shuru...")

                # Auto poll inbox
                otp_code = None
                poll_deadline = time.time() + 115
                tick = 0
                while time.time() < poll_deadline:
                    await asyncio.sleep(4)
                    tick += 1
                    otp_code, body = prov.fetch_otp(length=expected_len)
                    if otp_code:
                        await log(f"🔑 **OTP AAGAYA! Code:** `{otp_code}`")
                        break
                    if tick % 6 == 0:
                        left = int(poll_deadline - time.time())
                        await log(f"⏳ Inbox polling chalu hai... ({left}s bache)")

                if not otp_code:
                    await log("❌ Inbox me OTP time par nahi aaya. Naye mailbox se try kar rahe hain...")
                    continue

                # Verify OTP with Telegram
                await log(f"🔄 Verifying `{otp_code}` with Telegram...")
                if mode == "login":
                    verify_req = functions.account.VerifyEmailRequest(
                        purpose=types.EmailVerifyPurposeLoginChange(),
                        verification=types.EmailVerificationCode(code=otp_code)
                    )
                    res = await safe_call(c, verify_req, log_fn=log)
                    final_email = getattr(res, "email", None) or new_email
                else:
                    final_email = new_email

                await log(f"🎉 **EMAIL CHANGE SUCCESS!** -> `{final_email}`")
                database.update_account_field(phone, "current_email", final_email)
                database.update_account_field(phone, "last_change_status", f"Success ({final_email}) at {time.strftime('%H:%M:%S')}")
                return {"success": True, "email": final_email}

            except RPCError as rpc:
                err_key, desc = explain_error(rpc)
                if err_key == "EMAIL_NOT_ALLOWED":
                    domain = new_email.split("@")[-1] if "@" in new_email else ""
                    if domain:
                        database.add_blocked_domain(domain)
                    await log(f"🚫 Global Blacklist: Domain `{domain}` Telegram ne reject kiya. Auto-blocked and retrying with another provider...")
                    continue
                else:
                    await log(f"❌ Telegram RPC Error: {err_key} ({desc})")
                    return {"success": False, "error": f"{err_key}: {desc}"}

        await log("❌ Saare temp-mail attempts fail ho gaye.")
        database.update_account_field(phone, "last_change_status", f"Failed (All attempts) at {time.strftime('%H:%M:%S')}")
        return {"success": False, "error": "All email attempts failed"}

    except Exception as e:
        await log(f"❌ Fatal Error: {e}")
        database.update_account_field(phone, "last_change_status", f"Failed: {str(e)[:40]}")
        return {"success": False, "error": str(e)}
    finally:
        try:
            await c.disconnect()
        except Exception:
            pass

async def change_all_accounts(mode="login", log_callback=None, filter_owner=None):
    settings = database.get_settings()
    delay_between = settings.get("delay_between_accs", 8)
    accs = database.get_accounts()
    
    if filter_owner:
        accs = {p: a for p, a in accs.items() if a.get("added_by") == filter_owner}

    if not accs:
        if log_callback:
            await log_callback("⚠️ Koi accounts available nahi hain!")
        return None

    total = len(accs)
    start_time = time.time()
    if log_callback:
        await log_callback(
            f"🚀 **[STARTING ALL ID RUN]**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 Total Accounts: `{total}`\n"
            f"🎭 Anti-Fingerprinting: `Active (30 Devices)`\n"
            f"🧠 Adaptive Concurrency: `Safe Pacing Mode`\n"
            f"⏱️ Delay Between IDs: `{delay_between}s`\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )

    success_list = []
    fail_list = []

    for i, (phone, acc_data) in enumerate(accs.items(), 1):
        if log_callback:
            await log_callback(f"\n▶️ **[{i}/{total}] Processing:** `{phone}`")
        res = await change_email_for_account(phone, mode=mode, log_callback=log_callback)
        if res.get("success"):
            success_list.append({"phone": phone, "email": res.get("email")})
        else:
            fail_list.append({"phone": phone, "error": res.get("error")})

        if i < total:
            await gaussian_delay(delay_between - 1.0, delay_between + 2.0)

    elapsed_sec = int(time.time() - start_time)
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": total,
        "success_count": len(success_list),
        "fail_count": len(fail_list),
        "duration_sec": elapsed_sec,
        "success_items": success_list,
        "fail_items": fail_list
    }
    database.add_report(report)

    summary_text = (
        f"📊 **[DETAILED FAILURE & SUCCESS REPORT]**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🕒 Time Completed: `{time.strftime('%H:%M:%S')}`\n"
        f"⏱️ Total Duration: `{elapsed_sec}s`\n"
        f"📱 Total IDs: `{total}`\n"
        f"✅ Successful: `{len(success_list)}`\n"
        f"❌ Failed: `{len(fail_list)}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )
    if success_list:
        summary_text += "🟢 **Successful Accounts:**\n"
        for s in success_list:
            summary_text += f"• `{s['phone']}` ➔ `{s['email']}`\n"
    if fail_list:
        summary_text += "\n🔴 **Detailed Failure Breakdown:**\n"
        for f in fail_list:
            summary_text += f"• `{f['phone']}`: `{f['error']}`\n"

    if log_callback:
        await log_callback(summary_text)

    return report
