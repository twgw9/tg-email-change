#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Telegram login/recovery email changer — ek account, ek run.
# python tg_email_change.py --status
# python tg_email_change.py --email aap@mail.com
# python tg_email_change.py --email aap@mail.com --recovery
# python tg_email_change.py --email aap@mail.com --notify
# python tg_email_change.py --notify --logout
# python tg_email_change.py --report
# pip install "telethon>=1.36"

import argparse
import asyncio
import getpass
import glob
import inspect
import json
import re
import os
import random
import sys
import time

from telethon import TelegramClient, functions, types
from telethon.errors import FloodError, FloodWaitError, RPCError, SessionPasswordNeededError

SESSION_NAME = "tg_session"
REPORT_STEM = "tg_email_report"
LOCK_FILE = "tg_email.lock"
MAX_WAIT = 3600
CALL_GAP = (0.8, 1.6)
API_ID = int(os.getenv("TG_API_ID", "0") or 0)
API_HASH = os.getenv("TG_API_HASH", "") or ""
ENV_2FA = os.getenv("TG_2FA_PASSWORD", "") or ""
ENV_PROXY = os.getenv("TG_PROXY", "") or ""

EVENTS = []
STARTED = None
ARGS = None
PROXY = None


def log(m=""):
    print(m, flush=True)


def rec(step, status, detail="", seconds=0):
    EVENTS.append({"time": time.strftime("%H:%M:%S"), "step": step, "status": status,
                   "detail": str(detail), "seconds": int(seconds or 0)})


class Stop(Exception):
    pass


def parse_proxy(url):
    if not url:
        return None
    from urllib.parse import urlparse, unquote
    u = urlparse(url if "://" in url else "socks5://" + url)
    if not u.hostname:
        raise ValueError("proxy URL galat hai")
    return {"proxy_type": (u.scheme or "socks5"), "addr": u.hostname, "port": int(u.port or 1080),
            "username": unquote(u.username) if u.username else None,
            "password": unquote(u.password) if u.password else None, "rdns": True}


HINTS = {
    "EMAIL_NOT_ALLOWED": "Telegram is email/domain ko allow nahi karta — dusra email do.",
    "EMAIL_INVALID": "Email spelling check karo.",
    "EMAIL_NOT_SETUP": "Is account par pehle koi login email set nahi hai. App me Settings > Privacy & Security > Login Email se set karo, phir ye script change kar sakti hai.",
    "EMAIL_NOT_MODIFIED": "Ye email pehle se hi set hai.",
    "EMAIL_UNCONFIRMED": "Purana email abhi confirm nahi hua — pehle usko confirm karo.",
    "EMAIL_HASH_EXPIRED": "Request expire — script dobara chalao.",
    "EMAIL_VERIFY_EXPIRED": "OTP expire — script dobara chalao.",
    "PASSWORD_HASH_INVALID": "2FA password galat tha.",
    "PHONE_CODE_INVALID": "Login code galat tha — script dobara chalao.",
    "PHONE_CODE_EXPIRED": "Login code expire — script dobara chalao.",
    "PHONE_NUMBER_INVALID": "Phone format galat hai (+91XXXXXXXXXX).",
    "SESSION_PASSWORD_NEEDED": "2FA password chahiye.",
    "AUTH_KEY_UNREGISTERED": "Session revoke ho chuki — tg_session.session delete karke dobara login karo.",
    "SESSION_REVOKED": "Session revoke ho gayi — tg_session.session delete karke dobara login karo.",
    "USER_DEACTIVATED_BAN": "Account banned/deactivated hai.",
    "USER_DEACTIVATED": "Account deactivated hai.",
    "PHONE_NUMBER_BANNED": "Ye number banned hai.",
    "API_ID_PUBLISHED_FLOOD": "api_id public hai — my.telegram.org se naya lo.",
}
ORDER = ["EMAIL_NOT_MODIFIED", "EMAIL_NOT_ALLOWED", "EMAIL_NOT_SETUP", "EMAIL_UNCONFIRMED",
         "EMAIL_HASH_EXPIRED", "EMAIL_VERIFY_EXPIRED", "EMAIL_INVALID", "PASSWORD_HASH_INVALID",
         "AUTH_KEY_UNREGISTERED", "SESSION_REVOKED", "USER_DEACTIVATED_BAN", "USER_DEACTIVATED",
         "PHONE_NUMBER_BANNED",
         "PHONE_NUMBER_INVALID", "PHONE_CODE_INVALID", "PHONE_CODE_EXPIRED",
         "API_ID_PUBLISHED_FLOOD", "SESSION_PASSWORD_NEEDED"]


