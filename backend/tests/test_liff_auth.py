from app.api import routes
from app.main import app
from app.services.auth import VerifiedLineIdentity, resolve_line_login_channel_id


def test_me_accepts_verified_liff_id_token(client, monkeypatch):
    app.dependency_overrides.pop(routes.current_user, None)

    async def fake_verify_liff_id_token(id_token: str):
        assert id_token == "valid-id-token"
        return VerifiedLineIdentity(
            line_user_id="liff-user",
            display_name="LIFF User",
            picture_url="https://example.com/avatar.jpg",
        )

    monkeypatch.setattr(routes, "verify_liff_id_token", fake_verify_liff_id_token)

    response = client.get("/api/me", headers={"X-Line-Id-Token": "valid-id-token"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["line_user_id"] == "liff-user"
    assert payload["display_name"] == "LIFF User"


def test_me_requires_auth_in_production_without_headers(client, monkeypatch):
    app.dependency_overrides.pop(routes.current_user, None)
    monkeypatch.setattr(routes.settings, "environment", "production")

    response = client.get("/api/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "LINE authentication is required"


def test_resolve_line_login_channel_id_prefers_liff_prefix(monkeypatch):
    monkeypatch.setattr(routes.settings, "line_login_channel_id", None)
    monkeypatch.setattr(routes.settings, "liff_channel_id", "2009526305-adlzUvHT")
    monkeypatch.setattr(routes.settings, "line_channel_id", "2009525591")

    assert resolve_line_login_channel_id() == "2009526305"
