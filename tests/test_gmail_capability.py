"""Expose availability without initiating OAuth or publishing configuration."""
import pytest

from api.gmail import service


@pytest.mark.parametrize("client_id, client_secret, expected", [
    ("", "", False),
    ("synthetic-client", "", False),
    ("synthetic-client", "synthetic-secret", True),
])
def test_gmail_status_reports_configured_availability_without_secrets(monkeypatch, client_id, client_secret, expected):
    monkeypatch.setenv("GMAIL_CLIENT_ID", client_id)
    monkeypatch.setenv("GMAIL_CLIENT_SECRET", client_secret)
    monkeypatch.setattr(service.token_store, "load_credentials", lambda _user: {})
    result = service.status("synthetic-user").model_dump()
    assert result["available"] is expected
    assert result["connected"] is False
    assert "synthetic-client" not in str(result)
    assert "synthetic-secret" not in str(result)
