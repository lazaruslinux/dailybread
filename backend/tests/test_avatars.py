"""Avatar upload, serving, permissions, and removal."""

import io

import pytest
from PIL import Image

from app.config import settings
from tests.conftest import user_id


@pytest.fixture(autouse=True)
def isolated_media(tmp_path, monkeypatch):
    """Write avatars under a throwaway dir, never the repo's ./media."""
    monkeypatch.setattr(settings, "media_root", str(tmp_path))


def png_bytes(color=(120, 80, 40), size=(400, 300)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def upload(client, uid, data=None, content_type="image/png"):
    return client.post(
        f"/users/{uid}/avatar",
        files={"file": ("photo.png", data if data is not None else png_bytes(), content_type)},
    )


def test_upload_then_serve_own_avatar(owner):
    uid = user_id(owner)
    # No photo yet: the image 404s and the profile reports none.
    assert owner.get(f"/users/{uid}/avatar").status_code == 404
    assert owner.get("/auth/me").json()["avatar_updated_at"] is None

    res = upload(owner, uid)
    assert res.status_code == 200, res.text
    assert res.json()["avatar_updated_at"] is not None

    img = owner.get(f"/users/{uid}/avatar")
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/webp"
    # Stored image is normalised to the fixed square.
    assert Image.open(io.BytesIO(img.content)).size == (256, 256)


def test_me_reports_avatar_after_upload(owner):
    upload(owner, user_id(owner))
    assert owner.get("/auth/me").json()["avatar_updated_at"] is not None


def test_parent_can_set_childs_avatar(owner, child):
    res = upload(owner, user_id(child))
    assert res.status_code == 200, res.text


def test_non_admin_parent_can_set_childs_avatar(parent, child):
    # Managing a child's photo is a parent power, not an admin one.
    res = upload(parent, user_id(child))
    assert res.status_code == 200, res.text


def test_parent_cannot_set_another_parents_avatar(parent, owner):
    res = upload(parent, user_id(owner))
    assert res.status_code == 403


def test_child_cannot_set_owners_avatar(owner, child):
    res = upload(child, user_id(owner))
    assert res.status_code == 403


def test_child_cannot_set_own_avatar(child):
    # Children don't manage photos at all, not even their own.
    res = upload(child, user_id(child))
    assert res.status_code == 403


def test_rejects_non_image_bytes(owner):
    res = upload(owner, user_id(owner), data=b"this is not an image")
    assert res.status_code == 400


def test_rejects_non_image_content_type(owner):
    res = owner.post(
        f"/users/{user_id(owner)}/avatar",
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert res.status_code == 415


def test_delete_reverts_to_initials(owner):
    uid = user_id(owner)
    upload(owner, uid)
    assert owner.delete(f"/users/{uid}/avatar").status_code == 204
    assert owner.get(f"/users/{uid}/avatar").status_code == 404
    assert owner.get("/auth/me").json()["avatar_updated_at"] is None


def test_a_decode_bomb_is_refused_by_its_header(owner, monkeypatch):
    """Oversized dimensions are rejected from the header alone, before any
    pixel buffer is allocated (the cap is shrunk so a tiny file trips it)."""
    from app import avatars

    monkeypatch.setattr(avatars, "MAX_PIXELS", 100)
    res = upload(owner, user_id(owner), data=png_bytes(size=(20, 20)))
    assert res.status_code == 400
    assert "too large" in res.json()["detail"]
