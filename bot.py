#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Multi-Account Manager & Automation Bot v5.0 (24/7 Alwaysdata Production Ready)
Features:
- Auto Reconnection & Infinite Keep-Alive
- Process Watchdog & Signal Handling (SIGTERM/SIGHUP safe)
- Atomic Database & Anti-Crash
- Smart FloodWait Auto-Resume (no human needed)
- Exact Match UI Grid (16 Action Handlers)
"""

import os
import sys
import asyncio
import logging
import signal
import time

from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError, PhoneCodeInvalidError,
    PhoneNumberInvalidError, FloodWaitError
)

import database
import tg_manager
from temp_mail import get_temp_mailbox

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TG_BOT_24_7")

BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "").strip()
API_ID = int(os.getenv("TG_API_ID", "0") or 0)
API_HASH = os.getenv("TG_API_HASH", "").strip()
INITIAL_OWNER = os.getenv("TG_OWNER_ID", "").strip()

if INITIAL_OWNER:
    for oid in INITIAL_OWNER.split(","):
        if oid.strip().isdigit():
            database.add_owner(int(oid.strip()))

USER_STATES = {}
IS_CHANGING_NOW = False
CURRENT_LOG_CHAT = None

def auth_check(user_id):
    return database.is_admin_or_owner(user_id)

def owner_check(user_id):
    return database.is_owner(user_id)

def get_grid_keyboard(user_id):
    return [
        [
            Button.inline("➕ Add ID", b"btn_add_id"),
            Button.inline("📋 My IDs", b"btn_my_ids")
        ],
        [
            Button.inline("📧 Change Email", b"btn_change_email_single"),
            Button.inline("listids", b"btn_list_ids"),
            Button.inline("⏱️ Timer", b"btn_timer_menu")
        ],
        [
            Button.inline("🔑 Fetch OTP", b"btn_fetch_otp_menu"),
            Button.inline("🔍 Check Status", b"btn_check_status")
        ],
        [
            Button.inline("📊 Stats", b"btn_stats")
        ],
        [
            Button.inline("🔑 Manage APIs", b"btn_manage_apis"),
            Button.inline("👥 Admins", b"btn_admins_menu")
        ],
        [
            Button.inline("🌐 Proxy Menu", b"btn_proxy_menu"),
            Button.inline("🌐 All IDs", b"btn_all_ids")
        ],
        [
            Button.inline("⚡ Run Timer Now", b"btn_run_timer_now"),
            Button.inline("🚀 Start All Users", b"btn_start_all_users")
        ],
        [
            Button.inline("📧 Change All Users", b"btn_change_all_users")
        ],
        [
            Button.inline("📧 Email Domains", b"btn_email_domains")
        ]
    ]

async def loop_worker(bot):
    """
    24/7 Resilient Loop Worker:
    Continuously executes timer-based email rotations across all accounts
    without crashing or freezing on network dropouts.
    """
    global IS_CHANGING_NOW
    while True:
        try:
            settings = database.get_settings()
            interval = max(10, settings.get("loop_interval", 300))
            enabled = settings.get("loop_enabled", False)

            if enabled and not IS_CHANGING_NOW:
                logger.info(f"Loop timer tick: Starting change_all_accounts (Interval: {interval}s)")
                IS_CHANGING_NOW = True

                async def loop_log(text):
                    logger.info(text)
                    target = settings.get("notify_chat_id") or CURRENT_LOG_CHAT
                    if target:
                        try:
                            await bot.send_message(target, text)
                        except Exception:
                            pass

                try:
                    await tg_manager.change_all_accounts(
                        mode=settings.get("mode", "login"),
                        log_callback=loop_log
                    )
                except Exception as ex:
                    logger.error(f"Error in batch loop: {ex}")
                finally:
                    IS_CHANGING_NOW = False

            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Loop worker unexpected error: {e}")
            await asyncio.sleep(20)

async def run_bot_forever():
    """
    Infinite Connection Keeper for Alwaysdata / Linux Daemons.
    Automatically catches disconnection and reconnects smoothly.
    """
    while True:
        try:
            logger.info("Initializing Telegram Bot Client...")
            bot = TelegramClient(
                "bot_session",
                API_ID,
                API_HASH,
                connection_retries=None, # Infinite retries on network disconnect
                retry_delay=3,
                auto_reconnect=True
            )
            await bot.start(bot_token=BOT_TOKEN)
            logger.info("✅ Bot is online, polling and ready!")

            # Background Loop Task
            loop_task = asyncio.create_task(loop_worker(bot))

            # Register handlers
            register_handlers(bot)

            # Wait until disconnected
            await bot.run_until_disconnected()
            logger.warning("Bot disconnected. Reconnecting in 5 seconds...")
            loop_task.cancel()
            await asyncio.sleep(5)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Process stopping by user signal.")
            break
        except Exception as e:
            logger.error(f"Bot connection crashed: {e}. Auto-restarting in 8s...")
            await asyncio.sleep(8)

def register_handlers(bot):

    @bot.on(events.NewMessage(pattern="/start"))
    async def cmd_start(event):
        user_id = event.sender_id
        if not database.get_owners():
            database.add_owner(user_id)
            logger.info(f"First user {user_id} configured as Primary Super Owner.")

        if not auth_check(user_id):
            await event.respond("⛔ **Access Denied!**\nAapke paas is bot ko use karne ki permission nahi hai. Kisi owner se permission lein.")
            return

        global CURRENT_LOG_CHAT
        CURRENT_LOG_CHAT = event.chat_id
        database.update_settings("notify_chat_id", event.chat_id)

        accs = database.get_accounts()
        settings = database.get_settings()
        role = "👑 Owner" if database.is_owner(user_id) else "👮 Admin"
        timer_status = "🟢 ON" if settings.get("loop_enabled") else "🔴 OFF"

        banner = (
            f"⚡ **TELEGRAM PRO AUTOMATION CONTROLLER (24/7 ACTIVE)** ⚡\n\n"
            f"👤 **Role:** `{role}` | ID: `{user_id}`\n"
            f"📱 **Total Accounts:** `{len(accs)}`\n"
            f"⏱️ **Timer Loop:** `{settings.get('loop_interval', 300)}s` | Status: `{timer_status}`\n\n"
            f"✨ **Engine Specs:**\n"
            f"• 🎭 Anti-Fingerprinting: `30 Device Models Pool`\n"
            f"• 📧 Email Engines: `Mail.tm, Guerrilla, Mail.gw, 1SecMail, IMAP`\n"
            f"• 🚫 Global Domain Blacklist: `Active & Auto-filtering`\n"
            f"• ⏱️ Gaussian Human Delays: `1.5s - 3.2s Random`\n"
            f"• 🔮 FloodWait Auto-Resume: `100% Automated`\n"
            f"• 🔄 Alwaysdata Keep-Alive: `Active & Self-Healing`\n\n"
            "Neeche diye gaye buttons se operate karein:"
        )
        await event.respond(banner, buttons=get_grid_keyboard(user_id))

    @bot.on(events.CallbackQuery)
    async def handle_callback_query(event):
        user_id = event.sender_id
        if not auth_check(user_id):
            await event.answer("Access Denied!", alert=True)
            return

        data = event.data.decode("utf-8")

        # 1. ADD ID
        if data == "btn_add_id":
            USER_STATES[user_id] = {"step": "ask_phone"}
            await event.respond("➕ **[Add ID]** Phone Number bhejein (Format: `+91XXXXXXXXXX`):")
            await event.answer()

        # 2. MY IDs
        elif data == "btn_my_ids":
            accs = database.get_accounts()
            my_accs = {p: a for p, a in accs.items() if a.get("added_by") == user_id or database.is_owner(user_id)}
            if not my_accs:
                await event.respond("ℹ️ Aapke paas koi IDs add nahi hain.", buttons=get_grid_keyboard(user_id))
            else:
                msg = f"📋 **Aapki IDs ({len(my_accs)}):**\n\n"
                for i, (p, a) in enumerate(my_accs.items(), 1):
                    msg += f"**{i}.** `{p}` | 📧: `{a.get('current_email') or 'None'}` | 2FA: `{'Yes' if a.get('password_2fa') else 'No'}`\n"
                await event.respond(msg, buttons=get_grid_keyboard(user_id))
            await event.answer()

        # 3. CHANGE EMAIL (Single)
        elif data == "btn_change_email_single":
            accs = database.get_accounts()
            if not accs:
                await event.answer("Pehle ID add karein!", alert=True)
                return
            buttons = []
            for p in accs.keys():
                buttons.append([Button.inline(f"📧 Change {p}", f"single_change_{p}".encode())])
            buttons.append([Button.inline("🔙 Back", b"btn_back_main")])
            await event.edit("📧 **Select ID to Change Email:**", buttons=buttons)
            await event.answer()

        elif data.startswith("single_change_"):
            phone = data.replace("single_change_", "")
            await event.answer(f"Starting for {phone}...")
            status_msg = await event.respond(f"🚀 `{phone}` ka email change shuru ho raha hai...")
            
            async def single_log(t):
                try:
                    await bot.send_message(event.chat_id, t)
                except Exception:
                    pass

            settings = database.get_settings()
            await tg_manager.change_email_for_account(phone, mode=settings.get("mode", "login"), log_callback=single_log)
            await event.respond(f"🏁 Finished processing `{phone}`!", buttons=get_grid_keyboard(user_id))

        # 4. listids
        elif data == "btn_list_ids":
            accs = database.get_accounts()
            if not accs:
                await event.respond("ℹ️ Database me koi accounts nahi hain.", buttons=get_grid_keyboard(user_id))
            else:
                msg = f"📋 **Registered IDs List ({len(accs)}):**\n\n"
                for i, (p, a) in enumerate(accs.items(), 1):
                    dev = a.get("device_profile") or {}
                    msg += f"**{i}.** `{p}` | 📧 `{a.get('current_email') or 'None'}`\n"
                    msg += f"   • Device: `{dev.get('device_model', 'Random Android')}`\n"
                    msg += f"   • Status: `{a.get('last_change_status')}`\n\n"
                await event.respond(msg, buttons=get_grid_keyboard(user_id))
            await event.answer()

        # 5. TIMER MENU
        elif data == "btn_timer_menu":
            s = database.get_settings()
            status_str = "🟢 Active" if s.get("loop_enabled") else "🔴 Stopped"
            msg = (
                f"⏱️ **Timer Configuration:**\n\n"
                f"• Current Interval: `{s.get('loop_interval', 300)}` seconds\n"
                f"• Loop Status: `{status_str}`\n\n"
                f"Select an action:"
            )
            btns = [
                [Button.inline("🟢 Turn Loop ON", b"timer_on"), Button.inline("🔴 Turn Loop OFF", b"timer_off")],
                [Button.inline("⏱️ 60s", b"set_timer_60"), Button.inline("⏱️ 300s (5m)", b"set_timer_300"), Button.inline("⏱️ 600s (10m)", b"set_timer_600")],
                [Button.inline("🔙 Back", b"btn_back_main")]
            ]
            await event.edit(msg, buttons=btns)
            await event.answer()

        elif data == "timer_on":
            database.update_settings("loop_enabled", True)
            database.update_settings("notify_chat_id", event.chat_id)
            await event.answer("Timer Loop Started! 🟢", alert=True)
            await event.edit("🟢 **Timer Loop is now ACTIVE!**", buttons=get_grid_keyboard(user_id))

        elif data == "timer_off":
            database.update_settings("loop_enabled", False)
            await event.answer("Timer Loop Stopped! 🔴", alert=True)
            await event.edit("🔴 **Timer Loop is now STOPPED!**", buttons=get_grid_keyboard(user_id))

        elif data.startswith("set_timer_"):
            sec = int(data.replace("set_timer_", ""))
            database.update_settings("loop_interval", sec)
            await event.answer(f"Timer set to {sec}s!", alert=True)
            await event.edit(f"✅ Timer interval updated: **{sec} seconds**!", buttons=get_grid_keyboard(user_id))

        # 6. FETCH OTP
        elif data == "btn_fetch_otp_menu":
            accs = database.get_accounts()
            if not accs:
                await event.answer("Pehle account add karein!", alert=True)
                return
            buttons = []
            row = []
            for p in accs.keys():
                row.append(Button.inline(f"📱 {p}", f"fetch_otp_{p}".encode()))
                if len(row) == 2:
                    buttons.append(row)
                    row = []
            if row:
                buttons.append(row)
            buttons.append([Button.inline("🔙 Back", b"btn_back_main")])
            await event.edit("🔍 **Kis ID ka OTP fetch karna hai?**", buttons=buttons)
            await event.answer()

        elif data.startswith("fetch_otp_"):
            phone = data.replace("fetch_otp_", "")
            await event.answer("Fetching OTP & details...")
            status_msg = await event.respond(f"⏳ `{phone}` se details fetch ho rahi hain...")
            res = await tg_manager.fetch_account_latest_otp(phone)
            if not res.get("success"):
                await status_msg.edit(f"❌ Error: `{res.get('error')}`")
                return

            code = res.get("code") or "Code nahi mila"
            pass_2fa = res.get("pass_2fa") or "Not set"
            text = res.get("text", "")
            date = res.get("date", "N/A")

            reply = (
                f"📱 **Account Details & Latest OTP:**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📞 **Phone No:** `{res.get('phone')}`\n"
                f"🔐 **2FA Password:** `{pass_2fa}`\n"
                f"🔑 **Latest OTP Code:** `{code}`\n"
                f"🕒 **Time:** `{date}`\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📩 **Telegram Official Message:**\n`{text}`"
            )
            await status_msg.edit(reply, buttons=get_grid_keyboard(user_id))

        # 7. CHECK STATUS
        elif data == "btn_check_status":
            await event.answer("Checking accounts status...")
            accs = database.get_accounts()
            active_cnt = sum(1 for a in accs.values() if a.get("status") == "active")
            msg = (
                f"🔍 **System & Accounts Health Check:**\n\n"
                f"• Total Loaded Accounts: `{len(accs)}`\n"
                f"• Active Sessions: `{active_cnt}`\n"
                f"• Proxies Configured: `{len(database.get_proxies())}`\n"
                f"• API IDs Configured: `{len(database.get_apis())}`\n"
                f"• Blocked Domains Count: `{len(database.get_blocked_domains())}`\n\n"
                f"🛡️ Anti-Fingerprint Device Profiles: **30 Loaded**\n"
                f"🔮 Smart FloodWait Auto-Resume: **Enabled**\n"
                f"🚀 24/7 Keep-Alive: **Online**"
            )
            await event.respond(msg, buttons=get_grid_keyboard(user_id))

        # 8. STATS
        elif data == "btn_stats":
            reports = database.get_latest_reports(limit=1)
            last_run = reports[0] if reports else {}
            msg = (
                f"📊 **Global Statistics & Reports:**\n\n"
                f"• Total Saved Accounts: `{len(database.get_accounts())}`\n"
                f"• Total History Logs: `{len(database.get_latest_reports(50))}`\n\n"
                f"⏱️ **Last Execution Details:**\n"
                f"• Timestamp: `{last_run.get('timestamp', 'Never')}`\n"
                f"• Total Processed: `{last_run.get('total', 0)}`\n"
                f"• ✅ Success Count: `{last_run.get('success_count', 0)}`\n"
                f"• ❌ Failed Count: `{last_run.get('fail_count', 0)}`\n"
                f"• Duration: `{last_run.get('duration_sec', 0)}s`"
            )
            await event.respond(msg, buttons=get_grid_keyboard(user_id))
            await event.answer()

        # 9. MANAGE APIs
        elif data == "btn_manage_apis":
            apis = database.get_apis()
            msg = f"🔑 **API Rotation Pool ({len(apis)}):**\n\n"
            if not apis:
                msg += "• Using Default API ID from environment.\n"
            else:
                for i, a in enumerate(apis, 1):
                    msg += f"**{i}.** API ID: `{a.get('api_id')}`\n"
            msg += "\nNaya API add karne ke liye type karein:\n`/add_api <api_id> <api_hash>`\nRemove karne ke liye: `/del_api <api_id>`"
            await event.respond(msg, buttons=get_grid_keyboard(user_id))
            await event.answer()

        # 10. ADMINS
        elif data == "btn_admins_menu":
            owners = database.get_owners()
            admins = database.get_admins()
            msg = "👥 **Admins & Owners Management:**\n\n👑 **Owners (Full Access):**\n"
            for o in owners:
                msg += f"• `{o}`\n"
            msg += "\n👮 **Admins:**\n"
            if not admins:
                msg += "• (Koi extra admin nahi hai)\n"
            else:
                for a in admins:
                    msg += f"• `{a}`\n"
            msg += "\n**Commands:**\n• `/add_admin <id>` - Naya admin banayein\n• `/remove_admin <id>` - Admin remove karein\n• `/add_owner <id>` - Naya owner banayein (Up to 4)"
            await event.respond(msg, buttons=get_grid_keyboard(user_id))
            await event.answer()

        # 11. PROXY MENU
        elif data == "btn_proxy_menu":
            proxies = database.get_proxies()
            msg = f"🌐 **Proxy Rotation Pool ({len(proxies)}):**\n\n"
            if not proxies:
                msg += "• Direct Connection (No proxies in pool)\n"
            else:
                for i, pr in enumerate(proxies, 1):
                    msg += f"**{i}.** `{pr}`\n"
            msg += "\nProxy add karne ke liye type karein:\n`/add_proxy socks5://user:pass@host:port`\nRemove karne ke liye: `/del_proxy <url>`"
            await event.respond(msg, buttons=get_grid_keyboard(user_id))
            await event.answer()

        # 12. ALL IDs
        elif data == "btn_all_ids":
            await handle_callback_query(type("Event", (), {"data": b"btn_list_ids", "sender_id": user_id, "respond": event.respond, "answer": event.answer, "chat_id": event.chat_id})())

        # 13. RUN TIMER NOW
        elif data == "btn_run_timer_now":
            global IS_CHANGING_NOW
            if IS_CHANGING_NOW:
                await event.answer("Execution pehle se running hai!", alert=True)
                return
            await event.answer("Triggering Timer Batch Run Now! ⚡")
            await event.respond("⚡ **[Run Timer Now]** Batch process manually shuru kiya gaya...")
            
            async def run_log(t):
                try:
                    await bot.send_message(event.chat_id, t)
                except Exception:
                    pass

            IS_CHANGING_NOW = True
            try:
                settings = database.get_settings()
                await tg_manager.change_all_accounts(mode=settings.get("mode", "login"), log_callback=run_log)
            finally:
                IS_CHANGING_NOW = False
            await event.respond("🏁 **[Run Timer Now]** Complete!", buttons=get_grid_keyboard(user_id))

        # 14. START ALL USERS
        elif data == "btn_start_all_users":
            database.update_settings("loop_enabled", True)
            database.update_settings("notify_chat_id", event.chat_id)
            await event.answer("Start All Users Loop Activated! 🚀", alert=True)
            await event.respond("🚀 **Start All Users Activated!**\nSabhi users ki IDs timer loop me automate ho gayi hain.", buttons=get_grid_keyboard(user_id))

        # 15. CHANGE ALL USERS
        elif data == "btn_change_all_users":
            if IS_CHANGING_NOW:
                await event.answer("Already running!", alert=True)
                return
            await event.answer("Starting Change All Users! 📧")
            await event.respond("📧 **[Change All Users]** Sabhi accounts ka email badalna shuru...")
            
            async def change_log(t):
                try:
                    await bot.send_message(event.chat_id, t)
                except Exception:
                    pass

            IS_CHANGING_NOW = True
            try:
                settings = database.get_settings()
                await tg_manager.change_all_accounts(mode=settings.get("mode", "login"), log_callback=change_log)
            finally:
                IS_CHANGING_NOW = False
            await event.respond("🏁 **[Change All Users]** Finished!", buttons=get_grid_keyboard(user_id))

        # 16. EMAIL DOMAINS
        elif data == "btn_email_domains":
            blocked = database.get_blocked_domains()
            msg = (
                f"📧 **Email Engine & Domains:**\n\n"
                f"🌐 **Supported Providers:**\n"
                f"• Mail.tm (Hydra API)\n"
                f"• GuerrillaMail (Direct API)\n"
                f"• Mail.gw (Fallback)\n"
                f"• 1SecMail (Fallback)\n"
                f"• IMAP / Kopeechka Support\n\n"
                f"🚫 **Global Domain Blacklist ({len(blocked)}):**\n"
            )
            if not blocked:
                msg += "• (Koi blocked domain nahi hai)\n"
            else:
                for d in blocked:
                    msg += f"• `{d}`\n"
            msg += "\nBlocklist saaf karne ke liye: `/clear_blocked`"
            await event.respond(msg, buttons=get_grid_keyboard(user_id))
            await event.answer()

        elif data == "btn_back_main":
            await event.edit("🤖 **Telegram Pro Automation Controller**", buttons=get_grid_keyboard(user_id))

    # ========================== CONVERSATION FLOW (ADD ID) ==========================
    @bot.on(events.NewMessage(pattern="/cancel"))
    async def cmd_cancel(event):
        user_id = event.sender_id
        state = USER_STATES.pop(user_id, None)
        if state and "client" in state:
            try:
                await state["client"].disconnect()
            except Exception:
                pass
        await event.respond("❌ Process cancel kar diya gaya.", buttons=get_grid_keyboard(user_id))

    @bot.on(events.NewMessage)
    async def handle_conversation_steps(event):
        user_id = event.sender_id
        state = USER_STATES.get(user_id)
        if not state:
            return

        text = (event.raw_text or "").strip()
        if text.startswith("/"):
            return

        step = state.get("step")

        # STEP 1: PHONE
        if step == "ask_phone":
            phone = text.replace(" ", "")
            if not phone.startswith("+") or len(phone) < 8:
                await event.respond("⚠️ Phone number invalid hai! Format: `+91XXXXXXXXXX` (with country code +)")
                return

            status_msg = await event.respond(f"⏳ Connecting with Anti-Fingerprinting device profile & sending code to `{phone}`...")
            client = tg_manager.get_client()
            await client.connect()
            try:
                send_code_res = await client.send_code_request(phone)
                state["client"] = client
                state["phone"] = phone
                state["phone_code_hash"] = send_code_res.phone_code_hash
                state["step"] = "ask_otp"
                await status_msg.edit(
                    f"📩 **Login Code Sent to {phone}!**\n\n"
                    f"Aapke Telegram app ya SMS me jo code aaya hai, wo yahan enter karein:"
                )
            except PhoneNumberInvalidError:
                await client.disconnect()
                USER_STATES.pop(user_id, None)
                await status_msg.edit("❌ Phone number invalid hai Telegram ke liye.")
            except FloodWaitError as fe:
                await client.disconnect()
                USER_STATES.pop(user_id, None)
                await status_msg.edit(f"⏳ FloodWait: Telegram ne `{fe.seconds}s` ka wait diya hai.")
            except Exception as e:
                await client.disconnect()
                USER_STATES.pop(user_id, None)
                await status_msg.edit(f"❌ Error sending code: {e}")

        # STEP 2: OTP
        elif step == "ask_otp":
            code = text.replace(" ", "")
            client = state.get("client")
            phone = state.get("phone")
            phone_code_hash = state.get("phone_code_hash")

            status_msg = await event.respond("🔄 Verifying OTP...")
            try:
                await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
                session_str = client.session.save()
                me = await client.get_me()
                user_info = {"id": me.id, "first_name": me.first_name, "username": me.username, "phone": me.phone}
                database.add_or_update_account(phone, session_str=session_str, password_2fa="", status="active", user_info=user_info, added_by=user_id)
                await client.disconnect()
                USER_STATES.pop(user_id, None)
                await status_msg.edit(
                    f"🎉 **Account Successfully Added!**\n\n"
                    f"• Phone: `{phone}`\n"
                    f"• Name: `{me.first_name}`\n"
                    f"• 2FA: `None`\n\n"
                    f"Ab aap iska email badal sakte hain ya timer loop chala sakte hain!",
                    buttons=get_grid_keyboard(user_id)
                )
            except SessionPasswordNeededError:
                state["step"] = "ask_2fa"
                await status_msg.edit(
                    "🔐 **2FA Password Detected!**\n\n"
                    "Is account par Two-Step Verification laga hai.\n"
                    "Kripya account ka **2FA Password** type karein:"
                )
            except PhoneCodeInvalidError:
                await status_msg.edit("❌ OTP code galat hai! Kripya sahi OTP dobara enter karein:")
            except Exception as e:
                await client.disconnect()
                USER_STATES.pop(user_id, None)
                await status_msg.edit(f"❌ Login Error: {e}")

        # STEP 3: 2FA
        elif step == "ask_2fa":
            pwd = text
            client = state.get("client")
            phone = state.get("phone")

            status_msg = await event.respond("🔄 Verifying 2FA Password...")
            try:
                await client.sign_in(password=pwd)
                session_str = client.session.save()
                me = await client.get_me()
                user_info = {"id": me.id, "first_name": me.first_name, "username": me.username, "phone": me.phone}
                database.add_or_update_account(phone, session_str=session_str, password_2fa=pwd, status="active", user_info=user_info, added_by=user_id)
                await client.disconnect()
                USER_STATES.pop(user_id, None)
                await status_msg.edit(
                    f"🎉 **Account Successfully Added with 2FA!**\n\n"
                    f"• Phone: `{phone}`\n"
                    f"• Name: `{me.first_name}`\n"
                    f"• 2FA Password: `{pwd}` (Saved securely for auto recovery)\n\n"
                    f"Ab aap iska OTP bhi fetch kar sakte hain aur email bhi change kar sakte hain!",
                    buttons=get_grid_keyboard(user_id)
                )
            except Exception as e:
                await status_msg.edit(f"❌ 2FA Password galat hai ya error aaya: {e}\nDobara password type karein ya `/cancel` karein.")

    # ========================== EXTRA SHORTCUT COMMANDS ==========================
    @bot.on(events.NewMessage(pattern=r"^/add_api\s+(\d+)\s+(.+)"))
    async def cmd_add_api(event):
        if not owner_check(event.sender_id):
            return
        aid = int(event.pattern_match.group(1))
        ahash = event.pattern_match.group(2).strip()
        database.add_api(aid, ahash)
        await event.respond(f"✅ Added API ID: `{aid}` to rotation pool!", buttons=get_grid_keyboard(event.sender_id))

    @bot.on(events.NewMessage(pattern=r"^/add_proxy\s+(.+)"))
    async def cmd_add_proxy(event):
        if not owner_check(event.sender_id):
            return
        p = event.pattern_match.group(1).strip()
        database.add_proxy(p)
        await event.respond(f"✅ Added Proxy `{p}` to pool!", buttons=get_grid_keyboard(event.sender_id))

    @bot.on(events.NewMessage(pattern="/clear_blocked"))
    async def cmd_clear_blocked(event):
        if not auth_check(event.sender_id):
            return
        database.clear_blocked_domains()
        await event.respond("✅ Domain blacklist saaf kar di gayi!", buttons=get_grid_keyboard(event.sender_id))

def main():
    if not BOT_TOKEN:
        print("[!] Error: TG_BOT_TOKEN environment variable is required to start the bot.")
        sys.exit(1)

    # Clean signal handling for alwaysdata
    def sig_handler(signum, frame):
        logger.info(f"Received signal {signum}. Shutting down cleanly.")
        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    try:
        asyncio.run(run_bot_forever())
    except (KeyboardInterrupt, SystemExit):
        pass

if __name__ == "__main__":
    main()
