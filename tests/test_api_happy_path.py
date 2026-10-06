"""
tests/test_api_happy_path.py — Integration test untuk verifikasi happy path backend endpoints.

Checkpoint 11: Memverifikasi semua endpoint backend bekerja dengan benar, termasuk:
- Happy path: tambah berita (POST 201) → verifikasi di GET list → hapus (DELETE 200) → verifikasi hilang
- Edge cases: DELETE id tidak ada (404), akses tanpa/salah key (403)
- POST /api/cari dengan DB kosong (ditemukan: false), MIME tidak valid (400)

Requirements: 3.1, 4.1, 4.2, 5.1, 5.2, 6.4, 6.5, 6.7
"""

import io
import os
import sqlite3
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image
import pymupdf

import database
from main import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def simple_client(tmp_path):
    """
    Client sederhana yang menggunakan DB isolasi tanpa mock os penuh.
    Database dan upload files diisolasi ke tmp_path.
    """
    db_file = str(tmp_path / "test_berita.db")
    foto_dir = tmp_path / "uploads" / "foto"
    pdf_dir = tmp_path / "uploads" / "pdf"
    tmp_dir = tmp_path / "uploads" / "tmp"
    for folder in (foto_dir, pdf_dir, tmp_dir):
        folder.mkdir(parents=True, exist_ok=True)

    with (
        patch.object(database, "_DB_PATH", db_file),
        patch("main.FOTO_DIR", foto_dir),
        patch("main.PDF_DIR", pdf_dir),
        patch("main.TMP_DIR", tmp_dir),
    ):
        database.init_db()
        client = TestClient(app, raise_server_exceptions=False)
        yield client, db_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ADMIN_KEY = "admin-dev-key"
ADMIN_HEADERS = {"x-admin-key": ADMIN_KEY}


def make_jpeg_bytes(width: int = 32, height: int = 32) -> bytes:
    """Buat bytes gambar JPEG valid."""
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(100, 150, 200)).save(buf, format="JPEG")
    return buf.getvalue()


def make_pdf_bytes() -> bytes:
    """Buat PDF valid satu halaman."""
    document = pymupdf.open()
    document.new_page()
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def add_berita(client, judul: str = "Berita Test", tanggal: str = "2024-06-15"):
    """Helper: tambah berita via POST /api/admin/berita dan kembalikan response."""
    return client.post(
        "/api/admin/berita",
        headers=ADMIN_HEADERS,
        files={
            "judul": (None, judul),
            "tanggal": (None, tanggal),
            "foto": ("test.jpg", make_jpeg_bytes(), "image/jpeg"),
            "pdf": ("test.pdf", make_pdf_bytes(), "application/pdf"),
        },
    )


def cleanup_berita_files(db_file: str):
    """Hapus file foto dan PDF yang tersimpan saat pengujian."""
    try:
        conn = sqlite3.connect(db_file)
        rows = conn.execute("SELECT foto_file, pdf_file FROM berita").fetchall()
        conn.close()
        upload_root = os.path.join(os.path.dirname(db_file), "uploads")
        for row in rows:
            foto_file, pdf_file = row
            for folder, filename in (
                (os.path.join(upload_root, "foto"), foto_file),
                (os.path.join(upload_root, "pdf"), pdf_file),
            ):
                if filename:
                    path = os.path.join(folder, filename)
                    if os.path.exists(path):
                        os.remove(path)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Tests: Happy Path
# ---------------------------------------------------------------------------

