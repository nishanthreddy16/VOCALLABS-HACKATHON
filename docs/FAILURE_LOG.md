# Failure log

| What we tried / expect to fail | What happens now | Next week |
|---|---|---|
| Blurry or folded challan | Low field confidence, missing fields, then HOLD_FOR_REVIEW | Image-quality check and retake guide |
| Hindi/Hinglish slang / bad transcription | Source transcript stays visible; unresolved statement cannot approve payment | Fine-tune a domain glossary and show alternate transcripts |
| Confident model invents an amount | Extraction prompt prohibits inference; missing facts force hold | JSON schema validation plus field-level citation coordinates |
| API/network outage | No decision is returned; captured evidence remains available for export | Offline queue and on-device OCR fallback |
| Repeated delivery photo | Not solved in demo | Perceptual hash and duplicate-delivery alert |
| Payment is disputed after approval | Sakshi never executes payment and preserves review evidence | Immutable reviewer audit trail and role-based approval |
