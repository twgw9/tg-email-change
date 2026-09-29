#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==========================================================================
  TELEGRAM LOGIN / RECOVERY EMAIL CHANGER   v2.2   (apne account ke liye)
==========================================================================
Ek run = ek account. Jis account me aap khud logged-in ho, sirf usi ka
email ye script badal sakti hai (Telegram API isse zyada kuch deta hi nahi).

NAYA v2.2 me
------------
  * --notify : run ka result aapke Telegram "Saved Messages" me bhi aata hai
      (cron/server fail ho to phone par pata chal jata hai, alag bot nahi chahiye)

NAYA v2.1 me (OTP POWER)
-----------------------
  * LIVE OTP WATCH: inbox har poll par scan hoti hai — naya Telegram mail
      aate hi screen par dikhta hai ("[mail] naya Telegram mail: ..."),
      code milte hi timestamps ke saath deta hai
  * OTP EXPIRE ho gaya? Script khud Telegram se NAYA code mangwati hai
      (dobara haath se nahi karna padta) — sirf temp mode me
  * --watch-inbox : alag window me live OTP feed (koi bhi mail aaye dikhe)
  * --proxy socks5://... : Telegram + temp-mail dono proxy ke through
      (server par Telegram blocked ho to kaam aayega)
  * --check : session valid hai ya nahi + account status
  * --logout : server par session chhod ke na jaana ho to revoke karo

NAYA v2.0 me
------------
  * 4 temp-mail PROVIDERS: mail.tm, mail.gw, GuerrillaMail, 1secmail
      -> --providers (sabki live health check), --provider NAME (force karo)
      -> auto mode: ek provider fail ho to agla apne aap try hota hai
  * AUTO DOMAIN BLACKLIST: jo domain Telegram ne reject kiya
      (EMAIL_NOT_ALLOWED) wo yaad rakha jata hai aur dobara use nahi hota
      -> --blocked dekho, --clear-blocked saaf karo
  * OTP retry: galat OTP type hua to dobara poochta hai (code dobara
      bhejne ki zaroorat nahi), spaced digits ("1 2 3 4 5") bhi padh leta hai
  * --dry-run: sirf OTP aane tak test karo, verify mat karo
  * --report: pichhli run ki report dobara dikhao

COMMANDS
--------
  python tg_email_change_own.py --providers
  python tg_email_change_own.py --domains
  python tg_email_change_own.py --email aap@mail.com
  python tg_email_change_own.py --email aap@mail.com --recovery
  python tg_email_change_own.py --temp
  python tg_email_change_own.py --temp --provider guerrilla
  python tg_email_change_own.py --status
  python tg_email_change_own.py --inbox
  python tg_email_change_own.py --report
  python tg_email_change_own.py --blocked / --clear-blocked

FLOODWAIT / 2FA / SAFETY
------------------------
  * Telegram jitne seconds flood-wait bolta hai, utna poora WAIT karke
    retry hota hai (limit bypass nahi, respect hoti hai). 1 ghante se
    zyada bole to script ruk jati hai aur report deti hai.
  * 2FA password sirf prompt se leta hai, disk par save nahi hota.
    (Non-interactive ke liye TG_2FA_PASSWORD env var.)
  * Ant me report: steps, floodwaits, time -> tg_email_report_*.json

ZAROORAT
--------
  pip install "telethon>=1.36" requests
  api_id/api_hash: https://my.telegram.org  -> TG_API_ID / TG_API_HASH
==========================================================================
"""

import argparse
import asyncio
import getpass
import inspect
import json
import os
import random
import re
import string
import sys
import time

import requests
from telethon import TelegramClient, functions, types
from telethon.errors import (
    FloodError,
    FloodWaitError,
    RPCError,
    SessionPasswordNeededError,
)

# ----------------------------- CONFIG -----------------------------
SESSION_NAME = "tg_session"
TEMP_BACKUP = "tempmail_backup.json"     # temp mailbox details (--inbox ke liye)
BLOCKED_FILE = "blocked_domains.json"    # Telegram ne jo domains reject kiye
REPORT_STEM = "tg_email_report"
LOCK_FILE = "tg_email_change.lock"   # ek waqt me ek hi run (server/cron ke liye)

POLL_SEC = 5                 # temp inbox poll interval (--poll se badal sakte ho)
CODE_TIMEOUT = 300           # OTP ka max wait (--otp-timeout)
OTP_ATTEMPTS = 3             # galat OTP par kitni baar dobara poochhe
MAX_TOTAL_WAIT = 3600        # floodwait me itne se zyada wait nahi (1 ghanta)
CALL_GAP = (0.8, 1.6)        # API calls ke beech chhota gap

API_ID = int(os.getenv("TG_API_ID", "0") or 0)
API_HASH = os.getenv("TG_API_HASH", "") or ""
ENV_2FA = os.getenv("TG_2FA_PASSWORD", "") or ""

PROVIDER_ORDER = ["mail.tm", "mail.gw", "guerrilla", "1secmail"]

HTTP_PROXY = os.getenv("TG_PROXY", "") or ""     # --proxy / TG_PROXY se set hota hai
TELE_PROXY = None                                # parse kiya hua proxy dict (telethon ke liye)
EVENTS = []
STARTED_AT = None
ARGS = None
# ------------------------------------------------------------------


# ============================== COMMON ==============================

def now_str():
    return time.strftime("%H:%M:%S")


def log(msg=""):
    print(msg, flush=True)


def record(step, status, detail="", seconds=0):
    EVENTS.append({"time": now_str(), "step": step, "status": status,
                   "detail": str(detail), "seconds": int(seconds or 0)})


class UserStop(Exception):
    """Aage badhna bekaar — friendly message ke saath ruk jao."""


class EmailNotAllowed(Exception):
    """Telegram ne ye email/domain allow nahi kiya (temp mail me common)."""


class MailError(Exception):
    """Temp-mail provider ki taraf se problem."""


def extract_code(text, length=0):
    """Text/HTML me se Telegram ka numeric OTP nikaalo (spaced digits bhi)."""
    if not text:
        return None
    t = re.sub(r"<[^>]+>", " ", text).replace("&nbsp;", " ")
    if length:
        m = re.search(r"(?<!\d)\d{%d}(?!\d)" % int(length), t)
        if m:
            return m.group(0)
        m = re.search(r"(?<!\d)(\d(?:[ \u00a0]?\d){%d})(?!\d)" % (int(length) - 1), t)
        if m:
            return re.sub(r"\D", "", m.group(1))
    m = re.search(r"(?<!\d)\d{5,8}(?!\d)", t)
    if m:
        return m.group(0)
    m = re.search(r"(?<!\d)(\d(?:[ \u00a0]?\d){4,7})(?!\d)", t)
    return re.sub(r"\D", "", m.group(1)) if m else None


def parse_proxy(url):
    """socks5://user:pass@host:port ya http://host:port -> telethon/requests dono ke liye."""
    if not url:
        return None
    from urllib.parse import urlparse, unquote
    u = urlparse(url if "://" in url else "socks5://" + url)
    if not u.hostname:
        raise ValueError("proxy URL galat hai")
    return {"proxy_type": (u.scheme or "socks5"), "addr": u.hostname, "port": int(u.port or 1080),
            "username": unquote(u.username) if u.username else None,
            "password": unquote(u.password) if u.password else None, "rdns": True}


