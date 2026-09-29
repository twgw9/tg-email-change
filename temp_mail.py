import requests
import json
import time
import random
import string
import re
import imaplib
import email
from email.header import decode_header
import database

def extract_code(text, length=0):
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

# ================= 1. MAIL.TM =================
class MailTmProvider:
    name = "mail.tm"
    def __init__(self, proxy=None):
        self.session = requests.Session()
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
        self.base_url = "https://api.mail.tm"
        self.token = None
        self.address = None

    def create(self, blocked_domains=()):
        r = self.session.get(f"{self.base_url}/domains", timeout=12)
        doms = r.json().get("hydra:member", [])
        if not doms:
            raise Exception("No mail.tm domains available")
        chosen = None
        for d in doms:
            dom = d.get("domain", "").lower()
            if dom and dom not in [x.lower() for x in blocked_domains]:
                chosen = dom
                break
        if not chosen:
            chosen = doms[0]["domain"]
        user = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        pwd = "".join(random.choices(string.ascii_letters + string.digits, k=14))
        self.address = f"{user}@{chosen}"
        r_acc = self.session.post(f"{self.base_url}/accounts", json={"address": self.address, "password": pwd}, timeout=12)
        if r_acc.status_code not in (200, 201):
            raise Exception(f"Account creation failed: {r_acc.text}")
        r_tok = self.session.post(f"{self.base_url}/token", json={"address": self.address, "password": pwd}, timeout=12)
        self.token = r_tok.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        return self.address

    def fetch_otp(self, length=0):
        if not self.token:
            return None, None
        try:
            r = self.session.get(f"{self.base_url}/messages", timeout=10)
            msgs = r.json().get("hydra:member", [])
            for m in msgs:
                sender = json.dumps(m.get("from") or {}).lower()
                subject = (m.get("subject") or "").lower()
                intro = m.get("intro") or ""
                if "telegram" in sender or "telegram" in subject or "telegram" in intro.lower():
                    mid = m.get("id")
                    r_detail = self.session.get(f"{self.base_url}/messages/{mid}", timeout=10)
                    detail = r_detail.json()
                    body = detail.get("text") or detail.get("html") or intro
                    code = extract_code(body, length) or extract_code(intro, length)
                    if code:
                        return code, body
        except Exception:
            pass
        return None, None

# ================= 2. GUERRILLAMAIL =================
class GuerrillaProvider:
    name = "guerrilla"
    def __init__(self, proxy=None):
        self.session = requests.Session()
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
        self.base_url = "https://api.guerrillamail.com/ajax.php"
        self.sid_token = None
        self.address = None

    def create(self, blocked_domains=()):
        r = self.session.get(f"{self.base_url}?f=get_email_address", timeout=12)
        data = r.json()
        self.sid_token = data.get("sid_token")
        self.address = data.get("email_addr")
        return self.address

    def fetch_otp(self, length=0):
        if not self.sid_token:
            return None, None
        try:
            r = self.session.get(f"{self.base_url}?f=get_email_list&offset=0&sid_token={self.sid_token}", timeout=10)
            msgs = r.json().get("list", [])
            for m in msgs:
                mail_from = (m.get("mail_from") or "").lower()
                subject = (m.get("mail_subject") or "").lower()
                excerpt = m.get("mail_excerpt") or ""
                if "telegram" in mail_from or "telegram" in subject or "telegram" in excerpt.lower():
                    mid = m.get("mail_id")
                    r_f = self.session.get(f"{self.base_url}?f=fetch_email&email_id={mid}&sid_token={self.sid_token}", timeout=10)
                    body = r_f.json().get("mail_body", "") or excerpt
                    code = extract_code(body, length) or extract_code(excerpt, length)
                    if code:
                        return code, body
        except Exception:
            pass
        return None, None

# ================= 3. MAIL.GW =================
class MailGwProvider:
    name = "mail.gw"
    def __init__(self, proxy=None):
        self.session = requests.Session()
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
        self.base_url = "https://api.mail.gw"
        self.token = None
        self.address = None

    def create(self, blocked_domains=()):
        r = self.session.get(f"{self.base_url}/domains", timeout=12)
        doms = r.json().get("hydra:member", [])
        if not doms:
            raise Exception("No mail.gw domains available")
        chosen = doms[0]["domain"]
        for d in doms:
            dom = d.get("domain", "").lower()
            if dom and dom not in [x.lower() for x in blocked_domains]:
                chosen = dom
                break
        user = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        pwd = "".join(random.choices(string.ascii_letters + string.digits, k=14))
        self.address = f"{user}@{chosen}"
        r_acc = self.session.post(f"{self.base_url}/accounts", json={"address": self.address, "password": pwd}, timeout=12)
        if r_acc.status_code not in (200, 201):
            raise Exception(f"Account creation failed: {r_acc.text}")
        r_tok = self.session.post(f"{self.base_url}/token", json={"address": self.address, "password": pwd}, timeout=12)
        self.token = r_tok.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        return self.address

    def fetch_otp(self, length=0):
        if not self.token:
            return None, None
        try:
            r = self.session.get(f"{self.base_url}/messages", timeout=10)
            msgs = r.json().get("hydra:member", [])
            for m in msgs:
                sender = json.dumps(m.get("from") or {}).lower()
                subject = (m.get("subject") or "").lower()
                intro = m.get("intro") or ""
                if "telegram" in sender or "telegram" in subject or "telegram" in intro.lower():
                    mid = m.get("id")
                    r_detail = self.session.get(f"{self.base_url}/messages/{mid}", timeout=10)
                    detail = r_detail.json()
                    body = detail.get("text") or detail.get("html") or intro
                    code = extract_code(body, length) or extract_code(intro, length)
                    if code:
                        return code, body
        except Exception:
            pass
        return None, None

# ================= 4. IMAP CUSTOM EMAIL HANDLER =================
class ImapCustomEmailProvider:
    """
    Kopeechka / Firstmail / Webmail / Custom Domain IMAP Support:
    Reads incoming Telegram OTP directly from custom IMAP server.
    """
    name = "imap_custom"
    def __init__(self, imap_host, imap_user, imap_pass, imap_port=993):
        self.imap_host = imap_host
        self.imap_user = imap_user
        self.imap_pass = imap_pass
        self.imap_port = imap_port
        self.address = imap_user

    def create(self, blocked_domains=()):
        return self.address

    def fetch_otp(self, length=0):
        try:
            mail = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            mail.login(self.imap_user, self.imap_pass)
            mail.select("inbox")
            status, messages = mail.search(None, '(FROM "telegram" OR SUBJECT "Telegram")')
            if status != "OK" or not messages[0]:
                mail.logout()
                return None, None
            msg_ids = messages[0].split()
            latest_id = msg_ids[-1]
            res, msg_data = mail.fetch(latest_id, "(RFC822)")
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body += part.get_payload(decode=True).decode(errors="ignore")
            else:
                body = msg.get_payload(decode=True).decode(errors="ignore")
            mail.logout()
            code = extract_code(body, length)
            return code, body
        except Exception:
            return None, None

PROVIDERS_ORDER = [MailTmProvider, GuerrillaProvider, MailGwProvider]

def get_temp_mailbox(proxy=None):
    blocked = database.get_blocked_domains()
    errors = []
    for prov_cls in PROVIDERS_ORDER:
        try:
            p = prov_cls(proxy=proxy)
            p.create(blocked_domains=blocked)
            return p
        except Exception as e:
            errors.append(f"{prov_cls.name}: {e}")

    raise Exception(f"All temp-mail providers failed! ({'; '.join(errors)})")
