# 2-minute pitch — Sakshi

Every evening, a site supervisor must release payment for a material delivery. The supplier sends a photo of a handwritten challan; the foreman sends a chaotic Hindi/Hinglish voice note from a noisy site. Today, the supervisor replays audio, squints at paper, and guesses. One wrong release can mean missing stock, damaged bags, or a dispute with no evidence trail.

We built **Sakshi** — witness in Hindi — an evidence reconciler, not another chatbot. It reads the challan, transcribes the voice report, and compares their independent claims. It shows exactly what agrees, what conflicts, where confidence is low, and the one question a supervisor should ask before payment.

The hard part is not OCR or transcription individually. It is making two unreliable modalities disagree safely. Our vision extraction never fills in an invisible value. The adjudicator cannot approve if the evidence conflicts, is incomplete, or the image confidence is low. It outputs hold-for-review and preserves an auditable source trail.

Remove AI and Sakshi stops working: handwritten evidence, code-mixed speech, and semantic reconciliation all return to manual guesswork. The API provides models; we built the orchestration, strict structured schema, decision policy, evidence graph UI, graceful failure behavior, and a 20-case evaluation harness.

At ten thousand users, synchronous model calls and raw uploads become the bottleneck. We would move to queued workers, signed object storage, caching, rate limits, and human-review queues. But the safety rule would stay: AI can recommend a hold. It never releases money.
