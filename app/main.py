"""Sakshi: safe, auditable multimodal delivery-evidence reconciliation."""
import base64
import datetime
import json
import mimetypes
import os
import time
import uuid
from pathlib import Path
from typing import Optional
from urllib import error, request

import bcrypt
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Header, Depends, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from groq import Groq
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import Column, String, Text, DateTime, JSON, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.safety import pending_review, safe_result

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
MEDIA_DIR = ROOT / "media"
MEDIA_DIR.mkdir(exist_ok=True)
EVAL_CASES = ROOT / "eval" / "cases.json"
load_dotenv(ROOT / ".env", override=True)
MAX_BYTES = 12 * 1024 * 1024
GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_VISION_MODEL = "qwen/qwen3.6-27b"
GROQ_TEXT_MODEL = "qwen/qwen3.6-27b"

# ── JWT & Auth Config ───────────────────────────────────────
JWT_SECRET = os.getenv("JWT_SECRET", "sakshi-jwt-secret-key-change-in-production-2025")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 1440

# ── Database (SQLite for local dev, PostgreSQL in Docker) ───
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'sakshi.db'}")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class UserModel(Base):
    __tablename__ = "users"
    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(200), unique=True, nullable=False, index=True)
    hashed_password = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class HistoryModel(Base):
    __tablename__ = "history"
    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4())[:8])
    user_id = Column(String(50), nullable=False, index=True)
    image_url = Column(Text, nullable=True)
    audio_url = Column(Text, nullable=True)
    transcript = Column(Text, nullable=True)
    document_data = Column(JSON, nullable=True)
    result_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Sakshi")
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

# ── Password & Auth Helpers ─────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_token(user_id: str, username: str) -> str:
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode({"sub": username, "id": user_id, "exp": expire}, JWT_SECRET, algorithm=JWT_ALGORITHM)

def get_current_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)) -> Optional[dict]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(authorization.split(" ")[1], JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = db.query(UserModel).filter(UserModel.id == payload.get("id")).first()
        return {"user_id": user.id, "username": user.username, "email": user.email} if user else None
    except Exception:
        return None

def require_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)) -> dict:
    user = get_current_user(authorization, db)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to access this feature")
    return user

# ── Auth Pydantic Models ────────────────────────────────────

class SignupRequest(BaseModel):
    username: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    email: str

# ── Auth Routes ─────────────────────────────────────────────

@app.post("/api/auth/signup", status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: Session = Depends(get_db)):
    username = body.username.strip()
    email = body.email.strip().lower()
    password = body.password.strip()
    if not username or not email or not password:
        raise HTTPException(400, "All fields are required")
    if len(password) < 4:
        raise HTTPException(400, "Password must be at least 4 characters")
    if db.query(UserModel).filter(UserModel.email == email).first():
        raise HTTPException(400, "Email already registered")
    if db.query(UserModel).filter(UserModel.username == username).first():
        raise HTTPException(400, "Username already taken")
    user = UserModel(username=username, email=email, hashed_password=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "Account created", "user_id": user.id}

