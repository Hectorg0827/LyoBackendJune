import pytest
from scripts.staging_target import approved_staging_origin, staging_origin


@pytest.mark.parametrize("origin", [
    "https://api.lyoai.app", "https://unrelated-staging.up.railway.app",
    "https://lyolaunchbackend-staging.up.railway.app.evil.test",
    "https://secret@lyolaunchbackend-staging.up.railway.app",
    "https://lyolaunchbackend-staging.up.railway.app:443",
    "http://lyolaunchbackend-staging.up.railway.app",
    "https://lyolaunchbackend-staging.up.railway.app/?target=production",
])
def test_other_services_and_ambiguous_origins_cannot_receive_fixtures(origin):
    assert not approved_staging_origin(origin)


def test_combined_launch_staging_is_allowed_separately_from_reserved_recovery(monkeypatch):
    monkeypatch.setenv("LYO_ONE_STAGING_BACKEND_URL", "https://lyolaunchbackend-staging.up.railway.app")
    assert staging_origin() == "https://lyolaunchbackend-staging.up.railway.app"
    assert approved_staging_origin("https://lyolaunchweb-staging.up.railway.app", web=True)
    assert not approved_staging_origin("https://lyolaunchbackend-staging.up.railway.app", web=True)
