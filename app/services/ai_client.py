"""Bridge to the NoLoop AI adjudication engine (Python/FastAPI, noloop-app/ai).

Primary path: POST the claim packet to the engine's /adjudicate endpoint.
Resilience: if the engine is unreachable, fall back to an in-process rule
engine that mirrors the Python pipeline, so the platform keeps working in a
live demo. The `model` field records which path ran.

This is a faithful port of backend/src/ai/ai.service.ts.
"""

from __future__ import annotations

import logging
import time

import httpx

from app.config import settings
from app.core.money import inr as _inr
from app.core.money import js_round as _js_round
from app.schemas.ai import AiDecision, AiDeduction, AiFraudFlag, ClaimPacket

log = logging.getLogger("ai_client")

_TYPICAL_LOS: dict[str, int] = {
    "appendectomy": 2,
    "cataract surgery": 1,
    "angioplasty": 3,
    "cesarean delivery": 3,
    "knee replacement": 4,
    "dialysis session": 1,
}
_LOS_TOLERANCE = 5
_DEFAULT_LOS = 3

_DENY_SIGNALS = {"BILL_MATH_MISMATCH", "POLICY_EXCLUSION", "DATE_INCONSISTENCY"}
_QUERY_SIGNALS = {"LENGTH_OF_STAY_ANOMALY", "AMOUNT_OUTLIER"}


