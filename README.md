# Sakshi — WhatsApp Evidence Reconciler

**Sakshi** helps a small contractor settle a delivery dispute without guessing. A supplier's delivery-challan photo and a foreman's Hindi/Hinglish voice note are converted into a shared claim graph. It highlights exactly what conflicts, shows the evidence behind each claim, and produces a human-review decision — it never silently "approves" a payment.

## Why this is a hackathon-fit project

- **Track:** Multimodal + AI for Bharat
- **Specific user:** a site supervisor reconciling a delivery before releasing payment.
- **AI is essential:** the useful output is an interpretation of messy handwriting plus code-mixed speech and their contradictions. Remove the models and no reliable reconciliation exists.
- **Two genuinely cooperating modalities:** Groq's multilingual Whisper transcription converts the foreman's voice note into a transcript; Groq-hosted Qwen vision reads the challan image and adjudicates the two independent claims. The adjudicator cannot run until both evidence streams are available.
- **Handles being wrong:** every field is tagged with a confidence and source; low-confidence or conflicting cases become **HOLD FOR REVIEW**, never an automatic payment decision.
- **Graceful degradation:** if the network/model is unavailable, the UI still retains the locally captured evidence and exposes an exportable review packet. It does not invent an answer.

## Prior-art check

Closest products found during research:

1. Fixo turns Hindi/Hinglish WhatsApp messages and voice notes into tasks. It does not reconcile a delivery claim against visual proof.
2. Photo-to-calendar products turn an image into events. They do not reason over conflicting, multimodal commercial evidence.
3. Generic OCR expense tools extract a bill, but do not maintain an auditable conflict graph between a verbal on-site report and a challan.

**Difference:** Sakshi is deliberately a *disagreement detector*, not an extraction or task-creation app. Its safe outcome is often “hold payment and ask this exact question.”

## Run it

Requirements: Python 3.11+ and a Groq API key. The service uses only the Python standard library plus FastAPI/Uvicorn.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export GROQ_API_KEY="..."
.venv/bin/uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Upload a challan image and a voice note. A transcript box is supplied for a fast, reliable demo if microphone/file transcription is unavailable.

## Run in VS Code

1. Open this folder in VS Code and install the **Python** extension if prompted.
2. Copy `.env.example` to `.env`, then paste your Groq key after `GROQ_API_KEY=`. Do not commit `.env`.
3. In VS Code, press `Cmd+Shift+P` → **Python: Select Interpreter** → choose `.venv`.
4. Press `F5`, choose **Run Sakshi (Groq)**, then open the localhost URL shown in the terminal.

The included `.vscode/launch.json` loads `.env` automatically.

If the page says **“GROQ_API_KEY is missing”**, check that the `.env` file is in the project root (next to `README.md`) and contains the key with no quotation marks or spaces around `=`:

```env
GROQ_API_KEY=gsk-your-real-key
```

After saving it, stop the running server and press `F5` again.

Verify setup at [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health). It must show:

```json
{"status":"ok","groq_key_configured":true}
```

If it says `false`, you are either running an older extracted ZIP or `.env` is not in the same folder as `README.md`.

### Demo narrative

Use a challan that says **50 cement bags, 12 Aug, ₹18,750**, then record/supply: *“Aaj 55 bags aaye, paanch bag geele hain; payment rok do.”* Sakshi should surface two conflicts: quantity (50 vs 55) and damaged stock. The result is **HOLD FOR REVIEW**, with a ready-to-send clarification question.

## Cost ceiling

At 100 reconciliations/day: 100 small audio transcriptions + 100 image parses + 100 short adjudications. Set a conservative operating ceiling of **$3/day** and enforce a 12 MB upload cap. Cache by file hash and queue work in production. A 24-hour demo uses far less.

## What breaks at 10,000 users?

Synchronous calls and raw uploads. Production needs object storage with signed URLs, a queue, per-tenant rate limits, hash caching, a human-review worklist, and evaluation/trace storage. No payment system should accept a model decision as the final authority.

## Evaluation harness

`eval/cases.json` contains 20 adversarial reconciliation cases. Score every run on (a) correct conflict detection, (b) no invented value, and (c) correct safe decision. The minimum launch gate is 95% on “no auto-approval when evidence conflicts or is low confidence.”

## Submission assets

- [Pitch](docs/PITCH.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Failure log](docs/FAILURE_LOG.md)
## Judge-ready upgrades

The upgraded demo adds a deterministic safety policy, field-level evidence provenance, evidence-driven next actions, safe `PENDING_REVIEW` degradation, downloadable review packets, latency visibility, and a 20-case evaluation endpoint at `/api/evaluate`.

For the live demo, use [the checklist](docs/DEMO_CHECKLIST.md) and include the documented [prior-art comparison](docs/PRIOR_ART.md).
