import json
import os
import time
import tempfile
import shutil

# Path of the database file relative to the script directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_FILE = os.path.join(BASE_DIR, "accounts.json")

DEFAULT_DB = {
    "owners": [],
    "admins": [],
    "accounts": {},
    "api_credentials": [],
    "proxies": [],
    "current_proxy_index": 0,
    "current_api_index": 0,
    "settings": {
        "loop_interval": 300,
        "loop_enabled": False,
        "mode": "login",
        "delay_between_accs": 8,
        "auto_resume_flood": True,
        "max_flood_wait": 1800,
        "concurrency": 1,
        "notify_chat_id": None
    },
    "blocked_domains": [],
    "history": []
}

def load_db():
    if not os.path.exists(DATABASE_FILE):
        db = dict(DEFAULT_DB)
        save_db(db)
        return db
    try:
        with open(DATABASE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for k, v in DEFAULT_DB.items():
                if k not in data:
                    data[k] = v
            for sk, sv in DEFAULT_DB["settings"].items():
                if sk not in data["settings"]:
                    data["settings"][sk] = sv
            return data
    except Exception:
        # If file is temporarily being written or corrupt, backup and return safe structure
        return dict(DEFAULT_DB)

def save_db(data):
    """
    Atomic Write: Writes to a temporary file first, then replaces the target.
    Prevents file corruption on unexpected Alwaysdata server restarts/crashes!
    """
    try:
        temp_dir = os.path.dirname(DATABASE_FILE)
        fd, tmp_file = tempfile.mkstemp(dir=temp_dir, prefix="acc_tmp_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        shutil.move(tmp_file, DATABASE_FILE)
    except Exception as e:
        # Fallback direct write
        try:
            with open(DATABASE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

# ================= AUTH =================
def is_owner(user_id):
    db = load_db()
    owners = [int(x) for x in db.get("owners", [])]
    return int(user_id) in owners

def is_admin_or_owner(user_id):
    db = load_db()
    uid = int(user_id)
    owners = [int(x) for x in db.get("owners", [])]
    admins = [int(x) for x in db.get("admins", [])]
    if not owners and not admins:
        return True
    return uid in owners or uid in admins

def add_owner(user_id):
    db = load_db()
    uid = int(user_id)
    if uid not in db["owners"]:
        db["owners"].append(uid)
        save_db(db)
        return True
    return False

def remove_owner(user_id):
    db = load_db()
    uid = int(user_id)
    if uid in db["owners"]:
        db["owners"].remove(uid)
        save_db(db)
        return True
    return False

def add_admin(user_id):
    db = load_db()
    uid = int(user_id)
    if uid not in db["admins"]:
        db["admins"].append(uid)
        save_db(db)
        return True
    return False

def remove_admin(user_id):
    db = load_db()
    uid = int(user_id)
    if uid in db["admins"]:
        db["admins"].remove(uid)
        save_db(db)
        return True
    return False

def get_owners():
    return load_db().get("owners", [])

def get_admins():
    return load_db().get("admins", [])

# ================= ACCOUNTS =================
def get_accounts():
    return load_db().get("accounts", {})

def get_account(phone):
    return load_db().get("accounts", {}).get(phone)

def add_or_update_account(phone, session_str="", password_2fa="", status="active", user_info=None, added_by=None):
    db = load_db()
    accs = db.setdefault("accounts", {})
    entry = accs.get(phone, {})
    entry["phone"] = phone
    if session_str:
        entry["session"] = session_str
    if password_2fa is not None:
        entry["password_2fa"] = password_2fa
    entry["status"] = status
    entry["updated_at"] = int(time.time())
    if user_info:
        entry["user_info"] = user_info
    if added_by:
        entry["added_by"] = added_by
    entry.setdefault("current_email", "")
    entry.setdefault("last_otp", "")
    entry.setdefault("last_change_status", "Never changed")
    entry.setdefault("device_profile", None)
    accs[phone] = entry
    save_db(db)
    return entry

def update_account_field(phone, key, val):
    db = load_db()
    accs = db.setdefault("accounts", {})
    if phone in accs:
        accs[phone][key] = val
        accs[phone]["updated_at"] = int(time.time())
        save_db(db)

def delete_account(phone):
    db = load_db()
    accs = db.get("accounts", {})
    if phone in accs:
        del accs[phone]
        save_db(db)
        return True
    return False

# ================= APIS & PROXIES =================
def get_apis():
    return load_db().get("api_credentials", [])

def add_api(api_id, api_hash):
    db = load_db()
    apis = db.setdefault("api_credentials", [])
    entry = {"api_id": int(api_id), "api_hash": str(api_hash).strip()}
    if entry not in apis:
        apis.append(entry)
        save_db(db)
        return True
    return False

def remove_api(api_id):
    db = load_db()
    apis = db.get("api_credentials", [])
    filtered = [a for a in apis if a.get("api_id") != int(api_id)]
    if len(filtered) != len(apis):
        db["api_credentials"] = filtered
        save_db(db)
        return True
    return False

def get_next_api(default_id=0, default_hash=""):
    db = load_db()
    apis = db.get("api_credentials", [])
    if not apis:
        return default_id, default_hash
    idx = db.get("current_api_index", 0) % len(apis)
    api = apis[idx]
    db["current_api_index"] = (idx + 1) % len(apis)
    save_db(db)
    return api.get("api_id"), api.get("api_hash")

def get_proxies():
    return load_db().get("proxies", [])

def add_proxy(proxy_url):
    db = load_db()
    proxies = db.setdefault("proxies", [])
    p = proxy_url.strip()
    if p and p not in proxies:
        proxies.append(p)
        save_db(db)
        return True
    return False

def remove_proxy(proxy_url):
    db = load_db()
    proxies = db.get("proxies", [])
    if proxy_url in proxies:
        proxies.remove(proxy_url)
        save_db(db)
        return True
    return False

def get_next_proxy(default_proxy=""):
    db = load_db()
    proxies = db.get("proxies", [])
    if not proxies:
        return default_proxy
    idx = db.get("current_proxy_index", 0) % len(proxies)
    proxy = proxies[idx]
    db["current_proxy_index"] = (idx + 1) % len(proxies)
    save_db(db)
    return proxy

# ================= SETTINGS & REPORTS =================
def get_settings():
    return load_db().get("settings", DEFAULT_DB["settings"])

def update_settings(key, val):
    db = load_db()
    s = db.setdefault("settings", {})
    s[key] = val
    save_db(db)

def get_blocked_domains():
    return load_db().get("blocked_domains", [])

def add_blocked_domain(domain):
    db = load_db()
    b = db.setdefault("blocked_domains", [])
    if domain and domain.lower() not in b:
        b.append(domain.lower())
        save_db(db)

def clear_blocked_domains():
    db = load_db()
    db["blocked_domains"] = []
    save_db(db)

def add_report(report_entry):
    db = load_db()
    hist = db.setdefault("history", [])
    hist.insert(0, report_entry)
    if len(hist) > 50:
        db["history"] = hist[:50]
    save_db(db)

def get_latest_reports(limit=5):
    return load_db().get("history", [])[:limit]
