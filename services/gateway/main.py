import os
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Header, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = Path("/app/static")
if not STATIC_DIR.exists():
    STATIC_DIR = ROOT / "app" / "static"

MEDIA_DIR = Path("/app/media")
if not MEDIA_DIR.exists():
    MEDIA_DIR = ROOT / "media"

# Sub-services URLs
AUTH_URL = os.getenv("AUTH_SERVICE_URL", "http://127.0.0.1:8002")
RECONCILE_URL = os.getenv("RECONCILE_SERVICE_URL", "http://127.0.0.1:8003")
HISTORY_URL = os.getenv("HISTORY_SERVICE_URL", "http://127.0.0.1:8004")

app = FastAPI(title="Sakshi API Gateway")

# Ensure static files and media folders exist
STATIC_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# Mount media directory so uploaded images/audio are served to client
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

client = httpx.AsyncClient(timeout=60.0)

async def verify_token_and_get_user(auth_header: Optional[str]) -> Optional[dict]:
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    try:
        res = await client.get(f"{AUTH_URL}/verify", headers={"Authorization": auth_header})
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"Auth verification error: {e}")
    return None

@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/api/health")
async def health():
    # Ping services
    health_status = {"status": "ok", "services": {}}
    for name, url in [("auth", AUTH_URL), ("reconcile", RECONCILE_URL), ("history", HISTORY_URL)]:
        try:
            res = await client.get(f"{url}/api/health" if "reconcile" in name else url)
            health_status["services"][name] = "up" if res.status_code < 500 else "down"
        except Exception:
            health_status["services"][name] = "offline"
    return health_status

# --- AUTH PROXY ---

@app.post("/api/auth/signup")
async def signup(request: Request):
    body = await request.json()
    try:
        res = await client.post(f"{AUTH_URL}/signup", json=body)
        return Response(content=res.content, status_code=res.status_code, media_type=res.headers.get("content-type"))
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Auth service offline: {exc}")

@app.post("/api/auth/login")
async def login(request: Request):
    body = await request.json()
    try:
        res = await client.post(f"{AUTH_URL}/login", json=body)
        return Response(content=res.content, status_code=res.status_code, media_type=res.headers.get("content-type"))
    except httpx.RequestError as exc:
        raise HTTPException(status_code=533, detail=f"Auth service offline: {exc}")

# --- RECONCILE PROXY ---

@app.post("/api/reconcile")
async def gateway_reconcile(request: Request, authorization: Optional[str] = Header(None)):
    user = await verify_token_and_get_user(authorization)
    
    # Parse incoming multipart form data
    form = await request.form()
    files = []
    data = {}
    
    for key, value in form.multi_items():
        if hasattr(value, "filename") and hasattr(value, "read"):
            content_bytes = await value.read()
            if len(content_bytes) > 0:
                files.append((key, (value.filename, content_bytes, value.content_type)))
        else:
            data[key] = value

    forward_headers = {}
    if user:
        forward_headers["X-User-Id"] = user["user_id"]
        forward_headers["X-User-Name"] = user["username"]

    try:
        res = await client.post(f"{RECONCILE_URL}/reconcile", data=data, files=files, headers=forward_headers)
        return Response(content=res.content, status_code=res.status_code, media_type=res.headers.get("content-type"))
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Reconciliation service offline: {exc}")

@app.post("/api/translate")
async def gateway_translate(request: Request):
    body = await request.json()
    try:
        res = await client.post(f"{RECONCILE_URL}/translate", json=body)
        return Response(content=res.content, status_code=res.status_code, media_type=res.headers.get("content-type"))
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Reconciliation service offline: {exc}")

@app.get("/api/evaluate")
async def gateway_evaluate():
    try:
        res = await client.get(f"{RECONCILE_URL}/api/evaluate")
        return Response(content=res.content, status_code=res.status_code, media_type=res.headers.get("content-type"))
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Reconciliation service offline: {exc}")

# --- HISTORY PROXY ---

@app.post("/api/history/save")
async def gateway_save_history(request: Request, authorization: Optional[str] = Header(None)):
    user = await verify_token_and_get_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized: Sign in to save comparisons")
        
    body = await request.json()
    headers = {"X-User-Id": user["user_id"]}
    try:
        res = await client.post(f"{HISTORY_URL}/save", json=body, headers=headers)
        return Response(content=res.content, status_code=res.status_code, media_type=res.headers.get("content-type"))
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"History service offline: {exc}")

@app.get("/api/history/list")
async def gateway_list_history(authorization: Optional[str] = Header(None)):
    user = await verify_token_and_get_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized: Sign in to view history")
        
    headers = {"X-User-Id": user["user_id"]}
    try:
        res = await client.get(f"{HISTORY_URL}/list", headers=headers)
        return Response(content=res.content, status_code=res.status_code, media_type=res.headers.get("content-type"))
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"History service offline: {exc}")

@app.delete("/api/history/delete/{comparison_id}")
async def gateway_delete_history(comparison_id: str, authorization: Optional[str] = Header(None)):
    user = await verify_token_and_get_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized: Sign in to delete records")
        
    headers = {"X-User-Id": user["user_id"]}
    try:
        res = await client.delete(f"{HISTORY_URL}/delete/{comparison_id}", headers=headers)
        return Response(content=res.content, status_code=res.status_code, media_type=res.headers.get("content-type"))
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"History service offline: {exc}")