def proxy_to_url(proxy):
    if not proxy:
        return None
    auth = ""
    if proxy.get("username"):
        auth = "%s:%s@" % (proxy["username"], proxy["password"] or "")
    return "%s://%s%s:%s" % (proxy["proxy_type"], auth, proxy["addr"], proxy["port"])


def apply_requests_proxy(session):
    url = HTTP_PROXY if isinstance(HTTP_PROXY, str) else proxy_to_url(HTTP_PROXY)
    if url:
        session.proxies = {"http": url, "https": url}
    return session


def call_with_retry(fn, *a, **kw):
    last = None
    for i in range(3):
        try:
            return fn(*a, **kw)
        except requests.RequestException as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


# ============================== PROVIDERS ==============================

class BaseProvider:
    name = "base"
    interactive = True

    def domains(self):
        return []

    def create(self, blocked_domains=(), local_hint=None):
        raise NotImplementedError

    def messages(self):
        return []

    def read(self, mid):
        return ""

    # ---- common helpers ----
    @staticmethod
    def is_telegram(m):
        blob = ((m.get("from") or "") + " " + (m.get("subject") or "")).lower()
        return "telegram" in blob

    def code_from(self, m, length=0):
        body = self.read(m["id"]) or ""
        return extract_code(body, length) or extract_code(m.get("intro") or "", length)

    def latest_code(self, length=0):
        for m in self.messages():
            if not self.is_telegram(m):
                continue
            c = self.code_from(m, length)
            if c:
                return c, m
        return None, None

    def wait_code(self, length, timeout):
        """Live OTP watch: naya mail aate hi dikhata hai, code milte hi deta hai."""
        log("   [inbox] OTP watch ON -> %s  (%s | har %ds | max %ds)" % (self.address, self.name, POLL_SEC, timeout))
        started = time.time()
        deadline = started + timeout
        seen, tick, last_report = set(), 0, 0
        while time.time() < deadline:
            tick += 1
            try:
                msgs = self.messages()
            except MailError as e:
                log("   [!] inbox read error (phir try karunga): %s" % str(e)[:120])
                msgs = []
            for m in msgs:
                key = str(m.get("id"))
                if key not in seen:
                    seen.add(key)
                    if self.is_telegram(m):
                        log("   [mail] naya Telegram mail: %s  |  %s"
                            % ((m.get("subject") or "")[:70], m.get("date", "")))
            for m in msgs:
                if not self.is_telegram(m):
                    continue
                c = self.code_from(m, length)
                if c:
                    log("   [ok] OTP mil gaya (%ds me): %s" % (int(time.time() - started), c))
                    return c
            left = int(deadline - time.time())
            if left > 0 and time.time() - last_report > 30:
                log("   [wait] OTP ka intezaar — %ds bache | inbox me %d message" % (left, len(msgs)))
                last_report = time.time()
            time.sleep(max(1, POLL_SEC))
        raise MailError("%ds me %s par Telegram ka code nahi aaya" % (timeout, self.address))

    def to_backup(self):
        return {"provider": self.name, "address": self.address}

    def health(self):
        try:
            d = self.domains()
            return True, "%d domain: %s" % (len(d), ", ".join(d[:3]))
        except Exception as e:
            return False, "%s: %s" % (type(e).__name__, str(e)[:90])


class HydraProvider(BaseProvider):
    """mail.tm / mail.gw — same API software, different host."""

    def __init__(self, name, base):
        self.name = name
        self.base = base
        self.s = apply_requests_proxy(requests.Session())
        self.s.headers["Accept"] = "application/json"
        self.address = None
        self.password = None
        self.token = None

    @staticmethod
    def _rand(n, chars=string.ascii_lowercase + string.digits):
        return "".join(random.choices(chars, k=n))

    def _req(self, method, path, ok=(200, 201), **kw):
        kw.setdefault("timeout", 25)
        try:
            r = call_with_retry(self.s.request, method, self.base + path, **kw)
        except requests.RequestException as e:
            raise MailError("%s network/proxy error: %s" % (self.name, str(e)[:120]))
        if r.status_code not in ok:
            raise MailError("%s %s -> HTTP %s: %s" % (self.name, path, r.status_code, r.text[:160]))
        try:
            return r.json() if r.text else {}
        except ValueError:
            raise MailError("%s ne JSON nahi bheja (provider down/blocked ho sakta hai?)" % self.name)

    def domains(self):
        data = self._req("GET", "/domains?page=1")
        items = data if isinstance(data, list) else data.get("hydra:member", [])
        doms = [d["domain"] for d in items
                if not d.get("isDisabled") and d.get("isActive", True) and not d.get("isPrivate", False)]
        if not doms:
            raise MailError("%s par koi active domain nahi" % self.name)
        return doms

    def create(self, blocked_domains=(), local_hint=None):
        doms = [d for d in self.domains() if d.lower() not in blocked_domains]
        if not doms:
            raise MailError("%s ke saare domains blacklist me hain" % self.name)
        random.shuffle(doms)
        last = None
        for dom in doms[:5]:
            self.address = "%s@%s" % (local_hint or ("tg" + self._rand(9)), dom)
            self.password = self._rand(18, string.ascii_letters + string.digits)
            try:
                self._req("POST", "/accounts", json={"address": self.address, "password": self.password})
                self._login()
                return self
            except MailError as e:
                last = e
        raise last or MailError("%s par mailbox nahi bana" % self.name)

    def _login(self):
        data = self._req("POST", "/token", json={"address": self.address, "password": self.password})
        self.token = data.get("token")
        return self

    def _auth(self):
        if not self.token:
            self._login()
        return {"Authorization": "Bearer %s" % self.token}

    def messages(self):
        data = self._req("GET", "/messages?page=1", headers=self._auth())
        items = data if isinstance(data, list) else data.get("hydra:member", [])
        return [{"id": m["id"], "from": (m.get("from") or {}).get("address", ""),
                 "subject": m.get("subject", ""), "date": m.get("createdAt", "")[:19],
                 "intro": m.get("intro", "")} for m in items]

    def read(self, mid):
        full = self._req("GET", "/messages/%s" % mid, headers=self._auth())
        return (full.get("text") or "") + " " + " ".join(full.get("html") or [])

    def to_backup(self):
        return {"provider": self.name, "address": self.address, "password": self.password, "token": self.token}

    def load(self, d):
        self.address = d.get("address")
        self.password = d.get("password")
        self.token = d.get("token")
        return self


