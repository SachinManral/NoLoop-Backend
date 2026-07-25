"""Deterministic Insurance Rules Engine for NoLoop Platform.

Per PRD.md, TRD.md, and BACKEND_SCHEMA.md:
- All monetary calculations are performed in 64-bit integer Paise (1 INR = 100 Paise).
- Evaluates policy coverage, exclusions, room rent caps, co-pay percentages, and waiting periods.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class RuleEvaluationResult:
    covered: bool
    reason: str
    payable_amount_paise: int
    room_rent_deduction_paise: int = 0
    copay_deduction_paise: int = 0
    waiting_period_violated: bool = False
    cited_clause_refs: list[str] = field(default_factory=list)


def evaluate_policy_rules(
    procedure: str,
    diagnosis: str,
    billed_paise: int,
    sum_insured_paise: int,
    length_of_stay_days: int,
    room_rent_billed_paise: int = 0,
    room_rent_cap_per_day_paise: int | None = None,
    copay_pct: int = 0,
    waiting_period_days: int = 0,
    covered_procedures: list[str] | None = None,
    exclusions: list[str] | None = None,
    admitted_at: date | None = None,
    policy_start_date: date | None = None,
) -> RuleEvaluationResult:
    """Evaluate deterministic policy coverage rules in 64-bit integer paise."""
    proc_clean = procedure.strip().lower()
    covered_procs = [p.strip().lower() for p in (covered_procedures or [])]
    exclusion_list = [p.strip().lower() for p in (exclusions or [])]
    cited_refs: list[str] = ["CLAUSE_GENERAL_TERMS"]

    # 1. Exclusion Check
    for ex in exclusion_list:
        if ex and (ex in proc_clean or proc_clean in ex):
            return RuleEvaluationResult(
                covered=False,
                reason=f"Procedure '{procedure}' is explicitly excluded under policy terms.",
                payable_amount_paise=0,
                cited_clause_refs=["CLAUSE_EXCLUSIONS"],
            )

    # 2. Waiting Period Check
    waiting_violated = False
    if waiting_period_days > 0 and admitted_at and policy_start_date:
        days_active = (admitted_at - policy_start_date).days
        if days_active < waiting_period_days:
            waiting_violated = True
            return RuleEvaluationResult(
                covered=False,
                reason=(
                    f"Claim filed within initial waiting period ({days_active} days active vs "
                    f"{waiting_period_days} days required)."
                ),
                payable_amount_paise=0,
                waiting_period_violated=True,
                cited_clause_refs=["CLAUSE_WAITING_PERIOD"],
            )

    # 3. Coverage Matching
    is_covered = True
    if covered_procs:
        matches = any(cp in proc_clean or proc_clean in cp for cp in covered_procs)
        if not matches:
            is_covered = False

    if not is_covered:
        return RuleEvaluationResult(
            covered=False,
            reason=f"Procedure '{procedure}' is not listed among covered procedures.",
            payable_amount_paise=0,
            cited_clause_refs=["CLAUSE_COVERED_PROCEDURES"],
        )

    cited_refs.append("CLAUSE_COVERAGE")

    # 4. Room Rent Cap Deduction
    room_rent_deduction = 0
    if room_rent_cap_per_day_paise and room_rent_cap_per_day_paise > 0 and length_of_stay_days > 0:
        max_allowed_room_rent = room_rent_cap_per_day_paise * length_of_stay_days
        if room_rent_billed_paise > max_allowed_room_rent:
            room_rent_deduction = room_rent_billed_paise - max_allowed_room_rent
            cited_refs.append("CLAUSE_ROOM_RENT_CAP")

    eligible_amount = max(0, billed_paise - room_rent_deduction)

    # 5. Co-pay Deduction
    copay_deduction = 0
    if copay_pct > 0:
        copay_deduction = int((eligible_amount * copay_pct) / 100)
        cited_refs.append("CLAUSE_COPAY")

    payable_before_si = max(0, eligible_amount - copay_deduction)

    # 6. Sum Insured Cap
    final_payable = min(payable_before_si, sum_insured_paise)
    if payable_before_si > sum_insured_paise:
        cited_refs.append("CLAUSE_SUM_INSURED")

    return RuleEvaluationResult(
        covered=True,
        reason=f"Covered under policy rules. Payable: ₹{final_payable / 100:,.2f}.",
        payable_amount_paise=final_payable,
        room_rent_deduction_paise=room_rent_deduction,
        copay_deduction_paise=copay_deduction,
        waiting_period_violated=False,
        cited_clause_refs=cited_refs,
    )