def err_code(e):
    n = type(e).__name__
    if n in ("RPCError", "FloodError", "FloodWaitError"):
        return ""
    c = re.sub(r"(?<!^)(?=[A-Z])", "_", n).upper()
    return c[:-6] if c.endswith("_ERROR") else c


def explain(e):
    t = (str(e) + " " + err_code(e)).upper()
    for k in ORDER:
        if k in t:
            log("   [!] %s: %s" % (k, HINTS[k]))
            return k
    log("   [!] %s" % e)
    return None


async def tg(client, step, req, max_wait=MAX_WAIT):
    waited = 0
    while True:
        try:
            await asyncio.sleep(random.uniform(*CALL_GAP))
            r = req()
            r = await r if inspect.isawaitable(r) else await client(r)
            if waited:
                log("   [ok] %ds wait ke baad safal." % waited)
                rec(step, "ok", "floodwait %ds ke baad safal" % waited)
            return r
        except (FloodWaitError, FloodError) as e:
            s = int(getattr(e, "seconds", 0) or 0) + 1
            if waited + s > max_wait:
                rec(step, "fail", "floodwait %ds (limit se zyada)" % s)
                raise Stop("Telegram ne %d seconds ka flood-wait bola. %d second baad dobara chalao." % (s, s))
            log("   [wait] flood-wait %ds (abhi %s, resuming %s)"
                % (s, time.strftime("%H:%M:%S"), time.strftime("%H:%M:%S", time.localtime(time.time() + s))))
            rec(step, "floodwait", "%ds wait" % s, seconds=s)
            await asyncio.sleep(s)
            waited += s


def creds():
    a, h = API_ID, API_HASH
    if not a or not h:
        log("api_id / api_hash: my.telegram.org se lo, ya env TG_API_ID / TG_API_HASH daalo.")
        try:
            a = a or (input("api_id: ").strip() or "0")
            h = h or input("api_hash: ").strip()
        except EOFError:
            sys.exit("[!] api_id/api_hash nahi mile (env vars set karo).")
    try:
        a = int(a)
    except ValueError:
        sys.exit("[!] api_id number hona chahiye.")
    if not h:
        sys.exit("[!] api_hash khali hai.")
    return a, h


def ask_phone():
    try:
        return input("   Phone (+91XXXXXXXXXX): ").strip()
    except EOFError:
        raise Stop("Phone input nahi mila — interactive terminal me chalao.")


def ask_code():
    try:
        return input("   Telegram app/SMS me aaya login code: ").strip()
    except EOFError:
        raise Stop("Login code input nahi mila — interactive terminal me chalao.")


async def connect(a, h):
    kw = {}
    if PROXY:
        try:
            import python_socks  # noqa
        except ImportError:
            raise Stop("Proxy ke liye: pip install 'python-socks[asyncio]'")
        kw["proxy"] = PROXY
        log("   (proxy: %s://%s:%s)" % (PROXY["proxy_type"], PROXY["addr"], PROXY["port"]))
    c = TelegramClient(SESSION_NAME, a, h, **kw)
    try:
        await c.start(phone=ask_phone, code_callback=ask_code,
                      password=lambda: ENV_2FA or getpass.getpass("   Telegram 2FA password: "))
    except SessionPasswordNeededError:
        raise Stop("2FA password chahiye — dobara chalao.")
    except Stop:
        raise
    except (EOFError, KeyboardInterrupt):
        raise Stop("Login cancel ho gaya.")
    except RPCError as e:
        explain(e)
        raise Stop("Telegram login fail hua.")
    except OSError as e:
        raise Stop("Connect nahi ho paya (internet/proxy check karo): %s" % e)
    me = await c.get_me()
    who = ("%s %s" % (me.first_name or "", me.last_name or "")).strip() or "?"
    return c, "%s (@%s) +%s" % (who, me.username or "-", me.phone)


