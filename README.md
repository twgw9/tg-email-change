# Telegram Multi-ID Automation Bot (24/7 Alwaysdata Production Ready) 🚀

---

## 🌟 Alwaysdata Par 24/7 Setup Kaise Karein (Bina Kisi Error & Stop Ke)

### Step 1: Alwaysdata Dashboard Par Repo/Files Upload Karein
Aap SSH ya FTP ke zariye `tg-bot` folder ko apne Alwaysdata home directory me upload karein:
```bash
cd ~/tg-bot
```

### Step 2: Virtualenv & Dependencies
```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

### Step 3: `.env` File Banayein
```bash
cp .env.example .env
nano .env
```
Isme apni details daalein:
```bash
export TG_API_ID=your_api_id
export TG_API_HASH=your_api_hash
export TG_BOT_TOKEN="your_bot_token"
export TG_OWNER_ID="your_telegram_id"
```

### Step 4: 24/7 Background Service Setup (Alwaysdata Dashboard):
Alwaysdata ke dashboard me:
1. **Environment > Services** section me jayein.
2. **Add a service** par click karein.
3. Configure karein:
   - **Name:** `Telegram Bot 24/7`
   - **Command:** `/bin/bash /home/yourusername/tg-bot/alwaysdata_run.sh`
   - **Working directory:** `/home/yourusername/tg-bot`
4. **Submit** kar dein.

Yeh script **Supervisor Daemon** ke sath aati hai, jisse agar server par koi network fluctuation ya reboot hota hai, toh yeh **automatically restart ho kar continuous 24/7 chalti rahegi**!

---

## 📱 Bot Controls Layout (Matches Your Screenshot):

- **➕ Add ID / 📋 My IDs**: Phone No + OTP + 2FA daal kar account store karein.
- **📧 Change Email / listids / ⏱️ Timer**: Single account ka email badlein, list dekhein, ya timer loop configure karein.
- **🔑 Fetch OTP / 🔍 Check Status**: Account ka number, 2FA password aur **777000 ka latest code** instant fetch karein.
- **📊 Stats**: Detailed success, fail aur time taken report.
- **🔑 Manage APIs / 👥 Admins**: Multiple Telegram APIs rotate karein aur 3-4 Owners + Admins manage karein.
- **🌐 Proxy Menu / 🌐 All IDs**: Proxies rotate karein aur All IDs list dekhein.
- **⚡ Run Timer Now / 🚀 Start All Users**: Ek button click se sabhi IDs par automatic email change trigger karein.
- **📧 Change All Users**: Sabhi users ke accounts ka batch rotation.
- **📧 Email Domains**: Global blacklist aur available providers (Mail.tm, Guerrilla, Mail.gw, 1SecMail, IMAP).