@app.post("/api/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.query(UserModel).filter(UserModel.email == email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(401, "Incorrect email or password")
    token = create_token(user.id, user.username)
    return {"access_token": token, "token_type": "bearer", "username": user.username, "email": user.email}

@app.get("/api/auth/verify")
def verify_token(user: dict = Depends(require_user)):
    return user

# ── History Routes ──────────────────────────────────────────

class SaveHistoryRequest(BaseModel):
    id: Optional[str] = None
    image_url: Optional[str] = None
    audio_url: Optional[str] = None
    transcript: Optional[str] = None
    document_data: Optional[dict] = None
    result_data: Optional[dict] = None

@app.post("/api/history/save")
def save_history(body: SaveHistoryRequest, user: dict = Depends(require_user), db: Session = Depends(get_db)):
    record = HistoryModel(
        id=body.id or str(uuid.uuid4())[:8],
        user_id=user["user_id"],
        image_url=body.image_url,
        audio_url=body.audio_url,
        transcript=body.transcript,
        document_data=body.document_data,
        result_data=body.result_data,
    )
    db.add(record)
    db.commit()
    return {"message": "Saved", "id": record.id}

@app.get("/api/history/list")
def list_history(user: dict = Depends(require_user), db: Session = Depends(get_db)):
    records = db.query(HistoryModel).filter(HistoryModel.user_id == user["user_id"]).order_by(HistoryModel.created_at.desc()).all()
    return [
        {"id": r.id, "image_url": r.image_url, "audio_url": r.audio_url, "transcript": r.transcript,
         "document_data": r.document_data, "result_data": r.result_data, "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in records
    ]

@app.delete("/api/history/delete/{record_id}")
def delete_history(record_id: str, user: dict = Depends(require_user), db: Session = Depends(get_db)):
    record = db.query(HistoryModel).filter(HistoryModel.id == record_id, HistoryModel.user_id == user["user_id"]).first()
    if not record:
        raise HTTPException(404, "Record not found")
    db.delete(record)
    db.commit()
    return {"message": "Deleted"}

# ── Core Original Logic ─────────────────────────────────────

class ReviewPacket(BaseModel):
    id: str
    document: dict
    transcript: str
    result: dict
    observability: dict | None = None

class TranslateRequest(BaseModel):
    text: str
    target_language: str

def groq_json(url: str, payload: dict) -> dict:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise HTTPException(503, "GROQ_API_KEY is missing")
    req = request.Request(url, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "Sakshi-Hackathon/2.0"}, method="POST")
    try:
        with request.urlopen(req, timeout=50) as response:
            return json.loads(response.read())
    except error.HTTPError as exc:
        raise HTTPException(502, f"Model request failed: {exc.read().decode(errors='replace')[:300]}") from exc
    except error.URLError as exc:
        raise HTTPException(503, f"Model network unavailable: {exc.reason}") from exc

def content(response: dict) -> str:
    try:
        return response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise HTTPException(502, "Model returned an unreadable response.") from exc

def parse_json(raw: str) -> dict:
    try:
        return json.loads(raw.removeprefix("```json").removesuffix("```").strip())
    except json.JSONDecodeError as exc:
        raise HTTPException(502, "Model did not return valid structured evidence.") from exc

async def transcribe(audio: UploadFile) -> str:
    binary = await audio.read()
    if not binary or len(binary) > MAX_BYTES:
        raise HTTPException(400, "Audio must be between 1 byte and 12 MB.")
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise HTTPException(503, "GROQ_API_KEY is missing")
    try:
        reply = Groq(api_key=key).audio.transcriptions.create(file=(audio.filename or "voice-note.wav", binary), model="whisper-large-v3-turbo", response_format="json", temperature=0.0)
        return reply.text.strip()
    except Exception as exc:
        raise HTTPException(503, "Audio transcription unavailable") from exc

async def image_to_claim(image: UploadFile) -> dict:
    binary = await image.read()
    if not binary or len(binary) > MAX_BYTES:
        raise HTTPException(400, "Image must be between 1 byte and 12 MB.")
    mime = image.content_type or mimetypes.guess_type(image.filename or "")[0] or "image/jpeg"
    prompt = """Extract only visible delivery-challan evidence. Return JSON only:
{"supplier":{"value":string|null,"confidence":0-1},"date":{"value":string|null,"confidence":0-1},"items":[{"name":string,"quantity":number|null,"unit":string|null,"condition":string|null,"confidence":0-1}],"amount":{"value":number|null,"currency":string|null,"confidence":0-1},"unknowns":[string]}. Never infer invisible values."""
    response = groq_json(f"{GROQ_BASE}/chat/completions", {"model": GROQ_VISION_MODEL, "temperature": 0.01, "reasoning_effort": "none", "max_completion_tokens": 1024, "response_format": {"type": "json_object"}, "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(binary).decode()}", "detail": "high"}}]}]})
    return parse_json(content(response))

