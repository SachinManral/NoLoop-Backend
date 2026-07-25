"""Unit tests for NoLoop Rules Engine (Paise Precision)."""

from datetime import date
from app.services.rules_engine import evaluate_policy_rules


def test_covered_procedure_full_approval():
    res = evaluate_policy_rules(
        procedure="Appendectomy",
        diagnosis="Acute Appendicitis",
        billed_paise=7500000,  # ₹75,000
        sum_insured_paise=50000000,  # ₹5,00,000
        length_of_stay_days=2,
        covered_procedures=["Appendectomy", "Cataract"],
        exclusions=["Cosmetic Surgery"],
    )
    assert res.covered is True
    assert res.payable_amount_paise == 7500000
    assert "CLAUSE_COVERAGE" in res.cited_clause_refs


def test_explicit_exclusion_rejection():
    res = evaluate_policy_rules(
        procedure="Cosmetic Rhinoplasty",
        diagnosis="Nasal Deformity",
        billed_paise=12000000,  # ₹1,20,000
        sum_insured_paise=50000000,
        length_of_stay_days=1,
        covered_procedures=["Appendectomy"],
        exclusions=["Cosmetic Rhinoplasty", "Dental"],
    )
    assert res.covered is False
    assert res.payable_amount_paise == 0
    assert "CLAUSE_EXCLUSIONS" in res.cited_clause_refs


def test_room_rent_cap_and_copay_deductions():
    res = evaluate_policy_rules(
        procedure="Knee Replacement",
        diagnosis="Osteoarthritis",
        billed_paise=20000000,  # ₹2,00,000 total bill
        sum_insured_paise=50000000,
        length_of_stay_days=4,
        room_rent_billed_paise=4000000,  # ₹40,000 billed for room (₹10,000/day)
        room_rent_cap_per_day_paise=500000,  # ₹5,000/day cap (max allowed = ₹20,000)
        copay_pct=10,  # 10% copay
        covered_procedures=["Knee Replacement"],
    )
    assert res.covered is True
    # Excess room rent = ₹40k - ₹20k = ₹20,000 (2000000 paise)
    assert res.room_rent_deduction_paise == 2000000
    # Eligible bill after room rent deduction = ₹1,80,000 (18000000 paise)
    # 10% copay = ₹18,000 (1800000 paise)
    assert res.copay_deduction_paise == 1800000
    # Payable = ₹1,80,000 - ₹18,000 = ₹1,62,000 (16200000 paise)
    assert res.payable_amount_paise == 16200000
    assert "CLAUSE_ROOM_RENT_CAP" in res.cited_clause_refs
    assert "CLAUSE_COPAY" in res.cited_clause_refs


def test_waiting_period_violation():
    res = evaluate_policy_rules(
        procedure="Cataract Surgery",
        diagnosis="Cataract",
        billed_paise=3500000,
        sum_insured_paise=30000000,
        length_of_stay_days=1,
        waiting_period_days=90,
        covered_procedures=["Cataract Surgery"],
        admitted_at=date(2026, 3, 10),
        policy_start_date=date(2026, 3, 1),  # Policy active only 9 days
    )
    assert res.covered is False
    assert res.waiting_period_violated is True
    assert res.payable_amount_paise == 0
    assert "CLAUSE_WAITING_PERIOD" in res.cited_clause_refs
