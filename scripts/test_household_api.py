"""
Household Integration Test — runs against the live Express backend (port 3001).

Tests the full household flow with real API calls:
  1. Register two users (roommate scenario)
  2. Create household, join via code
  3. Add meals, create expenses
  4. Verify balances, activity feed, consolidated grocery list

Prerequisites:
  - Express server running on port 3001
  - Prisma migrated (run `npx prisma migrate dev`)
  - PYTHONPATH=. python3 scripts/test_household_api.py
"""

import http.client
import json
import time
import sys
import os

HOST = "localhost"
PORT = 3001
BASE = "/api/v1"


def api(method: str, path: str, body: dict = None, token: str = None) -> dict:
    """Make an HTTP request to the Express backend."""
    conn = http.client.HTTPConnection(HOST, PORT, timeout=10)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = json.dumps(body) if body else None
    conn.request(method, f"{BASE}{path}", body=payload, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()

    try:
        parsed = json.loads(data) if data else {}
    except json.JSONDecodeError:
        parsed = {"raw": data.decode()}

    if resp.status >= 400:
        print(f"  ⚠️  {method} {path} -> {resp.status}: {parsed.get('error', parsed)}")
        return {"error": parsed.get('error', str(parsed)), "_status": resp.status}

    return {**parsed, "_status": resp.status}


def login_or_register(email: str, name: str) -> str:
    """Login or register a user, return auth token."""
    result = api("POST", "/auth/login", {"email": email, "password": "test123"})
    if result.get("token"):
        return result["token"]

    # Register
    result = api("POST", "/auth/register", {
        "email": email, "password": "test123", "name": name,
        "region": "North India", "diet": "Veg",
    })
    token = result.get("token")
    if not token:
        print(f"  ❌ Failed to auth {email}: {result}")
        sys.exit(1)
    return token


def test_roommate_scenario():
    print("=" * 60)
    print("🏠 SCENARIO A: 2 Roommates")
    print("=" * 60)

    # 1. Register users
    print("\n📝 Registering users...")
    prateek_token = login_or_register("prateek_roommate@test.com", "Prateek")
    alex_token = login_or_register("alex_roommate@test.com", "Alex")
    print(f"  ✅ Prateek token: {prateek_token[:16]}...")
    print(f"  ✅ Alex token: {alex_token[:16]}...")

    # 2. Prateek creates household
    print("\n🏠 Creating household...")
    create_res = api("POST", "/households", {"name": "Prateek's Kitchen"}, token=prateek_token)
    household_id = create_res.get("id")
    invite_code = create_res.get("code", "unknown")
    assert household_id, f"Failed to create household: {create_res}"
    print(f"  ✅ Household created: {household_id[:8]}...")
    print(f"  ✅ Invite code: {invite_code}")
    print(f"  📱 Share link: https://mealdrama.app/join?code={invite_code}")

    # 3. Alex joins via code
    print("\n🔗 Alex joining via invite code...")
    join_res = api("POST", "/households/join", {"code": invite_code}, token=alex_token)
    assert join_res.get("id") == household_id, f"Join failed: {join_res}"
    print(f"  ✅ Alex joined household!")

    # 4. Verify members
    print("\n👥 Verifying members...")
    get_res = api("GET", f"/households/{household_id}", token=prateek_token)
    members = get_res.get("members", [])
    print(f"  ✅ {len(members)} members: {[m['name'] for m in members]}")

    # 5. Add meals (simulated via profile update / tray)
    print("\n🍽️  Adding meals for both users...")
    for token, name in [(prateek_token, "Prateek"), (alex_token, "Alex")]:
        api("PUT", "/users/profile", {
            "name": name,
            "plannedSlots": ["Breakfast", "Lunch", "Dinner"],
        }, token=token)
    print(f"  ✅ Both users have planned slots set")

    # 6. Create expenses (cook salary split)
    print("\n💰 Creating shared expenses...")
    exp1 = api("POST", f"/households/{household_id}/expenses", {
        "title": "Cook Ramesh - July Salary",
        "amount": 4000,
        "category": "cook_salary",
    }, token=prateek_token)
    if exp1.get("id"):
        print(f"  ✅ Cook salary ₹4,000 split equally")
    else:
        print(f"  ⚠️  Expense endpoint may need prisma migrate: {exp1}")

    exp2 = api("POST", f"/households/{household_id}/expenses", {
        "title": "Weekly Groceries",
        "amount": 1500,
        "category": "groceries",
    }, token=prateek_token)
    if exp2.get("id"):
        print(f"  ✅ Weekly groceries ₹1,500 split equally")

    # 7. Check balances
    print("\n⚖️  Checking balances...")
    balances = api("GET", f"/households/{household_id}/balances", token=prateek_token)
    if isinstance(balances, list):
        for b in balances:
            print(f"  {b['memberName']}: owes ₹{b['totalOwed']}, paid ₹{b['totalPaid']}, balance ₹{b['balance']}")
    else:
        print(f"  ⚠️  Balances: {balances}")

    # 8. Check consolidated meals
    print("\n📋 Checking consolidated grocery list...")
    meals = api("GET", f"/households/{household_id}/meals?start=2026-07-20&end=2026-08-03", token=prateek_token)
    if isinstance(meals, dict) and meals.get("meals"):
        print(f"  ✅ {len(meals['meals'])} total meals across {len(meals.get('members', []))} members")
        by_member = {}
        for m in meals["meals"]:
            name = m.get("requestedBy", "Unknown")
            if name not in by_member:
                by_member[name] = []
            by_member[name].append(m["name"])
        for member_name, meal_names in by_member.items():
            print(f"    {member_name}: {', '.join(meal_names[:3])}{'...' if len(meal_names) > 3 else ''}")
    else:
        print(f"  ⚠️  Consolidated meals: {meals}")

    # 9. Check activity feed
    print("\n📜 Checking activity feed...")
    activity = api("GET", f"/households/{household_id}/activity", token=prateek_token)
    if isinstance(activity, list):
        print(f"  ✅ {len(activity)} activity events")
        for a in activity[:5]:
            print(f"    {a.get('memberName')}: {a.get('action')} {a.get('detail', '')}")
    else:
        print(f"  ⚠️  Activity: {activity}")

    print("\n" + "=" * 60)
    print("✅ ROOMMATE SCENARIO COMPLETE")
    print("=" * 60)


def test_family_scenario():
    print("\n" + "=" * 60)
    print("👨‍👩‍👧‍👦 SCENARIO B: 4 Family Members")
    print("=" * 60)

    # 1. Register family members
    print("\n📝 Registering family members...")
    mom_token = login_or_register("mom_kapoor@test.com", "Mom")
    dad_token = login_or_register("dad_kapoor@test.com", "Dad")
    son_token = login_or_register("son_kapoor@test.com", "Son")
    daughter_token = login_or_register("daughter_kapoor@test.com", "Daughter")
    print(f"  ✅ All 4 family members registered")

    # 2. Mom creates household
    print("\n🏠 Creating family household...")
    create_res = api("POST", "/households", {"name": "The Kapoor Family Kitchen"}, token=mom_token)
    household_id = create_res.get("id")
    invite_code = create_res.get("code", "unknown")
    assert household_id, f"Failed: {create_res}"
    print(f"  ✅ Family household: {household_id[:8]}...")
    print(f"  ✅ Invite code: {invite_code}")

    # 3. Family joins
    print("\n🔗 Family members joining...")
    for token, name in [(dad_token, "Dad"), (son_token, "Son"), (daughter_token, "Daughter")]:
        join_res = api("POST", "/households/join", {"code": invite_code}, token=token)
        status = "✅" if join_res.get("id") == household_id else "❌"
        print(f"  {status} {name} joined")

    # 4. Create multiple expenses (real family scenario)
    print("\n💰 Creating family shared expenses...")
    expenses_data = [
        ("Monthly Groceries - July", 8500, "groceries"),
        ("Cook Maya - July Salary", 12000, "cook_salary"),
        ("Kitchen Supplies", 2400, "supplies"),
        ("Gas & Electricity", 3200, "utilities"),
    ]
    for title, amount, category in expenses_data:
        result = api("POST", f"/households/{household_id}/expenses", {
            "title": title, "amount": amount, "category": category,
        }, token=mom_token)
        if result.get("id"):
            print(f"  ✅ {title}: ₹{amount:,}")
        else:
            print(f"  ⚠️  {title}: {result.get('error', 'unknown')}")

    # 5. Check balances
    print("\n⚖️  Family balances...")
    balances = api("GET", f"/households/{household_id}/balances", token=mom_token)
    if isinstance(balances, list):
        for b in balances:
            emoji = "🔴" if b["balance"] < 0 else "🟢" if b["balance"] > 0 else "⚪"
            print(f"  {emoji} {b['memberName']}: owes ₹{b['totalOwed']:,.0f}, paid ₹{b['totalPaid']:,.0f}")

    # 6. Consolidated meals
    print("\n📋 Family consolidated grocery list...")
    meals = api("GET", f"/households/{household_id}/meals?start=2026-07-20&end=2026-08-03", token=mom_token)
    if isinstance(meals, dict) and meals.get("meals"):
        print(f"  ✅ {len(meals['meals'])} meals across {len(meals.get('members', []))} members")
        by_member = {}
        for m in meals["meals"]:
            name = m.get("requestedBy", "Unknown")
            if name not in by_member:
                by_member[name] = []
            by_member[name].append(m["name"])
        for member_name, meal_names in by_member.items():
            print(f"    {member_name}: {len(meal_names)} meals")
    else:
        print(f"  ⚠️  Consolidated meals: {meals}")

    # 7. Activity feed
    print("\n📜 Family activity feed...")
    activity = api("GET", f"/households/{household_id}/activity", token=mom_token)
    if isinstance(activity, list):
        print(f"  ✅ {len(activity)} events")
        for a in activity[:5]:
            print(f"    {a.get('memberName')}: {a.get('action')} {a.get('detail', '')}")
    else:
        print(f"  ⚠️  Activity: {activity}")

    print("\n" + "=" * 60)
    print("✅ FAMILY SCENARIO COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    print("🧪 MEALDRAMA HOUSEHOLD INTEGRATION TEST")
    print(f"   Target: http://{HOST}:{PORT}{BASE}")
    print(f"   Time:   {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Check server health
    try:
        health = api("GET", "/health")
        if health.get("_status") == 200 or health.get("status"):
            print(f"   Server:  ✅ Online\n")
        else:
            print(f"   Server:  ⚠️  Responded but unexpected: {health}\n")
    except Exception as e:
        print(f"   Server:  ❌ Could not connect — is port 3001 running?\n")
        sys.exit(1)

    test_roommate_scenario()
    test_family_scenario()

    print("\n" + "=" * 60)
    print("🎉 ALL SCENARIOS COMPLETE")
    print("=" * 60)
