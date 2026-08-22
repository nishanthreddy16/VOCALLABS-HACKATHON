import base64
import json
import mimetypes
import os
import time
import uuid
from pathlib import Path
from urllib import error, request

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from groq import Groq
from pydantic import BaseModel

from safety import pending_review, safe_result

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent.parent
MAX_BYTES = 12 * 1024 * 1024
GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_VISION_MODEL = "qwen/qwen3.6-27b"
GROQ_TEXT_MODEL = "qwen/qwen3.6-27b"

# Configure media storage directory (shared volume in Docker Compose)
MEDIA_DIR = Path("/app/media")
if not MEDIA_DIR.exists():
    MEDIA_DIR = ROOT / "media"
    
IMAGES_DIR = MEDIA_DIR / "images"
AUDIO_DIR = MEDIA_DIR / "audio"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Sakshi Reconciliation Service")

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

async def transcribe_bytes(binary: bytes, filename: str) -> str:
    if not binary or len(binary) > MAX_BYTES:
        raise HTTPException(400, "Audio must be between 1 byte and 12 MB.")
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise HTTPException(503, "GROQ_API_KEY is missing")
    try:
        reply = Groq(api_key=key).audio.transcriptions.create(file=(filename, binary), model="whisper-large-v3-turbo", response_format="json", temperature=0.0)
        return reply.text.strip()
    except Exception as exc:
        raise HTTPException(503, "Audio transcription unavailable") from exc

async def image_to_claim_bytes(binary: bytes, mime: str) -> dict:
    if not binary or len(binary) > MAX_BYTES:
        raise HTTPException(400, "Image must be between 1 byte and 12 MB.")
    prompt = """You are an expert OCR and Multimodal Document Intelligence System specializing in Indian delivery challans, goods receipts, Mathadi/labour vouchers, invoices, and site receipts.
Extract all visible evidence from the image (supporting both printed and handwritten text in English, Devanagari/Hindi/Marathi script).

Return ONLY JSON matching this exact structure:
{
  "supplier": {"value": string|null, "confidence": number},
  "date": {"value": string|null, "confidence": number},
  "items": [
    {
      "name": string,
      "quantity": number|null,
      "unit": string|null,
      "condition": string|null,
      "confidence": number
    }
  ],
  "amount": {"value": number|null, "currency": "INR"|string|null, "confidence": number},
  "unknowns": [string]
}

Extraction Guidelines:
1. SUPPLIER: Look for company, organization, union header (e.g., 'महाराष्ट्र राज्य माथाडी...', contractor, trader name, or vendor logo).
2. DATE: Look for date fields (दिनांक, Date, Dt, e.g. '09/04/15').
3. ITEMS: Read all table rows and listed entries (e.g., 'वाराई', 'हमाली', materials, quantities, or line charges). Transcribe Devanagari & Latin script accurately.
4. AMOUNT: Extract total monetary value (कुल रक्कम, एकूण रक्कम, Total, Amount e.g. 3000, 3750). Check both digits and handwritten words ('तीन हजार रुपये').
5. UNKNOWNS: List any field that is completely illegible or obscured by heavy blur. If the image is readable, leave unknowns empty.
Never infer or hallucinate unwritten values."""
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

def response_with_pending(reason: str, transcript: str, document: dict | None, timings: dict, started: float) -> dict:
    document = document or empty_document()
    return {"id": str(uuid.uuid4())[:8], "document": document, "transcript": transcript, "result": pending_review(reason, document, transcript), "observability": {"timings_ms": timings, "total_ms": round((time.perf_counter() - started) * 1000)}}

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

@app.post("/translate")
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

@app.post("/reconcile")
async def reconcile(image: UploadFile = File(...), transcript: str = Form(""), audio: UploadFile | None = File(None)):
    started, timings = time.perf_counter(), {}
    transcript = transcript.strip()
    
    # Read files
    binary_image = await image.read()
    binary_audio = await audio.read() if audio else None
    
    # Save image to shared storage
    img_id = str(uuid.uuid4())
    img_ext = Path(image.filename or "challan.jpg").suffix or ".jpg"
    img_filename = f"{img_id}{img_ext}"
    img_path = IMAGES_DIR / img_filename
    with open(img_path, "wb") as f:
        f.write(binary_image)
    image_url = f"/media/images/{img_filename}"
    
    # Save audio if present
    audio_url = None
    if binary_audio and audio:
        aud_id = str(uuid.uuid4())
        aud_ext = Path(audio.filename or "audio.wav").suffix or ".wav"
        aud_filename = f"{aud_id}{aud_ext}"
        aud_path = AUDIO_DIR / aud_filename
        with open(aud_path, "wb") as f:
            f.write(binary_audio)
        audio_url = f"/media/audio/{aud_filename}"
    
    if not transcript and binary_audio and audio:
        phase = time.perf_counter()
        try:
            transcript = await transcribe_bytes(binary_audio, audio.filename or "voice-note.wav")
            timings["transcription_ms"] = round((time.perf_counter() - phase) * 1000)
        except HTTPException as exc:
            return response_with_pending(exc.detail, transcript, None, timings, started)
            
    if len(transcript) < 8:
        raise HTTPException(400, "Upload a voice note or add a short transcript; Sakshi will not guess what was said.")
        
    phase = time.perf_counter()
    try:
        mime = image.content_type or mimetypes.guess_type(image.filename or "")[0] or "image/jpeg"
        document = await image_to_claim_bytes(binary_image, mime)
        timings["vision_ms"] = round((time.perf_counter() - phase) * 1000)
    except HTTPException as exc:
        return response_with_pending(exc.detail, transcript, None, timings, started)
        
    phase = time.perf_counter()
    try:
        result = safe_result(document, transcript, assess_claims(document, transcript))
        timings["reconciliation_ms"] = round((time.perf_counter() - phase) * 1000)
    except HTTPException as exc:
        return response_with_pending(exc.detail, transcript, document, timings, started)
        
    return {
        "id": str(uuid.uuid4())[:8],
        "document": document,
        "transcript": transcript,
        "result": result,
        "image_url": image_url,
        "audio_url": audio_url,
        "observability": {
            "timings_ms": timings,
            "total_ms": round((time.perf_counter() - started) * 1000),
            "estimated_model_cost_usd": "Demo estimate: confirm against current provider pricing before production"
        }
    }

EVAL_CASES = ROOT / "eval" / "cases.json"

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