async def get_otp(length, label, email):
    log("")
    log("   ---------------- OTP ----------------")
    log("   Account : %s" % label)
    log("   Email   : %s" % email)
    log("   Digits  : %d" % length)
    log("   ------------------------------------")
    try:
        code = input("   OTP type karo: ").strip()
    except EOFError:
        raise Stop("OTP input nahi mila (non-interactive run).")
    if not code:
        raise Stop("OTP khali chhoda gaya.")
    rec("otp", "ok", "manual input")
    return code


async def get_2fa(pwd):
    if ENV_2FA:
        return ENV_2FA
    if pwd.has_password:
        if pwd.hint:
            log("   (2FA hint: %s)" % pwd.hint)
        pw = getpass.getpass("   Current 2FA password: ")
    else:
        log("   [!] 2FA set nahi hai — recovery email ke liye naya password banega.")
        pw = getpass.getpass("   NAYA 2FA password: ")
        if not pw:
            raise Stop("Password khali.")
        if getpass.getpass("   Dobara (confirm): ") != pw:
            raise Stop("Password match nahi kiya.")
    if not pw:
        raise Stop("2FA password nahi mila.")
    return pw


async def status(c):
    me = await c.get_me()
    log("\n[status]")
    log("  name     : %s %s" % (me.first_name or "", me.last_name or ""))
    log("  username : @%s" % (me.username or "-"))
    log("  id       : %s" % me.id)
    log("  phone    : +%s" % me.phone)
    p = await tg(c, "status", lambda: functions.account.GetPasswordRequest())
    log("  2FA      : %s" % ("ON" if p.has_password else "OFF"))
    if p.has_password and p.hint:
        log("  2FA hint : %s" % p.hint)
    log("  login email : %s" % (getattr(p, "login_email_pattern", None) or "(set nahi hai)"))
    log("  pending     : %s" % (getattr(p, "email_unconfirmed_pattern", None) or "(koi nahi)"))
    rec("status", "ok", getattr(p, "login_email_pattern", None) or "none")
    return p


async def change_login(c, email, label):
    p = await tg(c, "account", lambda: functions.account.GetPasswordRequest())
    if getattr(p, "email_unconfirmed_pattern", None):
        log("   [!] Pending email: %s" % p.email_unconfirmed_pattern)

    log("\n[1/4] code mangwa raha hoon: %s" % email)
    try:
        sent = await tg(c, "send_code", lambda: functions.account.SendVerifyEmailCodeRequest(
            purpose=types.EmailVerifyPurposeLoginChange(), email=email))
    except RPCError as e:
        explain(e)
        raise Stop("send_code fail hua.")
    log("   [ok] code -> %s (%d digits)" % (sent.email_pattern, sent.length))
    rec("send_code", "ok", sent.email_pattern)

    log("\n[2/4] OTP ...")
    log("\n[3/4] verify ...")
    for try_no in range(1, 4):
        code = await get_otp(sent.length, label, email)
        try:
            res = await tg(c, "verify_email", lambda: functions.account.VerifyEmailRequest(
                purpose=types.EmailVerifyPurposeLoginChange(),
                verification=types.EmailVerificationCode(code=code)))
            break
        except RPCError as e:
            k = explain(e)
            if k in ("EMAIL_VERIFY_EXPIRED", "EMAIL_HASH_EXPIRED"):
                log("   [retry] expire ho gaya — naya code mangwa raha hoon ...")
                sent = await tg(c, "send_code", lambda: functions.account.SendVerifyEmailCodeRequest(
                    purpose=types.EmailVerifyPurposeLoginChange(), email=email))
                rec("send_code", "ok", "resend")
                continue
            if k in ("PHONE_CODE_INVALID", "EMAIL_INVALID") or k is None:
                if try_no < 3:
                    log("   [retry] OTP galat — dobara try (%d/3)." % try_no)
                    continue
                raise Stop("OTP 3 baar galat raha.")
            raise Stop("%s: %s" % (k, HINTS[k]))
    else:
        raise Stop("OTP verify nahi ho paya.")

    log("\n[4/4] DONE")
    log("   LOGIN EMAIL CHANGE -> %s" % (getattr(res, "email", None) or email))
    rec("verify_email", "ok", getattr(res, "email", None) or email)
    return getattr(res, "email", None) or email