class TestHappyPath:
    """Test happy path: tambah → list → hapus."""

    def test_static_assets_are_served(self, simple_client):
        """Assets statis seperti CSS harus tersedia dari URL /static/... ."""
        client, _ = simple_client
        resp = client.get("/static/css/style.css")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert "body" in resp.text.lower()

    def test_add_berita_returns_201(self, simple_client):
        """POST /api/admin/berita dengan data valid harus mengembalikan HTTP 201."""
        client, db_file = simple_client
        try:
            resp = add_berita(client, judul="Berita Test Checkpoint")
            assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert "id" in data
            assert data["judul"] == "Berita Test Checkpoint"
            assert data["message"] == "Berita berhasil ditambahkan."
        finally:
            cleanup_berita_files(db_file)

    def test_added_berita_appears_in_list(self, simple_client):
        """Berita yang ditambahkan harus muncul di GET /api/admin/berita."""
        client, db_file = simple_client
        try:
            add_resp = add_berita(client, judul="Berita Muncul di List")
            assert add_resp.status_code == 201
            berita_id = add_resp.json()["id"]

            list_resp = client.get("/api/admin/berita", headers=ADMIN_HEADERS)
            assert list_resp.status_code == 200
            items = list_resp.json()
            assert len(items) == 1
            assert items[0]["id"] == berita_id
            assert items[0]["judul"] == "Berita Muncul di List"
            assert items[0]["tanggal"] == "2024-06-15"
            assert "foto_url" in items[0]
            assert "pdf_url" in items[0]
        finally:
            cleanup_berita_files(db_file)

    def test_delete_berita_returns_200(self, simple_client):
        """DELETE /api/admin/berita/{id} dengan id valid harus mengembalikan HTTP 200."""
        client, db_file = simple_client
        try:
            add_resp = add_berita(client, judul="Berita Untuk Dihapus")
            assert add_resp.status_code == 201
            berita_id = add_resp.json()["id"]

            del_resp = client.delete(
                f"/api/admin/berita/{berita_id}",
                headers=ADMIN_HEADERS
            )
            assert del_resp.status_code == 200, f"Expected 200, got {del_resp.status_code}: {del_resp.text}"
            assert del_resp.json()["message"] == "Berita berhasil dihapus."
        finally:
            cleanup_berita_files(db_file)

    def test_deleted_berita_gone_from_list(self, simple_client):
        """Berita yang dihapus harus tidak muncul lagi di GET /api/admin/berita."""
        client, db_file = simple_client
        try:
            add_resp = add_berita(client, judul="Berita Yang Akan Hilang")
            assert add_resp.status_code == 201
            berita_id = add_resp.json()["id"]

            del_resp = client.delete(
                f"/api/admin/berita/{berita_id}",
                headers=ADMIN_HEADERS
            )
            assert del_resp.status_code == 200

            list_resp = client.get("/api/admin/berita", headers=ADMIN_HEADERS)
            assert list_resp.status_code == 200
            items = list_resp.json()
            assert len(items) == 0, f"Expected 0 items after delete, got {len(items)}"
        finally:
            cleanup_berita_files(db_file)

    def test_full_happy_path_add_list_delete_verify(self, simple_client):
        """
        Happy path lengkap:
        POST 201 → GET (muncul) → DELETE 200 → GET (hilang)
        """
        client, db_file = simple_client
        try:
            add_resp = add_berita(client, judul="Berita Checkpoint Lengkap", tanggal="2024-12-01")
            assert add_resp.status_code == 201, f"Langkah 1 gagal: {add_resp.status_code} {add_resp.text}"
            berita_id = add_resp.json()["id"]

            list_resp = client.get("/api/admin/berita", headers=ADMIN_HEADERS)
            assert list_resp.status_code == 200
            items = list_resp.json()
            assert any(item["id"] == berita_id for item in items), "Berita tidak ditemukan di list setelah ditambahkan"

            del_resp = client.delete(f"/api/admin/berita/{berita_id}", headers=ADMIN_HEADERS)
            assert del_resp.status_code == 200, f"Langkah 3 gagal: {del_resp.status_code} {del_resp.text}"

            list_resp2 = client.get("/api/admin/berita", headers=ADMIN_HEADERS)
            assert list_resp2.status_code == 200
            items2 = list_resp2.json()
            assert not any(item["id"] == berita_id for item in items2), "Berita masih ada di list setelah dihapus"
        finally:
            cleanup_berita_files(db_file)


