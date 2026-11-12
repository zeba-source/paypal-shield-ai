import pytest

from paypal_db import validate_transition


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("CREATED", "AUTHORIZED"),
        ("AUTHORIZED", "PENDING_2FA"),
        ("AUTHORIZED", "PENDING_REVIEW"),
        ("AUTHORIZED", "CAPTURED"),
        ("PENDING_2FA", "AUTHORIZED"),
        ("PENDING_REVIEW", "AUTHORIZED"),
    ],
)
def test_allowed_paypal_transitions(current, target):
    validate_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("CREATED", "CAPTURED"),
        ("PENDING_2FA", "CAPTURED"),
        ("PENDING_REVIEW", "CAPTURED"),
        ("CAPTURED", "VOIDED"),
        ("VOIDED", "AUTHORIZED"),
    ],
)
def test_illegal_paypal_transitions_raise(current, target):
    with pytest.raises(ValueError, match="Illegal PayPal payment transition"):
        validate_transition(current, target)