async def change_recovery(c, email, label):
    p = await tg(c, "account", lambda: functions.account.GetPasswordRequest())
    if getattr(p, "email_unconfirmed_pattern", None):
        log("   [!] Pending email: %s" % p.email_unconfirmed_pattern)

    log("\n[1/3] 2FA password ...")
    pw = await get_2fa(p)

    log("\n[2/3] recovery email set kar raha hoon: %s" % email)

    async def cb(length):
        return await get_otp(length, label, email)

    try:
        ok = await tg(c, "edit_2fa", lambda: c.edit_2fa(current_password=pw, new_password=pw,
                                                       email=email, email_code_callback=cb))
    except RPCError as e:
        explain(e)
        raise Stop("edit_2fa fail hua.")
    log("\n[3/3] %s" % ("RECOVERY EMAIL CHANGE -> %s" % email if ok else "Kuch change nahi hua."))
    rec("edit_2fa", "ok" if ok else "nochange", email if ok else "")
    return ok


def report(label, target, st, note):
    el = int(time.time() - STARTED) if STARTED else 0
    waits = [e for e in EVENTS if e["status"] == "floodwait"]
    total = sum(w["seconds"] for w in waits)
    data = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "account": label,
            "mode": "recovery-email" if (ARGS and ARGS.recovery) else "login-email",
            "target_email": target, "result": st, "note": note, "duration_sec": el,
            "events": EVENTS, "waits": waits}
    path = "%s_%s.json" % (REPORT_STEM, time.strftime("%Y%m%d_%H%M%S"))
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError:
        path = None
    log("\n" + "=" * 56)
    log("  REPORT")
    log("=" * 56)
    log("  account : %s" % label)
    log("  mode    : %s" % data["mode"])
    log("  target  : %s" % target)
    log("  result  : %s%s" % (st, (" — " + note) if note else ""))
    log("  time    : %ss" % el)
    log("  floodwait: %d baar%s" % (len(waits), (" (total %ds)" % total) if waits else ""))
    for w in waits:
        log("     - %s : %s" % (w["time"], w["detail"]))
    for e in EVENTS:
        if e["status"] in ("ok", "fail"):
            log("     [%s] %s : %s" % (e["status"], e["step"], e["detail"]))
    if path:
        log("  file    : %s" % path)
    log("=" * 56)
    return data


def notify_text(label, target, st, note, el):
    return ("TG EMAIL CHANGE — %s\naccount : %s\nmode    : %s\ntarget  : %s\ntime    : %ss%s"
            % (st, label, "recovery-email" if (ARGS and ARGS.recovery) else "login-email",
               target, el, ("\nnote    : " + note[:300]) if note else ""))


async def send_notify(c, text):
    if c is None:
        return
    try:
        await c.send_message("me", text)
        log("   (report Saved Messages me bhej di)")
    except Exception as e:
        log("   [!] Saved Messages me report nahi gayi: %s" % str(e)[:120])


