import asyncio
import database
import temp_mail
import tg_manager

async def test_suite():
    print("=== [TEST 1] Testing Database & Staff RBAC ===")
    database.add_owner(111111)
    database.add_owner(222222)
    database.add_admin(333333)
    assert database.is_owner(111111) == True
    assert database.is_owner(222222) == True
    assert database.is_owner(333333) == False
    assert database.is_admin_or_owner(333333) == True
    assert database.is_admin_or_owner(999999) == False
    print("  -> RBAC (3-4 Owners & Admins) PASS!")

    print("=== [TEST 2] Testing Accounts & Reports ===")
    database.add_or_update_account("+919999999999", "dummy_session", "pass123", status="active", user_info={"first_name": "TestUser"})
    acc = database.get_account("+919999999999")
    assert acc["password_2fa"] == "pass123"
    
    rep = {
        "timestamp": "2026-09-29 22:00:00",
        "total": 1,
        "success_count": 1,
        "fail_count": 0,
        "duration_sec": 12,
        "success_items": [{"phone": "+919999999999", "email": "test@uberip.com"}],
        "fail_items": []
    }
    database.add_report(rep)
    assert len(database.get_latest_reports()) >= 1
    print("  -> Database accounts & reports PASS!")

    print("=== [TEST 3] Testing Temp-Mail Creation & Blacklist ===")
    m = temp_mail.get_temp_mailbox()
    print(f"  -> Mail created: {m.address} via {m.name}")
    assert "@" in m.address
    # Test domain blocking
    domain = m.address.split("@")[-1]
    database.add_blocked_domain(domain)
    assert domain.lower() in [d.lower() for d in database.get_blocked_domains()]
    print("  -> Domain auto-blacklist PASS!")

    print("=== [TEST 4] Testing OTP Extraction ===")
    sample_text = "Telegram code 84920. Do not give this code to anyone."
    code = temp_mail.extract_code(sample_text, 5)
    assert code == "84920"
    sample_text_spaced = "Your Telegram code: 7 3 9 1 0"
    code2 = temp_mail.extract_code(sample_text_spaced, 5)
    assert code2 == "73910"
    print("  -> OTP extraction (direct & spaced) PASS!")

    print("\n✅ ALL 4 TESTS PASSED COMPLETELY WITHOUT ANY ERRORS!")

if __name__ == "__main__":
    asyncio.run(test_suite())