def assess_claims(claim: dict, transcript: str) -> dict:
    prompt = f"""Compare two independent delivery evidence sources. Return JSON only:
{{"conflicts":[{{"field":string,"document_claim":string,"voice_claim":string,"why":string}}],"agreements":[string],"missing_information":[string]}}
Document evidence: {json.dumps(claim)}
Foreman Hindi/Hinglish transcript: {transcript!r}
Only report stated evidence. Identify quantity, material, condition, supplier, amount and date conflicts. Do not make a payment decision."""
    response = groq_json(f"{GROQ_BASE}/chat/completions", {"model": GROQ_VISION_MODEL, "temperature": 0.01, "reasoning_effort": "none", "max_completion_tokens": 1024, "response_format": {"type": "json_object"}, "messages": [{"role": "user", "content": prompt}]})
    return parse_json(content(response))

def empty_document() -> dict:
    return {"supplier": {"value": None, "confidence": 0}, "date": {"value": None, "confidence": 0}, "items": [], "amount": {"value": None, "currency": None, "confidence": 0}, "unknowns": ["Document analysis unavailable"]}

def response_with_pending(reason: str, transcript: str, document: dict | None, timings: dict, started: float, record_id: str | None = None, image_url: str | None = None, audio_url: str | None = None) -> dict:
    document = document or empty_document()
    return {"id": record_id or str(uuid.uuid4())[:8], "image_url": image_url, "audio_url": audio_url, "document": document, "transcript": transcript, "result": pending_review(reason, document, transcript), "observability": {"timings_ms": timings, "total_ms": round((time.perf_counter() - started) * 1000)}}

@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")

@app.get("/api/health")
def health():
    return {"status": "ok", "groq_key_configured": bool(os.getenv("GROQ_API_KEY")), "safety_policy": "deterministic"}

@app.get("/api/evaluate")
def evaluate():
    cases = json.loads(EVAL_CASES.read_text(encoding="utf-8"))
    runs, unsafe = [], 0
    for case in cases:
        actual = safe_result(case["document"], case["transcript"], case["assessment"])["decision"]
        passed = actual == case["expected_decision"]
        unsafe += int(actual == "RECOMMEND_PROCEED" and case["expected_decision"] != "RECOMMEND_PROCEED")
        runs.append({"id": case["id"], "name": case["name"], "expected": case["expected_decision"], "actual": actual, "passed": passed})
    passed = sum(run["passed"] for run in runs)
    return {"case_count": len(cases), "passed": passed, "decision_accuracy": round(passed / len(cases) * 100, 1), "unsafe_approvals": unsafe, "runs": runs}

