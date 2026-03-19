from app.api import routes


def test_upload_attachment_returns_storage_metadata(client, monkeypatch):
    def fake_store_attachment_bytes(*, content, mime_type, source_type, source_id, user_scope):
        return {
            "type": source_type,
            "mime_type": mime_type,
            "size": len(content),
            "storage_provider": "supabase",
            "storage_bucket": "meal-attachments",
            "storage_path": f"{user_scope}/{source_id}",
            "signed_url": "https://example.com/signed",
        }

    monkeypatch.setattr(routes, "store_attachment_bytes", fake_store_attachment_bytes)

    response = client.post(
        "/api/attachments",
        files={"file": ("meal.jpg", b"fake-image-bytes", "image/jpeg")},
    )

    assert response.status_code == 200
    payload = response.json()["payload"]
    assert payload["attachment"]["storage_provider"] == "supabase"
    assert payload["attachment"]["storage_path"] == "test-user/meal.jpg"
    assert payload["signed_url"] == "https://example.com/signed"