# ---------------------------------------------------------------------------
# Tests: Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Test edge cases dan error handling."""

    def test_delete_nonexistent_id_returns_404(self, simple_client):
        """DELETE /api/admin/berita/{id} dengan id tidak ada harus 404."""
        client, _ = simple_client
        resp = client.delete("/api/admin/berita/99999", headers=ADMIN_HEADERS)
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    def test_get_list_empty_db_returns_empty_list(self, simple_client):
        """GET /api/admin/berita saat DB kosong harus mengembalikan list kosong."""
        client, _ = simple_client
        resp = client.get("/api/admin/berita", headers=ADMIN_HEADERS)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_cari_empty_db_returns_not_found(self, simple_client):
        """POST /api/cari dengan DB kosong harus mengembalikan ditemukan=false."""
        client, _ = simple_client
        resp = client.post(
            "/api/cari",
            files={"file": ("test.jpg", make_jpeg_bytes(), "image/jpeg")}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ditemukan"] is False
        assert data["hasil"] == []

    def test_cari_invalid_mime_returns_400(self, simple_client):
        """POST /api/cari dengan MIME type tidak valid harus 400."""
        client, _ = simple_client
        resp = client.post(
            "/api/cari",
            files={"file": ("test.txt", b"bukan gambar", "text/plain")}
        )
        assert resp.status_code == 400

    def test_cari_invalid_image_content_returns_400(self, simple_client):
        """POST /api/cari dengan file yang bukan gambar valid (konten rusak) harus 400."""
        client, _ = simple_client
        resp = client.post(
            "/api/cari",
            files={"file": ("fake.jpg", b"bukan gambar valid", "image/jpeg")}
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Tests: Authentication
# ---------------------------------------------------------------------------

class TestAuthentication:
    """Test autentikasi endpoint admin."""

    def test_get_admin_without_key_returns_403(self, simple_client):
        """GET /api/admin/berita tanpa header x-admin-key harus 403."""
        client, _ = simple_client
        resp = client.get("/api/admin/berita")
        assert resp.status_code == 403

    def test_get_admin_with_wrong_key_returns_403(self, simple_client):
        """GET /api/admin/berita dengan kunci salah harus 403."""
        client, _ = simple_client
        resp = client.get("/api/admin/berita", headers={"x-admin-key": "kunci-salah"})
        assert resp.status_code == 403

    def test_post_berita_without_key_returns_403(self, simple_client):
        """POST /api/admin/berita tanpa kunci harus 403."""
        client, _ = simple_client
        resp = client.post(
            "/api/admin/berita",
            files={
                "judul": (None, "Test"),
                "tanggal": (None, "2024-01-01"),
                "foto": ("test.jpg", make_jpeg_bytes(), "image/jpeg"),
                "pdf": ("test.pdf", make_pdf_bytes(), "application/pdf"),
            }
        )
        assert resp.status_code == 403

    def test_delete_berita_without_key_returns_403(self, simple_client):
        """DELETE /api/admin/berita/{id} tanpa kunci harus 403."""
        client, _ = simple_client
        resp = client.delete("/api/admin/berita/1")
        assert resp.status_code == 403

    def test_get_admin_case_sensitive_key(self, simple_client):
        """x-admin-key bersifat case-sensitive: 'Admin-Dev-Key' harus ditolak."""
        client, _ = simple_client
        resp = client.get("/api/admin/berita", headers={"x-admin-key": "Admin-Dev-Key"})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tests: Validasi Input Upload Admin
# ---------------------------------------------------------------------------

class TestAdminUploadValidation:
    """Test validasi input pada POST /api/admin/berita."""

    def test_invalid_foto_mime_returns_400(self, simple_client):
        """Foto dengan MIME type tidak valid (mis. WebP) harus 400."""
        client, _ = simple_client
        buf = io.BytesIO()
        Image.new("RGB", (32, 32)).save(buf, format="WEBP")
        resp = client.post(
            "/api/admin/berita",
            headers=ADMIN_HEADERS,
            files={
                "judul": (None, "Test"),
                "tanggal": (None, "2024-01-01"),
                "foto": ("test.webp", buf.getvalue(), "image/webp"),
                "pdf": ("test.pdf", make_pdf_bytes(), "application/pdf"),
            }
        )
        assert resp.status_code == 400

    def test_invalid_pdf_mime_returns_400(self, simple_client):
        """PDF dengan MIME type bukan application/pdf harus 400."""
        client, _ = simple_client
        resp = client.post(
            "/api/admin/berita",
            headers=ADMIN_HEADERS,
            files={
                "judul": (None, "Test"),
                "tanggal": (None, "2024-01-01"),
                "foto": ("test.jpg", make_jpeg_bytes(), "image/jpeg"),
                "pdf": ("test.txt", b"bukan pdf", "text/plain"),
            }
        )
        assert resp.status_code == 400

    def test_empty_judul_returns_400(self, simple_client):
        """Judul kosong harus 400."""
        client, _ = simple_client
        resp = client.post(
            "/api/admin/berita",
            headers=ADMIN_HEADERS,
            files={
                "judul": (None, "   "),
                "tanggal": (None, "2024-01-01"),
                "foto": ("test.jpg", make_jpeg_bytes(), "image/jpeg"),
                "pdf": ("test.pdf", make_pdf_bytes(), "application/pdf"),
            }
        )
        assert resp.status_code == 400

    def test_invalid_tanggal_format_returns_400(self, simple_client):
        """Tanggal dengan format tidak valid harus 400."""
        client, _ = simple_client
        resp = client.post(
            "/api/admin/berita",
            headers=ADMIN_HEADERS,
            files={
                "judul": (None, "Test"),
                "tanggal": (None, "15-06-2024"),
                "foto": ("test.jpg", make_jpeg_bytes(), "image/jpeg"),
                "pdf": ("test.pdf", make_pdf_bytes(), "application/pdf"),
            }
        )
        assert resp.status_code == 400
