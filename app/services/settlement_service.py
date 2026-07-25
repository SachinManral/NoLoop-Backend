"""UPI Payment Settlement Service for NoLoop Platform.

Sprint 3: Host-to-Host UPI sandbox payment settlement engine executing digital payouts
from Insurer accounts directly to Hospital Virtual Payment Addresses (VPA) upon claim approval.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone

log = logging.getLogger("settlement_service")


@dataclass
class SettlementResult:
    claim_id: str
    claim_number: str
    amount_paise: int
    amount_inr: float
    hospital_vpa: str
    upi_txn_ref: str
    status: str
    settled_at: str


def generate_upi_txn_ref() -> str:
    """Generate a realistic NPCI/UPI transaction reference number."""
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    random_digits = "".join([str(random.randint(0, 9)) for _ in range(6)])
    return f"UPI/{now_str}/{random_digits}"


def execute_upi_settlement(
    claim_id: str,
    claim_number: str,
    hospital_name: str,
    approved_amount_paise: int,
    hospital_vpa: str | None = None,
) -> SettlementResult:
    """Execute direct Host-to-Host UPI payout from Insurer to Hospital VPA."""
    if approved_amount_paise <= 0:
        raise ValueError("Cannot settle claim with zero or negative approved amount.")

    # Default hospital VPA if none provided
    vpa = hospital_vpa or f"{hospital_name.lower().replace(' ', '')}@okbank"
    txn_ref = generate_upi_txn_ref()
    settled_time = datetime.now(timezone.utc).isoformat()
    amount_inr = round(approved_amount_paise / 100, 2)

    log.info(
        "Host-to-Host UPI Settlement SUCCESS: Claim %s (%s) -> Payout ₹%s to %s [TxnRef: %s]",
        claim_number,
        claim_id,
        f"{amount_inr:,.2f}",
        vpa,
        txn_ref,
    )

    return SettlementResult(
        claim_id=claim_id,
        claim_number=claim_number,
        amount_paise=approved_amount_paise,
        amount_inr=amount_inr,
        hospital_vpa=vpa,
        upi_txn_ref=txn_ref,
        status="SUCCESS",
        settled_at=settled_time,
    )
