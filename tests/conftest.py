"""All unit tests are offline; unexpected outbound connections fail immediately."""
import socket

import pytest


@pytest.fixture(scope="session", autouse=True)
def synthetic_suite_database(tmp_path_factory):
    # Older route tests depended on whatever data happened to be in the live DB.
    # Give them a deterministic fixture and keep all suite writes disposable.
    import database
    from scripts.seed_test_database import seed_records

    original = database.DB_PATH
    database.DB_PATH = tmp_path_factory.mktemp("suite") / "professors.db"
    seed_records()
    yield
    database.DB_PATH = original


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    # Never let a developer's live managed store leak into disposable tests.
    monkeypatch.delenv("RETENTION_ROOT", raising=False)
    monkeypatch.delenv("RETENTION_KEY_FILE", raising=False)
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def guarded_connect(sock, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1", "localhost"):
            return original_connect(sock, address)
        raise AssertionError("External network access is forbidden in tests. Mock the provider.")

    def guarded_connect_ex(sock, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1", "localhost"):
            return original_connect_ex(sock, address)
        raise AssertionError("External network access is forbidden in tests. Mock the provider.")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