def lock(force=False):
    if os.path.exists(LOCK_FILE):
        old = None
        try:
            with open(LOCK_FILE, encoding="utf-8") as f:
                old = int((f.read() or "0").strip() or 0)
        except (OSError, ValueError):
            old = None
        alive = False
        if old:
            try:
                os.kill(old, 0)
                alive = True
            except OSError:
                alive = False
        if alive and not force:
            sys.exit("[!] Script pehle se chal rahi hai (pid %s). --force-lock ya '%s' delete karo." % (old, LOCK_FILE))
    try:
        with open(LOCK_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass


def unlock():
    try:
        if os.path.exists(LOCK_FILE):
            with open(LOCK_FILE, encoding="utf-8") as f:
                if (f.read() or "").strip() == str(os.getpid()):
                    os.remove(LOCK_FILE)
    except OSError:
        pass


async def do_logout(c):
    log("\n[logout] session revoke ...")
    try:
        ok = await c.log_out()
    except RPCError as e:
        explain(e)
        raise Stop("Session revoke nahi ho payi.")
    log("   %s" % ("[ok] session revoke ho gayi." if ok else "[!] confirm nahi hua."))
    rec("logout", "ok" if ok else "warn", "")
    for f in (SESSION_NAME + ".session", SESSION_NAME + ".session-journal"):
        try:
            if os.path.exists(f):
                os.remove(f)
                log("   (delete: %s)" % f)
        except OSError:
            pass


def cmd_report():
    files = sorted(glob.glob(REPORT_STEM + "_*.json"))
    if not files:
        sys.exit("report file nahi mili.")
    with open(files[-1], encoding="utf-8") as f:
        d = json.load(f)
    waits = d.get("waits", [])
    log("=" * 56)
    log("  REPORT  %s" % files[-1])
    log("=" * 56)
    log("  account : %s" % d.get("account"))
    log("  mode    : %s" % d.get("mode"))
    log("  target  : %s" % d.get("target_email"))
    log("  result  : %s%s" % (d.get("result"), (" — " + d["note"]) if d.get("note") else ""))
    log("  time    : %ss" % d.get("duration_sec"))
    log("  floodwait: %d baar (total %ds)" % (len(waits), sum(w.get("seconds", 0) for w in waits)))
    for e in d.get("events", []):
        if e.get("status") in ("ok", "fail"):
            log("     [%s] %s : %s" % (e["status"], e["step"], e["detail"]))
    log("=" * 56)


async def run(args):
    global STARTED
    STARTED = time.time()
    a, h = creds()
    label, target, st, note = "(login pending)", args.email or "-", "FAILED", ""
    c = None
    try:
        target = args.email or "-"
        c, label = await connect(a, h)
        try:
            p = await tg(c, "account", lambda: functions.account.GetPasswordRequest())
        except RPCError:
            p = None
        log("=" * 56)
        log("  account : %s" % label)
        log("  mode    : %s" % ("recovery-email" if args.recovery else "login-email"))
        log("  target  : %s" % target)
        if p is not None:
            log("  2FA     : %s" % ("ON (hint: %s)" % p.hint if (p.has_password and p.hint)
                                    else ("ON" if p.has_password else "OFF")))
            log("  current : %s" % (getattr(p, "login_email_pattern", None) or "(set nahi hai)"))
        log("=" * 56)

        if args.logout:
            await do_logout(c)
            st, note = "OK", "logout"
            return 0
        if args.status:
            await status(c)
            st, note = "OK", "status"
            return 0

        if args.recovery:
            await change_recovery(c, target, label)
        else:
            await change_login(c, target, label)
        st = "OK"
        return 0
    except Stop as e:
        st, note = "STOPPED", str(e)
        log("\n[!] %s" % e)
        return 1
    except (KeyboardInterrupt, asyncio.CancelledError):
        st, note = "CANCELLED", "band kiya gaya"
        log("\nBand kar diya.")
        return 130
    finally:
        el = int(time.time() - STARTED) if STARTED else 0
        report(label, target, st, note)
        if args.notify and c is not None and not args.logout:
            await send_notify(c, notify_text(label, target, st, note, el))
        unlock()


def main():
    global ARGS, PROXY
    p = argparse.ArgumentParser(prog="tg_email_change.py", add_help=True)
    p.add_argument("--email")
    p.add_argument("--recovery", action="store_true")
    p.add_argument("--status", action="store_true")
    p.add_argument("--check", action="store_true")
    p.add_argument("--notify", action="store_true")
    p.add_argument("--logout", action="store_true")
    p.add_argument("--proxy")
    p.add_argument("--report", action="store_true")
    p.add_argument("--force-lock", action="store_true")
    args = p.parse_args()
    ARGS = args

    if args.report:
        cmd_report()
        return
    if args.check:
        args.status = True
    if os.getenv("TG_NOTIFY", "") in ("1", "true", "yes"):
        args.notify = True
    if args.proxy or ENV_PROXY:
        try:
            PROXY = parse_proxy(args.proxy or ENV_PROXY)
            log("   (proxy: %s://%s:%s)" % (PROXY["proxy_type"], PROXY["addr"], PROXY["port"]))
        except ValueError as e:
            p.error("--proxy galat: %s" % e)
    if not args.status and not args.email and not args.logout:
        p.error("--email EMAIL ya --status / --logout do")
    if args.email and ("@" not in args.email or " " in args.email):
        p.error("--email format theek nahi")

    lock(force=args.force_lock)
    rc = 0
    try:
        rc = asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nBand kar diya.")
        rc = 130
    finally:
        unlock()
    sys.exit(rc)


if __name__ == "__main__":
    main()