class GuerrillaProvider(BaseProvider):
    """api.guerrillamail.com — no signup, free, block-rotation built-in."""

    BASE = "https://api.guerrillamail.com/ajax.php"

    def __init__(self):
        self.name = "guerrilla"
        self.s = apply_requests_proxy(requests.Session())
        self.s.headers["User-Agent"] = "Mozilla/5.0"
        self.token = None
        self.address = None

    def _get(self, **params):
        params.setdefault("lang", "en")
        if self.token:
            params.setdefault("sid_token", self.token)
        try:
            r = call_with_retry(self.s.get, self.BASE, params=params, timeout=25)
        except requests.RequestException as e:
            raise MailError("guerrilla network/proxy error: %s" % str(e)[:120])
        if r.status_code != 200:
            raise MailError("guerrilla HTTP %s" % r.status_code)
        try:
            j = r.json()
        except ValueError:
            raise MailError("guerrilla ne JSON nahi bheja (provider down?)")
        if j.get("sid_token"):
            self.token = j["sid_token"]
        return j

    def domains(self):
        j = self._get(f="get_email_address")
        addr = j.get("email_addr") or ""
        return [addr.split("@")[-1]] if "@" in addr else ["guerrillamailblock.com"]

    def create(self, blocked_domains=(), local_hint=None):
        j = self._get(f="get_email_address")
        if j.get("email_addr"):
            self.address = j["email_addr"]
        user = local_hint or ("tg" + "".join(random.choices(string.ascii_lowercase + string.digits, k=9)))
        for attempt in range(3):
            try:
                j2 = self._get(f="set_email_user", email_user=user)
                if j2.get("email_addr"):
                    self.address = j2["email_addr"]
                    break
            except MailError:
                user = "tg" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        if not self.address:
            raise MailError("guerrilla par address nahi mila")
        return self

    def messages(self):
        j = self._get(f="check_email", seq=0)
        out = []
        for m in j.get("list", []) or []:
            out.append({"id": m.get("mail_id"), "from": m.get("mail_from", ""),
                        "subject": m.get("mail_subject", ""), "date": m.get("mail_date", ""),
                        "intro": m.get("mail_excerpt", "")})
        return out

    def read(self, mid):
        j = self._get(f="fetch_email", email_id=mid)
        return (j.get("mail_body") or "") + " " + (j.get("mail_excerpt") or "")

    def to_backup(self):
        return {"provider": self.name, "address": self.address, "token": self.token}

    def load(self, d):
        self.address = d.get("address")
        self.token = d.get("token")
        return self


class OneSecMailProvider(BaseProvider):
    """1secmail — free, kai baar down rehta hai, isliye auto mode me last me."""

    BASE = "https://www.1secmail.com/api/v1/"

    def __init__(self):
        self.name = "1secmail"
        self.s = apply_requests_proxy(requests.Session())
        self.s.headers["User-Agent"] = "curl/8.0"
        self.address = None
        self.login = None
        self.domain = None

    def _get(self, **params):
        try:
            r = call_with_retry(self.s.get, self.BASE, params=params, timeout=25)
        except requests.RequestException as e:
            raise MailError("1secmail network/proxy error: %s" % str(e)[:120])
        if r.status_code != 200:
            raise MailError("1secmail HTTP %s (provider down/blocked)" % r.status_code)
        try:
            return r.json()
        except ValueError:
            raise MailError("1secmail ne JSON nahi bheja")

    def domains(self):
        d = self._get(action="getDomainList")
        if not isinstance(d, list) or not d:
            raise MailError("1secmail par domain nahi mile")
        return d

    def create(self, blocked_domains=(), local_hint=None):
        doms = [d for d in self.domains() if d.lower() not in blocked_domains]
        if not doms:
            raise MailError("1secmail ke saare domains blacklist me hain")
        self.domain = random.choice(doms)
        self.login = local_hint or ("tg" + "".join(random.choices(string.ascii_lowercase + string.digits, k=9)))
        self.address = "%s@%s" % (self.login, self.domain)
        return self

    def messages(self):
        data = self._get(action="getMessages", login=self.login, domain=self.domain)
        return [{"id": m.get("id"), "from": m.get("from", ""), "subject": m.get("subject", ""),
                 "date": m.get("date", ""), "intro": ""} for m in (data or [])]

    def read(self, mid):
        j = self._get(action="readMessage", login=self.login, domain=self.domain, id=mid)
        return (j.get("textBody") or "") + " " + (j.get("htmlBody") or "")

    def to_backup(self):
        return {"provider": self.name, "address": self.address}


PROVIDER_FACTORY = {
    "mail.tm": lambda: HydraProvider("mail.tm", "https://api.mail.tm"),
    "mail.gw": lambda: HydraProvider("mail.gw", "https://api.mail.gw"),
    "guerrilla": GuerrillaProvider,
    "1secmail": OneSecMailProvider,
}


# --------------------------- BLOCKED DOMAINS ---------------------------

