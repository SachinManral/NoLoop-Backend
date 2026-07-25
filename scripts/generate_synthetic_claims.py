"""Synthetic claim-packet generator (faithful port of generate-synthetic-claims.ts).

Generates realistic FAKE claim packets with a `groundTruth` label, using the
same mulberry32 PRNG so output is reproducible per seed.

Usage:
    python scripts/generate_synthetic_claims.py [count] [seed]

Output: backend-py/data/synthetic/<ref>.json + index.json  (gitignored)
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone

_MASK = 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    return ((a & _MASK) * (b & _MASK)) & _MASK


# Reference: `t = (t + imul(t ^ t>>>7, 61|t)) ^ t`, then `(t ^ t>>>14) >>> 0`.
def mulberry32_exact(seed: int):
    a = seed & _MASK

    def rand() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & _MASK
        t = _imul(a ^ (a >> 15), 1 | a) & _MASK
        t = ((t + _imul(t ^ (t >> 7), 61 | t)) & _MASK) ^ t
        t &= _MASK
        return ((t ^ (t >> 14)) & _MASK) / 4294967296

    return rand


COUNT = int(sys.argv[1]) if len(sys.argv) > 1 else 20
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 42
rand = mulberry32_exact(SEED)


def pick(arr):
    return arr[int(rand() * len(arr))]


def rint(lo: int, hi: int) -> int:
    return int(rand() * (hi - lo + 1)) + lo


def rupees(n: int) -> int:
    return n * 100


FIRST = ["Sachin", "Priya", "Rahul", "Anita", "Vikram", "Neha", "Arjun", "Kavya",
         "Rohit", "Meera", "Aditya", "Sneha"]
LAST = ["Sharma", "Patel", "Reddy", "Iyer", "Nair", "Gupta", "Singh", "Mehta", "Rao", "Das"]
HOSPITALS = ["Meadowpine Hospital", "Brightwater Medical Center", "Stonehaven Hospital",
             "Cedarview Hospital", "Larkmont General Hospital"]
INSURERS = ["Everwell Assurance", "Trustline Health Cover", "Aegisbay Insurance",
            "Harborlight Health", "Brightpath Assurance"]
PROCEDURES = [
    {"name": "Appendectomy", "typicalLosDays": 2, "costLo": 40000, "costHi": 90000},
    {"name": "Cataract Surgery", "typicalLosDays": 1, "costLo": 25000, "costHi": 60000},
    {"name": "Angioplasty", "typicalLosDays": 3, "costLo": 150000, "costHi": 350000},
    {"name": "Cesarean Delivery", "typicalLosDays": 3, "costLo": 60000, "costHi": 140000},
    {"name": "Knee Replacement", "typicalLosDays": 4, "costLo": 200000, "costHi": 450000},
    {"name": "Dialysis Session", "typicalLosDays": 1, "costLo": 8000, "costHi": 20000},
]
EXCLUDABLE = ["Cosmetic Rhinoplasty", "LASIK Eye Surgery", "Dental Implants"]

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
DAY = timedelta(days=1)


def _inr_group(n: int) -> str:
    s = str(int(n))
    if len(s) <= 3:
        return s
    last3, rest = s[-3:], s[:-3]
    parts = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        parts.insert(0, rest)
    return ",".join(parts) + "," + last3


def fmt(d: datetime) -> str:
    return d.date().isoformat()


def build_claim(i: int) -> dict:
    r = rand()
    if r < 0.55:
        anomaly = "CLEAN"
    elif r < 0.68:
        anomaly = "LENGTH_OF_STAY_ANOMALY"
    elif r < 0.81:
        anomaly = "BILL_MATH_MISMATCH"
    elif r < 0.92:
        anomaly = "POLICY_EXCLUSION"
    else:
        anomaly = "AMOUNT_OUTLIER"

    excluded = anomaly == "POLICY_EXCLUSION"
    proc = (
        {"name": pick(EXCLUDABLE), "typicalLosDays": 2, "costLo": 50000, "costHi": 120000}
        if excluded
        else pick(PROCEDURES)
    )
    patient_name = f"{pick(FIRST)} {pick(LAST)}"
    hospital = pick(HOSPITALS)
    insurer = pick(INSURERS)
    sum_insured = rupees(pick([300000, 500000, 1000000]))

    los = (
        proc["typicalLosDays"] + rint(8, 15)
        if anomaly == "LENGTH_OF_STAY_ANOMALY"
        else max(1, proc["typicalLosDays"] + rint(-1, 1))
    )
    admitted_at = BASE + rint(0, 150) * DAY
    discharged_at = admitted_at + los * DAY

    room_per_day = rupees(rint(3000, 8000))
    procedure_cost = rupees(rint(proc["costLo"], proc["costHi"]))
    meds = rupees(rint(2000, 15000))
    items = [
        {"desc": f"Room charges ({los} days)", "amountPaise": room_per_day * los},
        {"desc": proc["name"], "amountPaise": procedure_cost},
        {"desc": "Medicines & consumables", "amountPaise": meds},
    ]
    line_sum = sum(it["amountPaise"] for it in items)
    total_paise = line_sum
    if anomaly == "AMOUNT_OUTLIER":
        total_paise = sum_insured + rupees(rint(50000, 200000))
    if anomaly == "BILL_MATH_MISMATCH":
        total_paise = line_sum + rupees(rint(15000, 60000))

    fraud_signals: list[str] = []
    verdict = "APPROVE"
    reasons: list[str] = []
    if anomaly == "LENGTH_OF_STAY_ANOMALY":
        fraud_signals.append("LENGTH_OF_STAY_ANOMALY")
        verdict = "QUERY"
        reasons.append(
            f"Length of stay {los}d far exceeds typical {proc['typicalLosDays']}d for {proc['name']}"
        )
    elif anomaly == "BILL_MATH_MISMATCH":
        fraud_signals.append("BILL_MATH_MISMATCH")
        verdict = "DENY"
        reasons.append("Bill total does not equal the sum of line items")
    elif anomaly == "POLICY_EXCLUSION":
        fraud_signals.append("POLICY_EXCLUSION")
        verdict = "DENY"
        reasons.append(f"{proc['name']} is excluded under the policy")
    elif anomaly == "AMOUNT_OUTLIER":
        fraud_signals.append("AMOUNT_OUTLIER")
        verdict = "QUERY"
        reasons.append("Claimed amount exceeds the sum insured")
    else:
        reasons.append("Procedure covered, amounts consistent, stay within norms")

    ref = f"NLP-{str(SEED).zfill(2)}{str(i + 1).zfill(4)}"
    return {
        "ref": ref,
        "type": "CASHLESS" if rand() < 0.6 else "REIMBURSEMENT",
        "patient": {"name": patient_name, "age": rint(8, 82), "gender": pick(["M", "F"])},
        "hospital": hospital,
        "insurer": insurer,
        "policy": {
            "policyNo": f"POL-{rint(100000, 999999)}",
            "sumInsuredPaise": sum_insured,
            "coveredProcedures": [p["name"] for p in PROCEDURES],
            "exclusions": EXCLUDABLE,
        },
        "admission": {
            "admittedAt": fmt(admitted_at),
            "dischargedAt": fmt(discharged_at),
            "lengthOfStayDays": los,
            "procedure": proc["name"],
            "diagnosis": f"{proc['name']} indicated",
        },
        "bill": {"lineItems": items, "totalPaise": total_paise},
        "dischargeSummary": (
            f"Patient {patient_name} ({rint(8, 82)}y) admitted on {fmt(admitted_at)} "
            f"for {proc['name']}. Hospitalized {los} day(s) at {hospital}. "
            f"Discharged {fmt(discharged_at)} in stable condition. "
            f"Total billed ₹{_inr_group(total_paise / 100)}."
        ),
        "groundTruth": {
            "verdict": verdict,
            "fraudSignals": fraud_signals,
            "reasons": reasons,
            "anomaly": anomaly,
        },
    }


def main() -> None:
    out_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "synthetic"
    )
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)

    claims = [build_claim(i) for i in range(COUNT)]
    for c in claims:
        with open(os.path.join(out_dir, f"{c['ref']}.json"), "w", encoding="utf-8") as fh:
            json.dump(c, fh, indent=2, ensure_ascii=False)

    by_verdict: dict[str, int] = {}
    by_anomaly: dict[str, int] = {}
    for c in claims:
        v = c["groundTruth"]["verdict"]
        a = c["groundTruth"]["anomaly"]
        by_verdict[v] = by_verdict.get(v, 0) + 1
        by_anomaly[a] = by_anomaly.get(a, 0) + 1
    summary = {
        "generatedCount": len(claims),
        "seed": SEED,
        "byVerdict": by_verdict,
        "byAnomaly": by_anomaly,
        "refs": [c["ref"] for c in claims],
    }
    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)

    print(f"✅ Generated {len(claims)} synthetic claims -> {out_dir}")
    print("   By verdict:", by_verdict)
    print("   By anomaly:", by_anomaly)


if __name__ == "__main__":
    main()
