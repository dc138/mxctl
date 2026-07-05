import pytest
from pydantic import TypeAdapter, ValidationError

from mxctl.models import CatchAll, EmailAccount, ErrorEnvelope, Forwarder, SuccessEnvelope

ACCOUNT = {
    "username": "box",
    "email": "box@example.com",
    "quota": 1024,
    "usage": 256.5,
    "limit": 9600,
    "sent": 42,
    "suspended": False,
}


def test_valid_account_list_envelope() -> None:
    adapter = TypeAdapter(SuccessEnvelope[list[EmailAccount]])
    envelope = adapter.validate_python({"success": True, "data": [ACCOUNT]})
    assert envelope.data[0].email == "box@example.com"


def test_missing_required_field_rejected() -> None:
    broken = {key: value for key, value in ACCOUNT.items() if key != "email"}
    with pytest.raises(ValidationError):
        EmailAccount.model_validate(broken)


def test_wrong_type_rejected() -> None:
    broken = dict(ACCOUNT, quota="lots")
    with pytest.raises(ValidationError):
        EmailAccount.model_validate(broken)


def test_extra_fields_ignored() -> None:
    account = EmailAccount.model_validate(dict(ACCOUNT, brand_new_field=1))
    assert account.username == "box"


def test_success_false_rejected_by_success_envelope() -> None:
    adapter = TypeAdapter(SuccessEnvelope[list[str]])
    with pytest.raises(ValidationError):
        adapter.validate_python({"success": False, "data": []})


def test_forwarder_requires_destinations() -> None:
    with pytest.raises(ValidationError):
        Forwarder.model_validate({"alias": "a", "email": "a@example.com"})


def test_catchall_types() -> None:
    assert CatchAll.model_validate({"type": "fail"}).type == "fail"
    catchall = CatchAll.model_validate({"type": "address", "address": "x@example.com"})
    assert catchall.address == "x@example.com"


def test_catchall_unknown_type_rejected() -> None:
    with pytest.raises(ValidationError):
        CatchAll.model_validate({"type": "bounce"})


def test_catchall_address_type_requires_address() -> None:
    with pytest.raises(ValidationError):
        CatchAll.model_validate({"type": "address"})
    with pytest.raises(ValidationError):
        CatchAll.model_validate({"type": "address", "address": None})


def test_error_envelope() -> None:
    envelope = ErrorEnvelope.model_validate(
        {"success": False, "error": {"code": "NOT_FOUND", "message": "missing"}}
    )
    assert envelope.error.code == "NOT_FOUND"
    with pytest.raises(ValidationError):
        ErrorEnvelope.model_validate({"success": True, "error": {"code": "X", "message": "y"}})