def load_blocked():
    if not os.path.exists(BLOCKED_FILE):
        return {}
    try:
        with open(BLOCKED_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_blocked(d):
    try:
        with open(BLOCKED_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
        os.chmod(BLOCKED_FILE, 0o600)
    except OSError as e:
        log("   [!] blocklist save nahi hui: %s" % e)


def block_domain(address, reason="EMAIL_NOT_ALLOWED"):
    dom = (address or "").split("@")[-1].lower()
    if not dom:
        return
    d = load_blocked()
    d[dom] = {"reason": reason, "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    save_blocked(d)
    log("   [!] '%s' ko auto-blocklist me daal diya (%s) — aage ise skip karunga." % (dom, reason))
    record("blocklist", "add", dom)


class MailboxPool:
    """Provider + blocked-domain logic: naya mailbox laao, zaroorat par switch karo."""

    def __init__(self, provider="auto", local_hint=None):
        self.order = PROVIDER_ORDER if provider == "auto" else [provider]
        self.local_hint = local_hint
        self.map = {p: k for k, p in enumerate(self.order)}
        self.current = None

    def blocked(self):
        return set(load_blocked().keys())

    def _try_provider(self, pname, blocked):
        try:
            prov = PROVIDER_FACTORY[pname]()
        except KeyError:
            raise MailError("unknown provider: %s" % pname)
        prov.create(blocked_domains=blocked, local_hint=self.local_hint)
        return prov

    def next_mailbox(self, failed_providers=()):
        blocked = self.blocked()
        log("   [mail] mailbox banane ki koshish — order: %s | blocked domains: %d"
            % (", ".join(self.order), len(blocked)))
        last_err = None
        for pname in self.order:
            if pname in failed_providers:
                continue
            try:
                prov = self._try_provider(pname, blocked)
                log("   [mail] mila: %s  (%s)" % (prov.address, pname))
                record("mailbox", "ok", "%s via %s" % (prov.address, pname))
                self.current = prov
                return prov
            except Exception as e:
                last_err = e
                log("   [mail] %s fail: %s" % (pname, str(e)[:120]))
                record("mailbox", "fail", "%s: %s" % (pname, str(e)[:120]))
        raise MailError("koi bhi provider kaam nahi kiya. Last error: %s" % last_err)


def save_temp_backup(prov):
    try:
        with open(TEMP_BACKUP, "w", encoding="utf-8") as f:
            json.dump(prov.to_backup(), f, indent=2)
        os.chmod(TEMP_BACKUP, 0o600)
        log("   (mailbox details '%s' me saved — --inbox se baad me khul sakta hai)" % TEMP_BACKUP)
    except OSError as e:
        log("   [!] mailbox details save nahi hui: %s" % e)


def load_temp_backup():
    if not os.path.exists(TEMP_BACKUP):
        raise UserStop("'%s' nahi mila — pehle ek baar --temp se chalao." % TEMP_BACKUP)
    with open(TEMP_BACKUP, encoding="utf-8") as f:
        d = json.load(f)
    pname = d.get("provider", "mail.tm")
    prov = PROVIDER_FACTORY[pname]()
    if hasattr(prov, "load"):
        prov.load(d)
    return prov, d


# ============================== TELEGRAM ==============================

RPC_HINTS = {
    "EMAIL_NOT_ALLOWED": "Telegram is email/domain ko allow nahi karta (kuch temp domains blocked hote hain). "
                         "Script khud dusra domain/provider try karegi — ya --email se apna real email do.",
    "EMAIL_INVALID": "Email address galat lag raha hai — spelling check karo.",
    "EMAIL_NOT_SETUP": "Is account par abhi LOGIN email set hi nahi hai, isliye 'change' nahi ho sakta. "
                       "Pehla login email Telegram app (Settings > Privacy & Security > Login Email) "
                       "ya login ke waqt set hota hai. Uske baad ye script change kar sakti hai.",
    "EMAIL_NOT_MODIFIED": "Ye email pehle se hi set hai — badalne ki zaroorat nahi.",
    "EMAIL_UNCONFIRMED": "Ek purana email abhi tak confirm nahi hua — pehle usko confirm karo.",
    "EMAIL_HASH_EXPIRED": "Verification request expire — script dobara chalao.",
    "EMAIL_VERIFY_EXPIRED": "OTP ki validity khatam — script dobara chalao.",
    "PASSWORD_HASH_INVALID": "2FA password galat tha.",
    "PASSWORD_MISSING": "2FA password diya hi nahi gaya.",
    "PHONE_CODE_INVALID": "Telegram login code galat tha — script dobara chalao.",
    "PHONE_CODE_EXPIRED": "Telegram login code expire — script dobara chalao.",
    "PHONE_NUMBER_INVALID": "Phone number ka format galat hai (+91XXXXXXXXXX jaisa).",
    "SESSION_PASSWORD_NEEDED": "Account par 2FA laga hai — 2FA password chahiye.",
    "AUTH_KEY_UNREGISTERED": "Session revoke ho chuki — tg_session file delete karke dobara login karo.",
    "SESSION_REVOKED": "Session revoke ho gayi — tg_session file delete karke dobara login karo.",
    "USER_DEACTIVATED_BAN": "Ye account Telegram ne ban kar diya hai.",
    "USER_DEACTIVATED": "Ye account deactivated hai.",
    "PHONE_NUMBER_BANNED": "Ye phone number Telegram par banned hai.",
    "API_ID_PUBLISHED_FLOOD": "Ye api_id public/published hai — my.telegram.org se naya lo.",
}
_HINT_ORDER = ["EMAIL_NOT_MODIFIED", "EMAIL_NOT_ALLOWED", "EMAIL_NOT_SETUP", "EMAIL_UNCONFIRMED",
               "EMAIL_HASH_EXPIRED", "EMAIL_VERIFY_EXPIRED", "EMAIL_INVALID",
               "PASSWORD_HASH_INVALID", "PASSWORD_MISSING", "AUTH_KEY_UNREGISTERED",
               "SESSION_REVOKED", "USER_DEACTIVATED_BAN", "USER_DEACTIVATED", "PHONE_NUMBER_BANNED",
               "PHONE_NUMBER_INVALID", "PHONE_CODE_INVALID", "PHONE_CODE_EXPIRED",
               "API_ID_PUBLISHED_FLOOD", "SESSION_PASSWORD_NEEDED"]


def err_code(exc):
    n = type(exc).__name__
    if n in ("RPCError", "FloodError", "FloodWaitError"):
        return ""
    c = re.sub(r"(?<!^)(?=[A-Z])", "_", n).upper()
    return c[:-6] if c.endswith("_ERROR") else c


def explain_error(exc):
    text = (str(exc) + " " + err_code(exc)).upper()
    for key in _HINT_ORDER:
        if key in text:
            log("   [!] %s" % key)
            log("       %s" % RPC_HINTS[key])
            return key
    log("   [!] Telegram error: %s" % exc)
    return None


async def tg_call(client, step, make_request, max_wait=MAX_TOTAL_WAIT):
    """Ek Telegram request; FloodWait aaye to poora wait karke retry."""
    waited, attempt = 0, 0
    while True:
        attempt += 1
        try:
            await asyncio.sleep(random.uniform(*CALL_GAP))
            res = make_request()
            res = await res if inspect.isawaitable(res) else await client(res)
            if waited:
                log("   [ok] %ds flood-wait ke baad request safal." % waited)
                record(step, "ok", "flood-wait %ds ke baad safal" % waited)
            return res
        except (FloodWaitError, FloodError) as e:
            secs = int(getattr(e, "seconds", 0) or 0) + 1
            if waited + secs > max_wait:
                record(step, "fail", "FloodWait %ds (max wait se zyada)" % secs)
                raise UserStop("Telegram ne %d seconds ka flood-wait bola. Itni der nahi ruka — "
                               "%d second baad dobara chalao (report file me detail hai)." % (secs, secs))
            log("   [wait] Telegram: %ds flood-wait (attempt %d). Poora wait karunga..." % (secs, attempt))
            log("          abhi %s | resuming ~%s" % (now_str(),
                                                      time.strftime("%H:%M:%S", time.localtime(time.time() + secs))))
            record(step, "floodwait", "%ds wait (attempt %d)" % (secs, attempt), seconds=secs)
            await asyncio.sleep(secs)
            waited += secs


def ensure_api_creds():
    api_id, api_hash = API_ID, API_HASH
    if not api_id or not api_hash:
        log("api_id / api_hash chahiye — https://my.telegram.org > API development tools (free).")
        log("(ya env vars: TG_API_ID / TG_API_HASH)\n")
        try:
            api_id = api_id or (input("api_id: ").strip() or "0")
            api_hash = api_hash or input("api_hash: ").strip()
        except EOFError:
            sys.exit("[!] api_id/api_hash nahi mile. Env vars set karo:\n"
                     "    export TG_API_ID=1234567 TG_API_HASH=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    try:
        api_id = int(api_id)
    except ValueError:
        sys.exit("[!] api_id number hona chahiye.")
    if not api_hash:
        sys.exit("[!] api_hash khali hai.")
    return api_id, api_hash


def _ask_phone():
    log("   (pehli baar: Telegram app me aaya login code dena hoga)")
    try:
        return input("   Phone (+91XXXXXXXXXX): ").strip()
    except EOFError:
        raise UserStop("Phone input nahi mila — interactive terminal me chalao.")


def _ask_login_code():
    try:
        return input("   Telegram app/SMS me aaya login code: ").strip()
    except EOFError:
        raise UserStop("Login code input nahi mila — interactive terminal me chalao.")


async def connect_telegram(api_id, api_hash):
    kwargs = {}
    if TELE_PROXY:
        try:
            import python_socks  # noqa: F401
        except ImportError:
            raise UserStop("Proxy use karne ke liye pehle ye install karo:\n"
                           "    pip install 'python-socks[asyncio]'")
        kwargs["proxy"] = TELE_PROXY
        log("   (proxy use ho raha hai: %s://%s:%s)" % (TELE_PROXY["proxy_type"], TELE_PROXY["addr"], TELE_PROXY["port"]))
    client = TelegramClient(SESSION_NAME, api_id, api_hash, **kwargs)
    try:
        await client.start(phone=_ask_phone, code_callback=_ask_login_code,
                           password=lambda: ENV_2FA or getpass.getpass("Telegram 2FA password: "))
    except SessionPasswordNeededError:
        raise UserStop("2FA password chahiye — dobara chalao aur password daalo.")
    except UserStop:
        raise
    except (EOFError, KeyboardInterrupt):
        raise UserStop("Login cancel ho gaya.")
    except RPCError as e:
        explain_error(e)
        raise UserStop("Telegram login fail hua.")
    except OSError as e:
        raise UserStop("Telegram se connect nahi ho paya (internet check karo): %s" % e)
    me = await client.get_me()
    who = "%s%s" % (me.first_name or "", (" " + me.last_name) if me.last_name else "")
    label = "%s (@%s) +%s" % (who.strip() or "?", me.username or "-", me.phone)
    return client, label


def print_header(label, mode, target_email, pwd=None, provider=None):
    log("=" * 64)
    log("  TELEGRAM EMAIL CHANGE  —  apne account ke liye  (v2.0)")
    log("=" * 64)
    log("  Account  : %s" % label)
    log("  Mode     : %s" % mode)
    log("  Target   : %s" % target_email)
    if provider:
        log("  Provider : %s" % provider)
    if pwd is not None:
        log("  2FA      : %s" % ("set (hint: %s)" % pwd.hint if pwd.has_password and pwd.hint
                                 else ("set" if pwd.has_password else "set nahi hai")))
        pending = getattr(pwd, "email_unconfirmed_pattern", None)
        if pending:
            log("  Pending  : %s (confirm nahi hua)" % pending)
        log("  Current  : %s" % (getattr(pwd, "login_email_pattern", None) or "(login email set nahi hai)"))
    log("=" * 64)


async def show_status(client):
    log("\n[status] account details ...")
    me = await client.get_me()
    log("  name     : %s%s" % (me.first_name or "", (" " + me.last_name) if me.last_name else ""))
    log("  username : @%s" % (me.username or "-"))
    log("  id       : %s" % me.id)
    log("  phone    : +%s" % me.phone)
    pwd = await tg_call(client, "status", lambda: functions.account.GetPasswordRequest())
    log("  2FA      : %s" % ("ON" if pwd.has_password else "OFF"))
    if pwd.has_password and pwd.hint:
        log("  2FA hint : %s" % pwd.hint)
    log("  login email (pattern) : %s" % (getattr(pwd, "login_email_pattern", None) or "(set nahi hai)"))
    log("  pending email         : %s" % (getattr(pwd, "email_unconfirmed_pattern", None) or "(koi nahi)"))
    log("  NOTE: pattern me * hota hai — poora email Telegram sirf aapko dikhata hai.")
    record("status", "ok", "login_email_pattern=%s" % (getattr(pwd, "login_email_pattern", None) or "none"))
    return pwd


async def make_code_getter(prov, target_email, label):
    """OTP: temp-inbox se auto; warna screen par banner + aap type karo."""

    async def get_code(length):
        if prov is not None:
            try:
                code = await asyncio.to_thread(prov.wait_code, length, ARGS.otp_timeout)
                log("   [ok] inbox se OTP mil gaya: %s" % code)
                record("otp", "ok", "temp inbox se auto")
                return code
            except MailError as e:
                log("   [!] %s" % e)
        log("")
        log("   ---------------- OTP CHAHIYE ----------------")
        log("   Account : %s" % label)
        log("   Email   : %s   <-- OTP yahan aaya hai" % target_email)
        log("   Digits  : %d" % length)
        log("   --------------------------------------------")
        try:
            code = await asyncio.to_thread(lambda: input("   OTP type karo: ").strip())
        except EOFError:
            raise UserStop("OTP input nahi mila (non-interactive run).")
        if not code:
            raise UserStop("OTP khali chhoda gaya — script rok di.")
        record("otp", "ok", "manual input")
        return code

    return get_code


def ask_2fa_password(has_password, hint=None):
    if ENV_2FA:
        log("   (2FA password env var se liya gaya)")
        return ENV_2FA
    if has_password:
        if hint:
            log("   (2FA hint: %s)" % hint)
        pw = getpass.getpass("   Current 2FA password (screen par nahi dikhega): ")
    else:
        log("   [!] Is account par 2FA set nahi hai — recovery email password ke bina set nahi hota,")
        log("       isliye ek naya 2FA password banaya jayega (~10 sec).")
        pw = getpass.getpass("   NAYA 2FA password: ")
        if not pw:
            raise UserStop("2FA password khali — rok diya.")
        if getpass.getpass("   Dobara wahi password (confirm): ") != pw:
            raise UserStop("Dono password match nahi kiye — dobara chalao.")
    if not pw:
        raise UserStop("2FA password nahi mila.")
    return pw


def raise_if_email_not_allowed(exc, step):
    key = explain_error(exc)
    if key == "EMAIL_NOT_ALLOWED":
        raise EmailNotAllowed(str(exc))
    if key:
        raise UserStop("%s: %s" % (key, RPC_HINTS[key]))
    raise UserStop("Telegram error (%s): %s" % (step, exc))


async def _verify_with_retries(client, get_code, length, purpose):
    """OTP verify karo; galat code par dobara poochta hai (naya code bhejne ki zaroorat nahi)."""
    last_key = None
    for attempt in range(1, OTP_ATTEMPTS + 1):
        code = await get_code(length)
        try:
            return await tg_call(client, "verify_email", lambda c=code: client(
                functions.account.VerifyEmailRequest(
                    purpose=purpose, verification=types.EmailVerificationCode(code=c))))
        except RPCError as e:
            last_key = explain_error(e)
            if last_key in ("PHONE_CODE_INVALID", "EMAIL_VERIFY_EXPIRED", "EMAIL_HASH_EXPIRED",
                            "EMAIL_INVALID") or last_key is None:
                if last_key in ("EMAIL_VERIFY_EXPIRED", "EMAIL_HASH_EXPIRED"):
                    raise UserStop("%s — script dobara chalao (naya code aayega)." % last_key)
                if attempt < OTP_ATTEMPTS:
                    log("   [retry] OTP galat lag raha hai — dobara try karo (%d/%d)." % (attempt, OTP_ATTEMPTS))
                    record("otp", "retry", "galat OTP attempt %d" % attempt)
                    continue
                raise UserStop("OTP %d baar galat raha — script dobara chalao." % OTP_ATTEMPTS)
            if last_key == "EMAIL_NOT_ALLOWED":
                raise EmailNotAllowed(str(e))
            raise UserStop("%s: %s" % (last_key, RPC_HINTS[last_key]))


async def change_login_email(client, new_email, get_code):
    pwd = await tg_call(client, "account", lambda: functions.account.GetPasswordRequest())
    pending = getattr(pwd, "email_unconfirmed_pattern", None)
    if pending:
        log("   [!] Ek email pehle se pending hai: %s (Telegram pehle usko confirm karwata hai)" % pending)

    log("\n[1/4] naye email par verification code mangwa raha hoon: %s" % new_email)
    try:
        sent = await tg_call(client, "send_code", lambda: functions.account.SendVerifyEmailCodeRequest(
                purpose=types.EmailVerifyPurposeLoginChange(), email=new_email))
    except RPCError as e:
        raise_if_email_not_allowed(e, "send_code")
    log("   [ok] code bhej diya -> %s (%d digits)" % (sent.email_pattern, sent.length))
    record("send_code", "ok", sent.email_pattern)

    log("\n[2/4] OTP ka intezaar ...")
    try:
        code = await get_code(sent.length)
    except MailError as e:
        log("   [!] %s" % e)
        log("   [retry] purana code expire ho gaya lagta hai — Telegram se NAYA code mangwa raha hoon...")
        sent = await tg_call(client, "send_code", lambda: functions.account.SendVerifyEmailCodeRequest(
                purpose=types.EmailVerifyPurposeLoginChange(), email=new_email))
        log("   [ok] naya code bheja -> %s (%d digits)" % (sent.email_pattern, sent.length))
        record("send_code", "ok", "resend -> %s" % sent.email_pattern)
        code = await get_code(sent.length)

    if ARGS.dry_run:
        log("\n[dry-run] OTP mil gaya (%s) par verify NAHI kiya (--dry-run). Kuch change nahi hua." % code)
        record("verify_email", "skipped", "dry-run")
        return None

    log("\n[3/4] OTP verify kar raha hoon ...")
    res = await _verify_with_retries(client, get_code, sent.length, types.EmailVerifyPurposeLoginChange())

    final = getattr(res, "email", None) or new_email
    log("\n[4/4] DONE ✔")
    log("   ==================================================")
    log("   LOGIN EMAIL CHANGE HO GAYA -> %s" % final)
    log("   ==================================================")
    record("verify_email", "ok", "new login email = %s" % final)
    return final


async def change_recovery_email(client, new_email, get_code):
    pwd = await tg_call(client, "account", lambda: functions.account.GetPasswordRequest())
    pending = getattr(pwd, "email_unconfirmed_pattern", None)
    if pending:
        log("   [!] Pending email: %s" % pending)

    log("\n[1/3] 2FA password ...")
    cur_pw = ask_2fa_password(pwd.has_password, getattr(pwd, "hint", None))

    log("\n[2/3] naya recovery email set kar raha hoon: %s" % new_email)

    async def cb(length):
        return await get_code(length)

    try:
        ok = await tg_call(client, "edit_2fa", lambda: client.edit_2fa(
            current_password=cur_pw, new_password=cur_pw, email=new_email, email_code_callback=cb))
    except RPCError as e:
        key = explain_error(e)
        if key == "EMAIL_UNCONFIRMED":
            raise UserStop("Pehle purana pending email confirm karo, phir dobara chalao.")
        if key == "PASSWORD_HASH_INVALID":
            raise UserStop("2FA password galat — dhyaan se dobara chalao.")
        if key == "EMAIL_NOT_ALLOWED":
            raise EmailNotAllowed(str(e))
        if key:
            raise UserStop("%s: %s" % (key, RPC_HINTS[key]))
        raise UserStop("Telegram error (edit_2fa): %s" % e)

    log("\n[3/3] DONE ✔")
    if ok:
        log("   ==================================================")
        log("   RECOVERY EMAIL CHANGE HO GAYA -> %s" % new_email)
        log("   ==================================================")
        record("edit_2fa", "ok", "recovery email = %s" % new_email)
    else:
        log("   [!] Telegram ne kuch change nahi kiya.")
        record("edit_2fa", "nochange", "")
    return ok


async def do_logout(client):
    """Server par session chhod ke jaana ho to — session revoke + files delete."""
    log("\n[logout] is machine par se session revoke kar raha hoon ...")
    try:
        ok = await client.log_out()
    except RPCError as e:
        explain_error(e)
        raise UserStop("Session revoke nahi ho payi.")
    log("   %s" % ("[ok] session revoke ho gayi (Telegram me ye device logout ho gaya)." if ok
                   else "[!] Telegram ne confirm nahi kiya, par local files hata raha hoon."))
    record("logout", "ok" if ok else "warn", "session revoke")
    for f in (SESSION_NAME + ".session", SESSION_NAME + ".session-journal"):
        try:
            if os.path.exists(f):
                os.remove(f)
                log("   (file delete: %s)" % f)
        except OSError as e:
            log("   [!] %s delete nahi hui: %s" % (f, e))
    return ok


# ============================== REPORT ==============================

def write_report(label, target_email, status, note="", provider=None):
    elapsed = int(time.time() - STARTED_AT) if STARTED_AT else 0
    stamp = time.strftime("%Y%m%d_%H%M%S")
    data = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "account": label,
        "mode": ("recovery-email" if (ARGS and ARGS.recovery) else "login-email") if ARGS else "-",
        "target_email": target_email,
        "provider": provider,
        "result": status,
        "note": note,
        "duration_sec": elapsed,
        "events": EVENTS,
        "waits": [e for e in EVENTS if e["status"] == "floodwait"],
    }
    path = "%s_%s.json" % (REPORT_STEM, stamp)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError as e:
        path = None
        log("   [!] report save nahi hui: %s" % e)
    print_report(data, path)
    return path


def print_report(data, path=None):
    waits = data.get("waits", [])
    total_wait = sum(int(w.get("seconds", 0)) for w in waits)
    log("\n" + "=" * 64)
    log("  REPORT")
    log("=" * 64)
    log("  account   : %s" % data.get("account"))
    log("  mode      : %s" % data.get("mode"))
    if data.get("provider"):
        log("  provider  : %s" % data.get("provider"))
    log("  target    : %s" % data.get("target_email"))
    log("  result    : %s%s" % (data.get("result"), ("  — " + data["note"]) if data.get("note") else ""))
    log("  time      : %ss" % data.get("duration_sec"))
    log("  floodwait : %d baar%s" % (len(waits), (" (total %ds rukna pada)" % total_wait) if waits else ""))
    for w in waits:
        log("     - %s : %s" % (w["time"], w["detail"]))
    log("  steps     :")
    for e in data.get("events", []):
        if e.get("status") in ("ok", "fail", "add", "retry", "skipped"):
            log("     - [%s] %s : %s" % (e["status"], e["step"], e["detail"]))
    if path:
        log("  file      : %s" % path)
    log("=" * 64)


# ============================== CLI TOOLS ==============================

def cmd_providers():
    log("=" * 64)
    log("  TEMP MAIL PROVIDERS — live health check")
    log("=" * 64)
    for name in PROVIDER_ORDER:
        try:
            ok, info = PROVIDER_FACTORY[name]().health()
        except Exception as e:
            ok, info = False, "%s: %s" % (type(e).__name__, str(e)[:80])
        log("  %-10s %s  %s" % (name, "OK  " if ok else "FAIL", info))
    log("-" * 64)
    log("  blocked domains (Telegram ne reject kiye): %d" % len(load_blocked()))
    for dom, meta in load_blocked().items():
        log("     - %s  (%s, %s)" % (dom, meta.get("reason"), meta.get("time")))
    log("=" * 64)


def cmd_domains():
    log("=" * 64)
    log("  AVAILABLE DOMAINS")
    log("=" * 64)
    blocked = load_blocked()
    for name in PROVIDER_ORDER:
        try:
            doms = PROVIDER_FACTORY[name]().domains()
        except Exception as e:
            log("  %-10s : ERROR %s" % (name, str(e)[:80]))
            continue
        for d in doms:
            log("  %-10s : %-32s %s" % (name, d, "[BLOCKED]" if d.lower() in blocked else ""))
    log("=" * 64)


def cmd_inbox():
    prov, d = load_temp_backup()
    if getattr(prov, "token", None) is None and prov.name in ("mail.tm", "mail.gw", "guerrilla"):
        prov.login() if hasattr(prov, "login") else None
    try:
        msgs = prov.messages()
    except MailError as e:
        sys.exit("Inbox nahi khula (mailbox expire ho gaya?): %s" % e)
    code, latest = prov.latest_code(0)
    log("=" * 64)
    log("  TEMP INBOX")
    log("=" * 64)
    log("  provider   : %s" % d.get("provider", prov.name))
    log("  email      : %s" % prov.address)
    log("  messages   : %d" % len(msgs))
    log("  latest OTP : %s" % (code or "(koi Telegram code nahi mila)"))
    if latest:
        log("  OTP msg    : %s | %s" % (latest.get("date", ""), latest.get("subject", "")))
    log("=" * 64)
    for m in msgs[:10]:
        log("- [%s] %s <%s>" % (m.get("date", ""), m.get("subject", ""), m.get("from", "")))
    if code:
        log("\n  >>> LATEST TELEGRAM CODE: %s" % code)


def cmd_watch_inbox():
    """Live OTP feed: naya mail aate hi code screen par."""
    prov, d = load_temp_backup()
    log("=" * 64)
    log("  LIVE OTP WATCH  ->  %s  (%s)" % (prov.address, d.get("provider", prov.name)))
    log("  (naya mail aate hi yahan dikhega | band karne ke liye Ctrl+C)")
    log("=" * 64)
    seen = set()
    try:
        while True:
            try:
                msgs = prov.messages()
            except MailError as e:
                log("   [!] inbox error (retry): %s" % str(e)[:110])
                msgs = []
            for m in msgs:
                key = str(m.get("id"))
                if key in seen:
                    continue
                seen.add(key)
                if prov.is_telegram(m):
                    code = prov.code_from(m, 0)
                    log("[%s] NEW  %s  <%s>" % (m.get("date", ""), (m.get("subject") or "")[:60], m.get("from", "")))
                    if code:
                        log("        >>> OTP: %s" % code)
                else:
                    log("[%s] mail %s" % (m.get("date", ""), (m.get("subject") or "")[:60]))
            time.sleep(max(1, POLL_SEC))
    except KeyboardInterrupt:
        log("\nWatch band kiya.")


def cmd_blocked():
    blocked = load_blocked()
    log("Blocked domains (auto-learned): %d" % len(blocked))
    for dom, meta in blocked.items():
        log("  - %-32s %s (%s)" % (dom, meta.get("reason"), meta.get("time")))


def cmd_clear_blocked():
    save_blocked({})
    log("Auto domain-blacklist saaf kar di (0 entries).")


def cmd_report():
    import glob
    files = sorted(glob.glob(REPORT_STEM + "_*.json"))
    if not files:
        sys.exit("Koi report file nahi mili ('%s_*.json')." % REPORT_STEM)
    with open(files[-1], encoding="utf-8") as f:
        data = json.load(f)
    print_report(data, files[-1])


# ============================ NOTIFY (OWN CHAT) ============================

def compose_notify(label, target, status, note, provider, elapsed, waits):
    """Report ka chhota text jo account ke 'Saved Messages' me bheja jata hai."""
    lines = ["TG EMAIL CHANGE — %s" % status,
             "account : %s" % label,
             "mode    : %s" % ("recovery-email" if (ARGS and ARGS.recovery) else "login-email"),
             "target  : %s" % target]
    if provider:
        lines.append("provider: %s" % provider)
    lines.append("time    : %ss" % elapsed)
    if waits:
        lines.append("floodwait: %d baar, total %ds rukna pada" % (len(waits), sum(int(w.get("seconds", 0)) for w in waits)))
    if note:
        lines.append("note    : %s" % note[:300])
    if status != "OK":
        lines.append("")
        lines.append("(server par: ~/tg-email/cron.log dekho ya --report chalao)")
    return "\n".join(lines)


async def send_self_notify(client, text):
    """Login hai isliye apne hi 'Saved Messages' me report bhej do — koi alag bot nahi chahiye."""
    if client is None:
        return False
    try:
        await client.send_message("me", text)
        log("   (report aapke Telegram 'Saved Messages' me bhej di)")
        return True
    except Exception as e:
        log("   [!] Saved Messages me report nahi gayi: %s" % str(e)[:120])
        return False


# ================================ LOCK ================================

def acquire_lock(force=False):
    """Ek waqt me ek hi run — server/cron par overlap se Telegram limit/bad effect na ho."""
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
            sys.exit("[!] Script pehle se chal rahi hai (pid %s). Ek saath do run karne se flood-wait/bad-signal "
                     "badhta hai.\n    Chhati hui lock: '%s' delete karo ya --force-lock lagao." % (old, LOCK_FILE))
        log("   (purani stale lock mili — hata di)")
    try:
        with open(LOCK_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except OSError as e:
        log("   [!] lock file nahi bani: %s" % e)


def release_lock():
    try:
        if os.path.exists(LOCK_FILE):
            with open(LOCK_FILE, encoding="utf-8") as f:
                if (f.read() or "").strip() == str(os.getpid()):
                    os.remove(LOCK_FILE)
    except OSError:
        pass


# ================================ RUN ================================

async def run(args):
    global STARTED_AT
    STARTED_AT = time.time()
    api_id, api_hash = ensure_api_creds()
    label, target_email, provider_name = "(login pending)", args.email or "(temp mail)", None
    status, note = "FAILED", ""
    client, prov = None, None
    failed_providers = []          # jinka mailbox nahi bana / fail hua
    try:
        if args.temp:
            pool = MailboxPool(args.provider, args.local)
            prov = await asyncio.to_thread(pool.next_mailbox, tuple(failed_providers))
            save_temp_backup(prov)
            target_email = prov.address
            provider_name = prov.name
        else:
            target_email = args.email

        client, label = await connect_telegram(api_id, api_hash)
        try:
            pwd = await tg_call(client, "account", lambda: functions.account.GetPasswordRequest())
        except RPCError:
            pwd = None
        print_header(label, "RECOVERY email change" if args.recovery else "LOGIN email change",
                     target_email, pwd, provider_name)

        if args.logout:
            await do_logout(client)
            status, note = "OK", "logout"
            return 0

        if args.status:
            await show_status(client)
            status, note = "OK", "status check"
            return 0

        get_code = await make_code_getter(prov, target_email, label)
        attempts = 4 if args.temp else 1

        for attempt in range(1, attempts + 1):
            try:
                if args.recovery:
                    await change_recovery_email(client, target_email, get_code)
                else:
                    await change_login_email(client, target_email, get_code)
                status = "OK"
                break
            except EmailNotAllowed:
                if not args.temp:
                    raise UserStop("Telegram ne ye email/domain reject kiya (EMAIL_NOT_ALLOWED). "
                                   "Apna real email use karo (--email).")
                block_domain(target_email)
                if attempt >= attempts:
                    raise UserStop("Har provider/domain par Telegram ne EMAIL_NOT_ALLOWED diya. "
                                   "Apna real email use karo: --email aap@mail.com")
                failed = {provider_name} if provider_name else set()
                if len(failed_providers) < len(PROVIDER_ORDER) - 1:
                    failed_providers = list(set(failed_providers) | failed)
                log("\n   [retry] naya mailbox try kar raha hoon (%d/%d)..." % (attempt + 1, attempts))
                pool = MailboxPool(args.provider, args.local)
                prov = await asyncio.to_thread(pool.next_mailbox, tuple(failed_providers))
                save_temp_backup(prov)
                target_email, provider_name = prov.address, prov.name
                get_code = await make_code_getter(prov, target_email, label)
        return 0
    except UserStop as e:
        status, note = "STOPPED", str(e)
        log("\n[!] %s" % e)
        return 1
    except MailError as e:
        status, note = "FAILED", "temp mail: %s" % e
        log("\n[!] Temp mail problem: %s" % e)
        return 1
    except (KeyboardInterrupt, asyncio.CancelledError):
        status, note = "CANCELLED", "user ne band kiya"
        log("\nBand kar diya.")
        return 130
    finally:
        write_report(label, target_email, status, note, provider_name)
        if args.notify and client is not None and not args.logout:
            elapsed = int(time.time() - STARTED_AT)
            waits = [e for e in EVENTS if e["status"] == "floodwait"]
            await send_self_notify(client, compose_notify(label, target_email, status, note,
                                                          provider_name, elapsed, waits))
        release_lock()


def main():
    global ARGS, POLL_SEC
    p = argparse.ArgumentParser(
        description="Telegram login/recovery email changer — sirf apne account ke liye (ek run = ek account).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""misale:
  %(prog)s --providers                     sab temp-mail providers ki health check
  %(prog)s --domains                       available domains (blocked mark ke saath)
  %(prog)s --status                        account + login email + 2FA status
  %(prog)s --email aap@mail.com            login email badlo
  %(prog)s --email aap@mail.com --recovery 2FA recovery email badlo
  %(prog)s --temp                          temp mailbox banao aur change karo
  %(prog)s --temp --provider guerrilla     kisi ek provider ko force karo
  %(prog)s --temp --dry-run                OTP aane tak test, verify mat karo
  %(prog)s --inbox                         pichhle temp mailbox ka latest OTP
  %(prog)s --watch-inbox                   live OTP feed (naya mail aate hi code)
  %(prog)s --temp --notify                 result Saved Messages me bhi aayega
  %(prog)s --proxy socks5://127.0.0.1:1080 --status      proxy ke through chalao
  %(prog)s --temp --logout                 run ke baad session revoke (server safai)
  %(prog)s --report / --blocked / --clear-blocked
""")
    p.add_argument("--email", metavar="EMAIL", help="naya email (recommended: apna asli email)")
    p.add_argument("--temp", action="store_true", help="temp mailbox khud banao (auto provider)")
    p.add_argument("--provider", default="auto", choices=["auto"] + PROVIDER_ORDER,
                   help="temp-mail provider (default: auto = try in order)")
    p.add_argument("--local", metavar="NAME", help="temp mailbox ka local part (mail.tm/guerrilla ke liye)")
    p.add_argument("--recovery", action="store_true", help="login email nahi, 2FA RECOVERY email badlo")
    p.add_argument("--status", action="store_true", help="sirf status dekho")
    p.add_argument("--dry-run", action="store_true", help="OTP aane par ruk jao, verify mat karo")
    p.add_argument("--poll", type=int, default=POLL_SEC, help="temp inbox poll seconds (default %d)" % POLL_SEC)
    p.add_argument("--otp-timeout", type=int, default=CODE_TIMEOUT, help="OTP wait seconds (default %d)" % CODE_TIMEOUT)
    p.add_argument("--providers", action="store_true", help="providers ki health check dikhao")
    p.add_argument("--domains", action="store_true", help="available domains dikhao")
    p.add_argument("--inbox", action="store_true", help="pichhle temp mailbox ka inbox + latest OTP")
    p.add_argument("--report", action="store_true", help="pichhli run ki report dikhao")
    p.add_argument("--blocked", action="store_true", help="auto-blocked domains dikhao")
    p.add_argument("--clear-blocked", action="store_true", help="blocklist saaf karo")
    p.add_argument("--proxy", metavar="URL",
                   help="socks5://user:pass@host:port ya http://host:port (Telegram + temp-mail dono ke liye)")
    p.add_argument("--check", action="store_true", help="session + account check (--status jaisa)")
    p.add_argument("--notify", action="store_true",
                   help="run ke ant me report apne Telegram 'Saved Messages' me bhejo (TG_NOTIFY=1 se bhi on)")
    p.add_argument("--logout", action="store_true",
                   help="run ke ant me is machine se session REVOKE karo (server safai ke liye)")
    p.add_argument("--watch-inbox", action="store_true", help="live OTP feed (saved temp mailbox)")
    p.add_argument("--force-lock", action="store_true",
                   help="lock ko ignore karke chalao (jab pichhla run crash ho gaya ho)")
    args = p.parse_args()
    ARGS = args

    if args.poll > 0:
        POLL_SEC = args.poll

    global HTTP_PROXY, TELE_PROXY
    if args.proxy:
        try:
            TELE_PROXY = parse_proxy(args.proxy)
            HTTP_PROXY = proxy_to_url(TELE_PROXY)
            log("   (proxy set: %s://%s:%s)" % (TELE_PROXY["proxy_type"], TELE_PROXY["addr"], TELE_PROXY["port"]))
        except ValueError as e:
            p.error("--proxy galat: %s" % e)
    if args.check:
        args.status = True
    if os.getenv("TG_NOTIFY", "") in ("1", "true", "yes"):
        args.notify = True

    for flag, fn in [("providers", cmd_providers), ("domains", cmd_domains), ("inbox", cmd_inbox),
                     ("watch_inbox", cmd_watch_inbox), ("report", cmd_report),
                     ("blocked", cmd_blocked), ("clear_blocked", cmd_clear_blocked)]:
        if getattr(args, flag):
            fn()
            return

    if not args.status and not args.email and not args.temp and not args.logout:
        p.error("--email EMAIL ya --temp do (ya --status / --providers / --inbox chalao)")
    if args.email and args.temp:
        p.error("--email aur --temp dono ek saath nahi")
    if args.email and ("@" not in args.email or " " in args.email):
        p.error("--email ka format theek nahi")
    acquire_lock(force=args.force_lock)
    rc = 0
    try:
        rc = asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nBand kar diya.")
        rc = 130
    finally:
        release_lock()
    sys.exit(rc)


if __name__ == "__main__":
    main()
