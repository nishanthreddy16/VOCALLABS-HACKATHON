import httpx

print("=== SIGNUP ===")
r = httpx.post("http://127.0.0.1:8000/api/auth/signup",
    json={"username":"Ravi Kumar","email":"ravi@test.com","password":"test1234"}, timeout=15)
print(r.status_code, r.text)

print("\n=== LOGIN ===")
r2 = httpx.post("http://127.0.0.1:8000/api/auth/login",
    json={"email":"ravi@test.com","password":"test1234"}, timeout=15)
print(r2.status_code, r2.text)

if r2.status_code == 200:
    token = r2.json()["access_token"]
    print("\n=== VERIFY ===")
    r3 = httpx.get("http://127.0.0.1:8000/api/auth/verify",
        headers={"Authorization": f"Bearer {token}"}, timeout=15)
    print(r3.status_code, r3.text)

    print("\n=== HISTORY LIST ===")
    r4 = httpx.get("http://127.0.0.1:8000/api/history/list",
        headers={"Authorization": f"Bearer {token}"}, timeout=15)
    print(r4.status_code, r4.text)