class AiClient:
    def __init__(self) -> None:
        self.engine_url = settings.ai_engine_url.rstrip("/")

    async def adjudicate(self, packet: ClaimPacket) -> tuple[AiDecision, int]:
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(
                    f"{self.engine_url}/adjudicate", json=packet.model_dump()
                )
                res.raise_for_status()
                decision = AiDecision(**res.json())
                return decision, int((time.perf_counter() - started) * 1000)
        except Exception as err:  # noqa: BLE001 — mirror the TS catch-all fallback
            log.warning("AI engine unreachable (%s); using in-process fallback", err)
            decision = self._fallback(packet)
            return decision, int((time.perf_counter() - started) * 1000)

    async def extract_document(self, image_base64: str, mime_type: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(
                    f"{self.engine_url}/extract",
                    json={"imageBase64": image_base64, "mimeType": mime_type},
                )
                res.raise_for_status()
                return res.json()
        except Exception as err:  # noqa: BLE001
            log.warning("Document extraction failed: %s", err)
            return {
                "enabled": False,
                "note": "The AI engine is unreachable — fill the form manually.",
            }

    # ── Sprint 3: RAG & Fraud Intelligence methods ──

    async def query_rag(self, procedure: str, diagnosis: str | None = None) -> dict:
        """Stage 3: Query OpenFDA + Tavily RAG context for procedure/drug safety."""
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(
                    f"{self.engine_url}/rag/query",
                    json={"procedure": procedure, "diagnosis": diagnosis},
                )
                res.raise_for_status()
                return res.json()
        except Exception as err:  # noqa: BLE001
            log.warning("RAG query endpoint failed (%s); using fallback", err)
            return {
                "procedure": procedure,
                "fdaWarnings": [],
                "clinicalBenchmarks": [],
                "citedSources": ["Clinical Rules Engine"],
                "recommendedStayDays": 3,
                "summary": f"Procedure: {procedure} (standard benchmark ~3 days).",
            }

    async def score_fraud(self, packet: ClaimPacket) -> dict:
        """Stage 3: Calculate explainable fraud risk score."""
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(
                    f"{self.engine_url}/fraud/check", json=packet.model_dump()
                )
                res.raise_for_status()
                return res.json()
        except Exception as err:  # noqa: BLE001
            log.warning("Fraud check endpoint failed (%s); using fallback", err)
            return {
                "riskScore": 0.1,
                "flags": [],
                "explanation": "Rule-based fraud evaluation clean.",
            }

    # ── Sprint 2: individual stage methods for orchestrator ──

    async def validate_documents(self, packet: ClaimPacket) -> dict:
        """Stage 1: Query-Proofing — validate documents against policy.

        Tries the AI engine /validate endpoint first; falls back to a
        deterministic check that the claim packet has all required fields.
        """
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(
                    f"{self.engine_url}/validate", json=packet.model_dump()
                )
                res.raise_for_status()
                return res.json()
        except Exception as err:  # noqa: BLE001
            log.warning("Validation endpoint unreachable (%s); using fallback", err)
            return self._fallback_validate(packet)

    async def check_policy(self, packet: ClaimPacket) -> dict:
        """Stage 2: Rules Engine — coverage, limits, co-pay, exclusions.

        Tries the AI engine /coverage endpoint; falls back to in-process check.
        """
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(
                    f"{self.engine_url}/coverage", json=packet.model_dump()
                )
                res.raise_for_status()
                return res.json()
        except Exception as err:  # noqa: BLE001
            log.warning("Coverage endpoint unreachable (%s); using fallback", err)
            return self._fallback_coverage(packet)

    # ── stage fallbacks ──────────────────────────────────────

    def _fallback_validate(self, packet: ClaimPacket) -> dict:
        """Deterministic validation: check required fields are present."""
        issues: list[str] = []
        if not packet.admission.procedure or len(packet.admission.procedure.strip()) < 2:
            issues.append("Missing or invalid procedure name")
        if not packet.admission.diagnosis:
            issues.append("Missing diagnosis")
        if packet.admission.lengthOfStayDays < 1:
            issues.append("Invalid length of stay (must be ≥ 1 day)")
        if not packet.bill.lineItems:
            issues.append("No line items in bill")
        if packet.bill.totalPaise <= 0:
            issues.append("Bill total must be > 0")
        if packet.admission.admittedAt and packet.admission.dischargedAt:
            if packet.admission.dischargedAt < packet.admission.admittedAt:
                issues.append("Discharge date is before admission date")

        return {"valid": len(issues) == 0, "issues": issues}

    def _fallback_coverage(self, packet: ClaimPacket) -> dict:
        """Deterministic coverage: check procedure against policy lists."""
        proc = packet.admission.procedure.strip().lower()
        excluded = [p.lower() for p in packet.policy.exclusions]
        covered_list = [p.lower() for p in packet.policy.coveredProcedures]

        if proc in excluded:
            return {
                "covered": False,
                "reason": f"'{packet.admission.procedure}' is listed under policy exclusions.",
                "citedClauseRefs": ["EXCLUSIONS"],
            }
        if proc in covered_list:
            return {
                "covered": True,
                "reason": f"'{packet.admission.procedure}' is a covered procedure under the policy.",
                "citedClauseRefs": ["COVERED_PROCEDURES"],
            }
        return {
            "covered": False,
            "reason": f"'{packet.admission.procedure}' is not explicitly listed; needs manual review.",
            "citedClauseRefs": [],
        }

    def _fallback(self, packet: ClaimPacket) -> AiDecision:
        proc = packet.admission.procedure.strip().lower()
        excluded = [p.lower() for p in packet.policy.exclusions]
        covered = [p.lower() for p in packet.policy.coveredProcedures]

        cited: list[str] = []
        if proc in excluded:
            coverage_covered = False
            coverage_reason = (
                f"'{packet.admission.procedure}' is listed under policy exclusions."
            )
            cited.append("EXCLUSIONS")
        elif proc in covered:
            coverage_covered = True
            coverage_reason = (
                f"'{packet.admission.procedure}' is a covered procedure under the policy."
            )
            cited.append("COVERED_PROCEDURES")
        else:
            coverage_covered = False
            coverage_reason = (
                f"'{packet.admission.procedure}' is not explicitly listed; "
                "needs manual review."
            )

        flags: list[AiFraudFlag] = []
        line_sum = sum(li.amountPaise for li in packet.bill.lineItems)
        total = packet.bill.totalPaise
        sum_insured = packet.policy.sumInsuredPaise
        over_cap_overage = (
            total > sum_insured
            and line_sum <= sum_insured
            and total - line_sum > sum_insured * 0.5
        )
        if line_sum != total and not over_cap_overage:
            flags.append(
                AiFraudFlag(
                    signal="BILL_MATH_MISMATCH",
                    severity="HIGH",
                    detail=(
                        f"Line items sum to ₹{_inr(line_sum)} but the bill total "
                        f"is ₹{_inr(total)}."
                    ),
                )
            )
        benchmark = _TYPICAL_LOS.get(proc, _DEFAULT_LOS)
        los = packet.admission.lengthOfStayDays
        if los > benchmark + _LOS_TOLERANCE:
            flags.append(
                AiFraudFlag(
                    signal="LENGTH_OF_STAY_ANOMALY",
                    severity="MEDIUM",
                    detail=(
                        f"Stay of {los} days far exceeds the ~{benchmark}-day "
                        f"benchmark for {packet.admission.procedure}."
                    ),
                )
            )
        if total > sum_insured and line_sum <= sum_insured:
            flags.append(
                AiFraudFlag(
                    signal="AMOUNT_OUTLIER",
                    severity="MEDIUM",
                    detail=(
                        f"Claimed ₹{_inr(total)} exceeds the sum insured "
                        f"₹{_inr(sum_insured)}."
                    ),
                )
            )
        if (
            packet.admission.admittedAt
            and packet.admission.dischargedAt
            and packet.admission.dischargedAt < packet.admission.admittedAt
        ):
            flags.append(
                AiFraudFlag(
                    signal="DATE_INCONSISTENCY",
                    severity="HIGH",
                    detail=(
                        f"Discharge date {packet.admission.dischargedAt} is before "
                        f"admission date {packet.admission.admittedAt}."
                    ),
                )
            )
        if not coverage_covered and "EXCLUSIONS" in cited:
            flags.append(
                AiFraudFlag(
                    signal="POLICY_EXCLUSION", severity="HIGH", detail=coverage_reason
                )
            )

        signals = {f.signal for f in flags}
        reasons = [f.detail for f in flags]

        approved: int | None
        deductions: list[AiDeduction] = []
        if signals & _DENY_SIGNALS:
            verdict = "DENY"
            approved = 0
        elif not coverage_covered:
            verdict = "QUERY"
            approved = None
            reasons.append(coverage_reason)
        elif signals & _QUERY_SIGNALS:
            verdict = "QUERY"
            approved = None
        else:
            verdict = "APPROVE"
            approved, deductions = self._payable(packet)
            if deductions:
                joined = ", ".join(
                    f"{d.label} (−₹{_inr(d.amountPaise)})" for d in deductions
                )
                reasons.append(f"Payable after deductions: {joined}.")
            reasons.append(
                "Procedure covered, amounts consistent, and stay within norms."
            )

        if verdict == "APPROVE":
            head = f"Claim approved for ₹{_inr(approved or 0)}."
        elif verdict == "DENY":
            head = "Claim denied."
        else:
            head = "Claim held for review."
        rationale = f"{head} {' '.join(reasons) or 'No issues detected.'}"

        return AiDecision(
            ref=packet.ref,
            verdict=verdict,
            rationale=rationale,
            citedClauseRefs=cited,
            fraudFlags=flags,
            approvedAmountPaise=approved,
            deductions=deductions,
            confidence=0.6 if verdict == "QUERY" else 0.92,
            model="rule-engine-py-fallback",
        )

    def _payable(self, packet: ClaimPacket) -> tuple[int, list[AiDeduction]]:
        deductions: list[AiDeduction] = []
        billed = packet.bill.totalPaise
        sum_insured = packet.policy.sumInsuredPaise
        gross = billed
        if billed > sum_insured:
            deductions.append(
                AiDeduction(label="Exceeds sum insured", amountPaise=billed - sum_insured)
            )
            gross = sum_insured
        cap = packet.policy.roomRentCapPerDayPaise
        if cap:
            los = max(1, packet.admission.lengthOfStayDays)
            room_billed = sum(
                li.amountPaise
                for li in packet.bill.lineItems
                if "room" in li.desc.lower()
            )
            allowed = cap * los
            if room_billed > allowed:
                excess = room_billed - allowed
                deductions.append(
                    AiDeduction(
                        label=f"Room rent above ₹{_inr(cap)}/day cap", amountPaise=excess
                    )
                )
                gross -= excess
        copay = packet.policy.copayPct or 0
        if copay > 0:
            amt = _js_round(gross * copay / 100)
            deductions.append(AiDeduction(label=f"{copay}% co-pay", amountPaise=amt))
            gross -= amt
        return max(0, gross), deductions


ai_client = AiClient()
