"""Unit tests for UPI Payment Settlement Service."""

import pytest
from app.services.settlement_service import execute_upi_settlement, generate_upi_txn_ref


def test_upi_txn_ref_format():
    ref = generate_upi_txn_ref()
    assert ref.startswith("UPI/")
    parts = ref.split("/")
    assert len(parts) == 3
    assert len(parts[1]) == 8  # YYYYMMDD date string


def test_execute_upi_settlement_success():
    res = execute_upi_settlement(
        claim_id="clm_123456",
        claim_number="CLM-9901",
        hospital_name="Apollo Hospital",
        approved_amount_paise=15000000,  # ₹1,50,000
    )

    assert res.claim_id == "clm_123456"
    assert res.claim_number == "CLM-9901"
    assert res.amount_paise == 15000000
    assert res.amount_inr == 150000.0
    assert res.hospital_vpa == "apollohospital@okbank"
    assert res.status == "SUCCESS"
    assert res.upi_txn_ref.startswith("UPI/")


def test_execute_upi_settlement_zero_amount_error():
    with pytest.raises(ValueError) as exc_info:
        execute_upi_settlement(
            claim_id="clm_err",
            claim_number="CLM-0000",
            hospital_name="Test Hospital",
            approved_amount_paise=0,
        )

    assert "zero or negative" in str(exc_info.value)
