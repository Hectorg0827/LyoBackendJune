"""Signing in to publish: say why a sign-in was refused, never echo the password."""
import json

import httpx
import pytest

from scripts import discover_media_certify as certify


def client(handler):
    return httpx.Client(base_url="https://api.example.test", transport=httpx.MockTransport(handler))


def test_a_refused_sign_in_names_the_reason_and_not_the_password(monkeypatch):
    monkeypatch.delenv("DISCOVER_CERTIFY_TOKEN", raising=False)
    monkeypatch.setenv("DISCOVER_CERTIFY_EMAIL", "library@example.test")
    monkeypatch.setenv("DISCOVER_CERTIFY_PASSWORD", "s3cret-pass")
    refuse = lambda request: httpx.Response(401, json={"error": {"message": "Invalid credentials"}})
    with pytest.raises(SystemExit) as raised:
        certify.authenticate(client(refuse))
    message = str(raised.value)
    assert "401" in message and "Invalid credentials" in message
    assert "s3cret-pass" not in message


def test_a_pasted_line_break_is_not_part_of_the_sign_in(monkeypatch):
    monkeypatch.delenv("DISCOVER_CERTIFY_TOKEN", raising=False)
    monkeypatch.setenv("DISCOVER_CERTIFY_EMAIL", " library@example.test\n")
    monkeypatch.setenv("DISCOVER_CERTIFY_PASSWORD", "pass word \r\n")
    seen = {}

    def accept(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"access_token": "token"})

    assert certify.authenticate(client(accept)) == "token"
    # Spaces inside or at the end of a password are kept: they can be typed.
    assert seen == {"email": "library@example.test", "password": "pass word "}
