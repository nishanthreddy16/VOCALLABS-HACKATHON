"""Deterministic safety policy for Sakshi evidence reconciliation."""

from __future__ import annotations

import re
from typing import Any


def clean_text(value: Any) -> str:
    """Return a lowercase, whitespace-normalized comparison value."""
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def confidence_label(value: Any) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "LOW"
    if score >= 0.85:
        return "HIGH"
    if score >= 0.70:
        return "MEDIUM"
    return "LOW"


def evidence_score(document: dict, transcript: str, conflicts: list[dict]) -> dict:
    """A transparent evidence-quality score, never a model probability."""
    factors: list[dict] = []
    score = 100
    items = document.get("items") or []
    if not items:
        score -= 35
        factors.append({"factor": "No readable delivery item", "impact": -35})
    for item in items:
        if item.get("quantity") is None:
            score -= 20
            factors.append({"factor": f"Missing quantity for {item.get('name') or 'item'}", "impact": -20})
        conf = item.get("confidence")
        conf_val = float(conf) if conf is not None else 0.95
        if conf_val < 0.70:
            score -= 15
            factors.append({"factor": f"Low readability for {item.get('name') or 'item'}", "impact": -15})
    if len(transcript.strip()) < 16:
        score -= 25
        factors.append({"factor": "Voice evidence is too short or ambiguous", "impact": -25})
    if conflicts:
        penalty = min(45, 15 * len(conflicts))
        score -= penalty
        factors.append({"factor": "Independent evidence conflicts", "impact": -penalty})
    score = max(0, score)
    return {"score": score, "level": "HIGH" if score >= 85 else "MEDIUM" if score >= 70 else "LOW", "factors": factors}


def document_provenance(document: dict) -> list[dict]:
    evidence: list[dict] = []
    for field in ("supplier", "date"):
        record = document.get(field) or {}
        if record.get("value") is not None:
            evidence.append({"field": field, "value": record["value"], "source": "delivery_challan", "quality": confidence_label(record.get("confidence"))})
    amount = document.get("amount") or {}
    if amount.get("value") is not None:
        evidence.append({"field": "amount", "value": f"{amount['value']} {amount.get('currency') or ''}".strip(), "source": "delivery_challan", "quality": confidence_label(amount.get("confidence"))})
    for item in document.get("items") or []:
        name = item.get("name") or "delivery item"
        if item.get("quantity") is not None:
            evidence.append({"field": "quantity", "item": name, "value": f"{item['quantity']} {item.get('unit') or ''}".strip(), "source": "delivery_challan", "quality": confidence_label(item.get("confidence"))})
        if item.get("condition"):
            evidence.append({"field": "condition", "item": name, "value": item["condition"], "source": "delivery_challan", "quality": confidence_label(item.get("confidence"))})
    return evidence


def voice_provenance(transcript: str) -> dict:
    return {"field": "foreman_report", "value": transcript, "source": "voice_note", "timestamp": "00:00 (full transcript)", "quality": "MEDIUM"}


def rule_based_question(conflicts: list[dict], missing: list[str]) -> str:
    fields = " ".join(clean_text(c.get("field")) for c in conflicts)
    if "quantity" in fields or "count" in fields:
        return "Physically count the delivered bags with the foreman and record the confirmed quantity."
    if any(word in fields for word in ("condition", "damage", "wet", "broken")):
        return "Inspect the reported damaged material and attach a site photograph before payment review."
    if "supplier" in fields:
        return "Verify the supplier name against the purchase order before payment review."
    if missing:
        return "Request a clearer challan photo or a precise foreman confirmation for the missing evidence."
    return "Ask the site supervisor to review the source evidence before taking any payment action."


def safe_result(document: dict, transcript: str, model_result: dict) -> dict:
    """Apply non-negotiable application rules to model-proposed conflicts."""
    conflicts = [c for c in (model_result.get("conflicts") or []) if isinstance(c, dict)]
    missing = list(model_result.get("missing_information") or [])
    for item in document.get("items") or []:
        if item.get("quantity") is None:
            missing.append(f"Readable quantity for {item.get('name') or 'delivery item'}")
        conf = item.get("confidence")
        conf_val = float(conf) if conf is not None else 0.95
        if conf_val < 0.70:
            missing.append(f"Clear reading of {item.get('name') or 'delivery item'}")
    missing.extend(document.get("unknowns") or [])
    missing = list(dict.fromkeys(str(x) for x in missing if str(x).strip()))
    score = evidence_score(document, transcript, conflicts)
    can_proceed = not conflicts and not missing and score["level"] == "HIGH"
    return {
        "decision": "RECOMMEND_PROCEED" if can_proceed else "HOLD_FOR_REVIEW",
        "decision_basis": "deterministic_safety_policy",
        "evidence_quality": score,
        "conflicts": conflicts,
        "agreements": model_result.get("agreements") or [],
        "missing_information": missing,
        "review_question": rule_based_question(conflicts, missing),
        "reasoning_summary": "Evidence is consistent and complete enough for a human to consider payment." if can_proceed else "Payment must remain on hold because evidence conflicts, is incomplete, or is not sufficiently readable.",
        "provenance": document_provenance(document) + [voice_provenance(transcript)],
    }


def pending_review(reason: str, document: dict | None = None, transcript: str = "") -> dict:
    """A safe, usable result for model or network failure."""
    return {
        "decision": "PENDING_REVIEW",
        "decision_basis": "safe_degradation",
        "evidence_quality": {"score": 0, "level": "LOW", "factors": [{"factor": reason, "impact": -100}]},
        "conflicts": [],
        "agreements": [],
        "missing_information": [reason],
        "review_question": "Keep payment on hold and retry analysis when the evidence service is available.",
        "reasoning_summary": "No payment recommendation was made because Sakshi could not safely complete the analysis.",
        "provenance": document_provenance(document or {}) + ([voice_provenance(transcript)] if transcript else []),
    }
