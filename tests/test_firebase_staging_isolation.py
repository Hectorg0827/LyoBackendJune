"""Staging Firebase must never select production credentials or ADC implicitly."""
import importlib
import json
from types import SimpleNamespace

import pytest


client_module = importlib.import_module("lyo_app.integrations.firebase_client")
ISOLATED = "lyo-launch-test"


@pytest.mark.parametrize(("project", "certificate", "gcp"), [
    (ISOLATED, ISOLATED, None),
    ("lyo-staging-artifacts", "lyo-staging-artifacts", "lyo-staging-artifacts"),
    ("lyo-sandbox-artifacts", "lyo-sandbox-artifacts", None),
])
def test_explicit_matching_isolated_project_is_allowed(project, certificate, gcp):
    assert client_module._is_isolated_staging_project(project, certificate, gcp)


@pytest.mark.parametrize(("project", "certificate", "gcp"), [
    (None, ISOLATED, None),
    ("lyo-production", "lyo-production", None),
    ("lyoapp", "lyoapp", None),
    (ISOLATED, "lyo-production", None),
    (ISOLATED, ISOLATED, "lyo-production"),
    ("lyo-test.evil", "lyo-test.evil", None),
])
def test_untrusted_or_mismatched_staging_project_is_rejected(project, certificate, gcp):
    assert not client_module._is_isolated_staging_project(project, certificate, gcp)


def mock_sdk(monkeypatch, *, reused_project=None):
    calls = []
    def certificate(value):
        calls.append("certificate")
        return value
    def adc():
        calls.append("ADC")
        raise AssertionError("Staging may not attempt ApplicationDefault")
    def get_app():
        if reused_project is None:
            raise ValueError("SDK not initialized")
        return SimpleNamespace(project_id=reused_project)
    def initialize_app(cred, options):
        calls.append("initialize_app")
        return SimpleNamespace(project_id=options["projectId"])
    def firestore_client(*, app):
        calls.append("firestore")
        return SimpleNamespace(project=app.project_id)
    monkeypatch.setattr(client_module, "_FIREBASE_AVAILABLE", True)
    monkeypatch.setattr(client_module, "credentials",
                        SimpleNamespace(Certificate=certificate, ApplicationDefault=adc), raising=False)
    monkeypatch.setattr(client_module, "firebase_admin",
                        SimpleNamespace(get_app=get_app, initialize_app=initialize_app), raising=False)
    monkeypatch.setattr(client_module, "firestore",
                        SimpleNamespace(client=firestore_client), raising=False)
    monkeypatch.setattr(client_module, "storage",
                        SimpleNamespace(bucket=lambda **kw: None), raising=False)
    instance = object.__new__(client_module.FirebaseClient)
    client_module.FirebaseClient.__init__(instance)
    return instance, calls


def test_no_staging_certificate_disables_storage_without_adc(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", ISOLATED)
    monkeypatch.delenv("FIREBASE_CREDENTIALS_JSON", raising=False)
    monkeypatch.delenv("FIREBASE_CREDENTIALS_PATH", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    instance, calls = mock_sdk(monkeypatch)
    instance.initialize_app()
    assert not instance.enabled
    assert instance.db is None
    assert calls == []


@pytest.mark.parametrize("configured_id", ["lyo-production", "different-staging"])
def test_staging_rejects_mismatched_credential_before_sdk(monkeypatch, configured_id):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", ISOLATED)
    monkeypatch.setenv("FIREBASE_CREDENTIALS_JSON", json.dumps({"project_id": configured_id}))
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    instance, calls = mock_sdk(monkeypatch)
    instance.initialize_app()
    assert not instance.enabled
    assert calls == []


def test_matching_isolated_certificate_enables_firestore(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", ISOLATED)
    monkeypatch.setenv("FIREBASE_CREDENTIALS_JSON", json.dumps({"project_id": ISOLATED}))
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    instance, calls = mock_sdk(monkeypatch)
    instance.initialize_app()
    assert instance.enabled
    assert instance.db.project == ISOLATED
    assert calls == ["certificate", "initialize_app", "firestore"]


def test_reused_sdk_for_different_project_cannot_enable_staging(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", ISOLATED)
    monkeypatch.setenv("FIREBASE_CREDENTIALS_JSON", json.dumps({"project_id": ISOLATED}))
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    instance, calls = mock_sdk(monkeypatch, reused_project="lyo-production")
    instance.initialize_app()
    assert not instance.enabled
    assert "firestore" not in calls
