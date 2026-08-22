Sakshi — WhatsApp Evidence Reconciler

Sakshi helps a small contractor settle a delivery dispute without guessing. A supplier’s delivery-challan photo and a foreman’s Hindi/Hinglish voice note are converted into a shared claim graph. It highlights exactly what conflicts, shows the evidence behind each claim, and produces a human-review decision — it never silently “approves” a payment.

Why this is a hackathon-fit project

* Track: Multimodal + AI for Bharat
* Specific user: A site supervisor reconciling a delivery before releasing payment.
* AI is essential: The useful output is an interpretation of messy handwriting plus code-mixed speech and their contradictions. Remove the models and no reliable reconciliation exists.
* Two genuinely cooperating modalities: Groq’s multilingual Whisper transcription converts the foreman’s voice note into a transcript; Groq-hosted Qwen vision reads the challan image and extracts the visual evidence. The reconciliation layer compares the two independent evidence streams only after both are available.
* Handles being wrong: Every field is tagged with a confidence and source; low-confidence or conflicting cases become HOLD FOR REVIEW, never an automatic payment decision.
* Human-in-the-loop: Sakshi does not decide whether a payment should actually be released. It identifies whether the available evidence is consistent and tells the human what needs to be verified.

How Sakshi works

Challan Image
     |
     v
Vision Model
     |
     v
Challan Evidence
     |
     |----------------------|
                            |
                            v
                    Evidence Reconciliation
                            ^
                            |
Voice Note -> Whisper -> Voice Evidence
                            |
                            v
                    Conflict Detection
                            |
                            v
                     Human Review
                       /       \
                      /         \
                     v           v
        RECOMMEND_PROCEED   HOLD_FOR_REVIEW

Sakshi compares evidence such as:

* Quantity
* Material
* Amount
* Condition
* Missing or damaged items

For example:

Challan: 50 cement bags
Voice note: 55 cement bags arrived
Conflict: Quantity mismatch
Decision: HOLD_FOR_REVIEW

Prior-art check

Closest products found during research:

1. Fixo turns Hindi/Hinglish WhatsApp messages and voice notes into tasks. It does not reconcile a delivery claim against visual proof.
2. Photo-to-calendar products turn an image into events. They do not reason over conflicting, multimodal commercial evidence.
3. Generic OCR expense tools extract a bill, but do not maintain an auditable conflict graph between a verbal on-site report and a challan.

Difference: Sakshi is deliberately a disagreement detector, not an extraction or task-creation app. Its safe outcome is often “hold payment and ask this exact question.”

Safety-first decision policy

Sakshi has two primary outcomes:

RECOMMEND_PROCEED

Used when the available evidence is sufficiently consistent and no significant unresolved conflict is detected.

HOLD_FOR_REVIEW

Used when:

* Quantities do not match
* Amounts do not match
* Material is missing
* Damage is reported
* Important evidence is missing
* A claim has low confidence
* The system cannot safely determine the correct outcome

Sakshi does not decide which source is truthful. It exposes the disagreement so that a human can verify it.

Example conflict

Challan:
50 cement bags
Voice note:
55 cement bags arrived
Conflict:
Delivered quantity differs from challan.
Decision:
HOLD_FOR_REVIEW

Another example:

Challan:
50 bags
No damage mentioned.
Voice note:
5 bags are wet.
Conflict:
Condition reported by the foreman is missing from the challan.
Decision:
HOLD_FOR_REVIEW

Graceful degradation

If network access or model processing is unavailable, Sakshi does not invent an answer.

The available evidence can still be retained for review, and a transcript can be entered manually when microphone or file transcription is unavailable. This allows the reconciliation workflow to be demonstrated even when automated transcription is temporarily unavailable.

Technology

* Python 3.11+
* FastAPI
* Uvicorn
* Groq API
* Multilingual Whisper for voice transcription
* Qwen Vision for challan understanding
* GitHub
* VS Code

Run it on Mac

Requirements

* macOS
* Python 3.11+
* Groq API key
* Internet connection

1. Open Terminal

Go to the project folder:

cd /path/to/VOCALLABS-HACKATHON

2. Create a Python virtual environment

python3 -m venv .venv

3. Activate the virtual environment

source .venv/bin/activate

After activation, your Terminal should show something similar to:

(.venv) your-mac:VOCALLABS-HACKATHON$

4. Install the dependencies

python -m pip install -r requirements.txt

5. Configure the Groq API key

Copy the example environment file:

cp .env.example .env

Open it:

nano .env

Add your key:

GROQ_API_KEY=your_groq_api_key

Save in nano:

Control + O
Enter
Control + X

Do not commit .env to GitHub.

6. Start Sakshi

With the virtual environment activated:

python -m uvicorn app.main:app --reload

You should see a localhost address in Terminal.

Open:

http://127.0.0.1:8000

7. Stop the server

When finished, press:

Control + C

Run in VS Code on Mac

1. Open the VOCALLABS-HACKATHON folder in VS Code.
2. Install the Python extension if VS Code asks.
3. Open the VS Code terminal.
4. Create the environment:

python3 -m venv .venv

5. Activate it:

source .venv/bin/activate

6. Install dependencies:

python -m pip install -r requirements.txt

7. Copy the environment file:

cp .env.example .env

8. Add your Groq API key to .env:

GROQ_API_KEY=your_groq_api_key

9. Press:

Cmd + Shift + P

10. Select:

Python: Select Interpreter

11. Choose the interpreter inside:

.venv/bin/python

12. Start the application from the VS Code terminal:

python -m uvicorn app.main:app --reload

13. Open:

http://127.0.0.1:8000

Demo workflow

1. Upload a delivery challan image.
2. Upload the foreman’s Hindi/Hinglish voice note.
3. Sakshi transcribes the voice note.
4. Sakshi extracts evidence from the challan.
5. The two evidence streams are compared.
6. Conflicts are highlighted.
7. The source and confidence of each claim are displayed.
8. Sakshi produces a review decision.

Example:

CHALLAN
50 cement bags
VOICE NOTE
55 cement bags arrived
5 bags are wet
CONFLICTS
• Quantity mismatch
• Damaged material reported
DECISION
HOLD_FOR_REVIEW

Evaluation

The reconciliation logic is tested using representative delivery scenarios, including:

* Matching evidence
* Missing materials
* Quantity mismatches
* Amount mismatches
* Damaged or wet materials
* Conflicting evidence
* Human-review cases

The important safety property is:

When evidence is inconsistent or insufficient, Sakshi prefers human review over an unsupported payment decision.

Security

* API keys are stored in environment variables.
* .env is excluded from Git.
* .env.example is provided as a template.
* API keys should never be placed directly in frontend code or committed to GitHub.

Core principle

Sakshi does not guess. Sakshi shows the evidence, finds the disagreement, and asks a human to decide.