@app.post("/api/review-packet")
def review_packet(packet: ReviewPacket):
    body = {"packet_version": "1.0", "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **packet.model_dump()}
    return JSONResponse(body, headers={"Content-Disposition": f'attachment; filename="sakshi-review-{packet.id}.json"'})

LANGUAGE_MAP = {
    "hi-in": "Hindi",
    "hi-in-latn": "Hinglish-style Hindi (Hindi words in English/Latin alphabet transliteration)",
    "te-in": "Telugu",
    "te-in-latn": "Hinglish-style Telugu (Telugu words in English/Latin alphabet transliteration)",
    "ta-in": "Tamil",
    "ta-in-latn": "Hinglish-style Tamil (Tamil words in English/Latin alphabet transliteration)",
    "kn-in": "Kannada",
    "kn-in-latn": "Hinglish-style Kannada (Kannada words in English/Latin alphabet transliteration)",
    "ml-in": "Malayalam",
    "ml-in-latn": "Hinglish-style Malayalam (Malayalam words in English/Latin alphabet transliteration)",
    "mr-in": "Marathi",
    "bn-in": "Bengali",
    "gu-in": "Gujarati",
    "pa-in": "Punjabi",
    "ur-in": "Urdu",
    "en-in": "Indian English"
}

@app.post("/api/translate")
def translate(req_body: TranslateRequest):
    lang_key = req_body.target_language.lower()
    lang_name = LANGUAGE_MAP.get(lang_key, req_body.target_language)
    if "latn" in lang_key or "transliteration" in lang_name.lower():
        prompt = f"Translate the following text into {lang_name}. Output JSON format like this: {{\"translated_text\": \"transliterated translation in English script\"}}.\nText to translate:\n{req_body.text}"
    else:
        prompt = f"Translate the following text into {lang_name}. Return your response in JSON format only:\n{{\"translated_text\": \"string\"}}\nText to translate:\n{req_body.text}"
    try:
        response = groq_json(f"{GROQ_BASE}/chat/completions", {
            "model": GROQ_TEXT_MODEL,
            "temperature": 0.01,
            "reasoning_effort": "none",
            "response_format": {"type": "json_object"},
            "max_completion_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}]
        })
        raw_content = content(response).strip()
        if "<think>" in raw_content:
            raw_content = raw_content.split("</think>")[-1].strip()
        parsed = json.loads(raw_content)
        translated = parsed.get("translated_text", "").strip()
        if "<think>" in translated:
            translated = translated.split("</think>")[-1].strip()
        return {"translated_text": translated}
    except Exception as exc:
        raise HTTPException(502, f"Translation failed: {str(exc)}")

@app.post("/api/reconcile")
async def reconcile(image: UploadFile = File(...), transcript: str = Form(""), audio: UploadFile | None = File(None)):
    started, timings = time.perf_counter(), {}
    record_id = str(uuid.uuid4())[:8]
    transcript = transcript.strip()

    # Save image to /media
    image_bytes = await image.read()
    img_ext = (image.filename or "img.jpg").rsplit(".", 1)[-1] or "jpg"
    img_filename = f"{record_id}.{img_ext}"
    (MEDIA_DIR / img_filename).write_bytes(image_bytes)
    image_url = f"/media/{img_filename}"
    await image.seek(0)

    # Save audio to /media if uploaded
    audio_url = None
    if audio:
        audio_bytes = await audio.read()
        if len(audio_bytes) > 0:
            aud_ext = (audio.filename or "audio.wav").rsplit(".", 1)[-1] or "wav"
            aud_filename = f"{record_id}.{aud_ext}"
            (MEDIA_DIR / aud_filename).write_bytes(audio_bytes)
            audio_url = f"/media/{aud_filename}"
            await audio.seek(0)

    if not transcript and audio:
        phase = time.perf_counter()
        try:
            transcript = await transcribe(audio)
            timings["transcription_ms"] = round((time.perf_counter() - phase) * 1000)
        except HTTPException as exc:
            return response_with_pending(exc.detail, transcript, None, timings, started, record_id=record_id, image_url=image_url, audio_url=audio_url)
    if len(transcript) < 8:
        raise HTTPException(400, "Upload a voice note or add a short transcript; Sakshi will not guess what was said.")
    phase = time.perf_counter()
    try:
        document = await image_to_claim(image)
        timings["vision_ms"] = round((time.perf_counter() - phase) * 1000)
    except HTTPException as exc:
        return response_with_pending(exc.detail, transcript, None, timings, started, record_id=record_id, image_url=image_url, audio_url=audio_url)
    phase = time.perf_counter()
    try:
        result = safe_result(document, transcript, assess_claims(document, transcript))
        timings["reconciliation_ms"] = round((time.perf_counter() - phase) * 1000)
    except HTTPException as exc:
        return response_with_pending(exc.detail, transcript, document, timings, started, record_id=record_id, image_url=image_url, audio_url=audio_url)
    return {"id": record_id, "image_url": image_url, "audio_url": audio_url, "document": document, "transcript": transcript, "result": result, "observability": {"timings_ms": timings, "total_ms": round((time.perf_counter() - started) * 1000), "estimated_model_cost_usd": "Demo estimate: confirm against current provider pricing before production"}}
