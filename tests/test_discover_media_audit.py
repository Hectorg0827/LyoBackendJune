"""The media audit vouches only for this API's own media, and only writes to the named database."""
import pytest

from scripts import discover_media_audit as audit

NAME = "a" * 32 + ".mp4"


@pytest.fixture
def stored(monkeypatch):
    # Every filename is "in the bucket": what decides the status is the URL.
    monkeypatch.setattr(audit, "stat_durable_media", lambda folder, name, root: 1234)
    monkeypatch.setattr(audit, "API_HOSTS", {"api.lyoai.app"})


@pytest.mark.parametrize("url,status", [
    (f"https://api.lyoai.app/api/v1/media/file/clips/{NAME}", "ready"),
    (f"/api/v1/media/file/clips/{NAME}", "ready"),
    # Same filename, other host: the stored URL would still send viewers there.
    (f"https://preview.example.app/api/v1/media/file/clips/{NAME}", "external"),
    (f"http://localhost:8000/api/v1/media/file/clips/{NAME}", "external"),
    ("https://commondatastorage.googleapis.com/sample/BigBuckBunny.mp4", "external"),
    (f"https://api.lyoai.app/api/v1/media/file/clips/{'a' * 32}.jpg", "external"),
])
def test_only_this_apis_media_can_be_ready(stored, url, status):
    assert audit.classify(url)[0] == status


def test_a_missing_object_on_this_api_is_missing(monkeypatch):
    monkeypatch.setattr(audit, "stat_durable_media", lambda folder, name, root: None)
    monkeypatch.setattr(audit, "API_HOSTS", {"api.lyoai.app"})
    assert audit.classify(f"https://api.lyoai.app/api/v1/media/file/clips/{NAME}") == ("missing", None)


def test_writes_need_a_backup_and_the_exact_database(monkeypatch):
    url = "postgresql://user:secret@db.internal:5432/railway"
    monkeypatch.delenv("DISCOVER_AUDIT_APPLY", raising=False)
    assert audit.guard(url) is False

    monkeypatch.setenv("DISCOVER_AUDIT_APPLY", "YES")
    with pytest.raises(RuntimeError, match="backup"):
        audit.guard(url)
    monkeypatch.setenv("DISCOVER_AUDIT_BACKUP_VERIFIED", "YES")
    # The right server is not enough: another database on it is refused.
    monkeypatch.setenv("DISCOVER_AUDIT_EXPECTED_TARGET", "db.internal/staging")
    with pytest.raises(RuntimeError, match="EXPECTED_TARGET"):
        audit.guard(url)
    monkeypatch.setenv("DISCOVER_AUDIT_EXPECTED_TARGET", "db.internal/railway")
    assert audit.guard(url) is True
