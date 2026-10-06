"""
tests/test_api.py — Integration tests untuk backend API.

Task 15.1: Happy path, edge cases, error handling, dan file deletion failure.

Skenario yang diuji:
- Happy path: tambah berita (POST 201) → verifikasi di GET list → hapus (DELETE 200)
  → verifikasi hilang dari GET list
- Edge cases: DELETE id tidak ada (404); GET list saat DB kosong ([]); POST /api/cari
  dengan DB kosong ({"ditemukan": false, "hasil": []})
- Error handling: mock DB failure pada /api/cari → 503; mock DB failure pada
  GET /api/admin/berita → 500
- File deletion failure on DELETE: mock os.remove raise OSError → tetap 200

Requirements: 4.1, 4.2, 4.4, 5.1, 5.2, 6.4, 6.5, 6.8
"""

import io
import os
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image
import pymupdf

import main
import database
from main import app, cleanup_orphan_uploads, index_missing_pdf_pages

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ADMIN_KEY = "admin-dev-key"
ADMIN_HEADERS = {"x-admin-key": ADMIN_KEY}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_jpeg_bytes(width: int = 32, height: int = 32) -> bytes:
    """Buat bytes gambar JPEG valid dalam memori."""
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(128, 64, 200)).save(buf, format="JPEG")
    return buf.getvalue()


def _make_pdf_bytes(image_bytes: bytes | None = None) -> bytes:
    """Buat PDF valid satu halaman dengan konten gambar memenuhi halaman."""
    image_bytes = image_bytes or _make_jpeg_bytes()
    document = pymupdf.open()
    page = document.new_page(width=32, height=32)
    page.insert_image(page.rect, stream=image_bytes)
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def _post_berita(client: TestClient, judul: str = "Berita Test", tanggal: str = "2024-07-20"):
    """Kirim POST /api/admin/berita dengan data valid dan kembalikan response."""
    return client.post(
        "/api/admin/berita",
        headers=ADMIN_HEADERS,
        files={
            "judul": (None, judul),
            "tanggal": (None, tanggal),
            "foto": ("foto.jpg", _make_jpeg_bytes(), "image/jpeg"),
            "pdf": ("berita.pdf", _make_pdf_bytes(), "application/pdf"),
        },
    )


def _cleanup_uploaded_files(db_path: str, foto_dir: str, pdf_dir: str) -> None:
    """Hapus file foto/PDF yang tersimpan di disk setelah test selesai."""
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT foto_file, pdf_file FROM berita").fetchall()
        conn.close()
        for foto_file, pdf_file in rows:
            for folder, fname in [(foto_dir, foto_file), (pdf_dir, pdf_file)]:
                if not fname:
                    continue
                full = os.path.join(folder, fname)
                if os.path.exists(full):
                    os.remove(full)
    except Exception:
        pass  # Best-effort cleanup — test isolation is the priority


# ---------------------------------------------------------------------------
# Fixture: isolated client with a fresh in-memory-ish DB per test
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path):
    """
    TestClient dengan database SQLite terisolasi di tmp_path.
    Setiap test mendapatkan database yang bersih.
    Cleanup file yang tersimpan di disk dilakukan setelah test selesai.
    """
    db_file = str(tmp_path / "berita_test.db")
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
        test_client = TestClient(app, raise_server_exceptions=False)
        yield test_client, db_file

    # Cleanup uploaded files after test
    _cleanup_uploaded_files(db_file, str(foto_dir), str(pdf_dir))


def test_cleanup_orphan_uploads_keeps_referenced_and_non_media_files(tmp_path):
    db_file = str(tmp_path / "cleanup_test.db")
    foto_dir = tmp_path / "foto"
    pdf_dir = tmp_path / "pdf"
    foto_dir.mkdir()
    pdf_dir.mkdir()

    referenced_photo = "dipakai.jpg"
    referenced_pdf = "dipakai.pdf"
    orphan_photo = "yatim.png"
    orphan_pdf = "yatim.pdf"
    ignored_file = "catatan.txt"
    for folder, name in (
        (foto_dir, referenced_photo),
        (pdf_dir, referenced_pdf),
        (foto_dir, orphan_photo),
        (pdf_dir, orphan_pdf),
        (foto_dir, ignored_file),
        (foto_dir, ".gitkeep"),
    ):
        (folder / name).write_text("file", encoding="utf-8")

    with (
        patch.object(database, "_DB_PATH", db_file),
        patch("main.FOTO_DIR", foto_dir),
        patch("main.PDF_DIR", pdf_dir),
    ):
        database.init_db()
        conn = database.get_connection()
        try:
            conn.execute(
                "INSERT INTO berita "
                "(judul, tanggal, foto_file, pdf_file, phash, dhash) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("Berita", "2024-01-01", referenced_photo, referenced_pdf, "", ""),
            )
            conn.commit()
        finally:
            conn.close()

        assert cleanup_orphan_uploads() == 2

    assert (foto_dir / referenced_photo).exists()
    assert (pdf_dir / referenced_pdf).exists()
    assert (foto_dir / ignored_file).exists()
    assert (foto_dir / ".gitkeep").exists()
    assert not (foto_dir / orphan_photo).exists()
    assert not (pdf_dir / orphan_pdf).exists()


# ---------------------------------------------------------------------------
# 1. Happy Path
# ---------------------------------------------------------------------------


class TestHappyPath:
    """
    Full happy path: POST /api/admin/berita (201) → GET list (muncul) →
    DELETE /api/admin/berita/{id} (200) → GET list (hilang).

    Requirements: 3.1, 4.1, 5.1, 5.2
    """

    def test_add_berita_returns_201(self, client):
        """POST /api/admin/berita dengan data valid harus mengembalikan HTTP 201."""
        tc, _ = client
        resp = _post_berita(tc, judul="Berita Pertama")
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert "id" in body
        assert body["judul"] == "Berita Pertama"
        assert "message" in body

    def test_add_berita_without_photo_is_allowed(self, client):
        """POST /api/admin/berita tanpa foto harus tetap sukses."""
        tc, _ = client
        resp = tc.post(
            "/api/admin/berita",
            headers=ADMIN_HEADERS,
            files={
                "judul": (None, "Tanpa Foto"),
                "tanggal": (None, "2024-07-20"),
                "pdf": ("berita.pdf", _make_pdf_bytes(), "application/pdf"),
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["judul"] == "Tanpa Foto"

    def test_search_matches_page_image_from_pdf_without_news_photo(self, client):
        """Gambar unggahan dicocokkan dengan halaman PDF meski foto berita kosong."""
        tc, db_file = client
        query_image = _make_jpeg_bytes()
        pdf_bytes = _make_pdf_bytes(query_image)

        add_response = tc.post(
            "/api/admin/berita",
            headers=ADMIN_HEADERS,
            files={
                "judul": (None, "Berita dari PDF"),
                "tanggal": (None, "2024-07-20"),
                "pdf": ("berita.pdf", pdf_bytes, "application/pdf"),
            },
        )
        assert add_response.status_code == 201, add_response.text

        conn = sqlite3.connect(db_file)
        try:
            indexed_pages = conn.execute(
                "SELECT page_number FROM berita_pdf_hashes WHERE berita_id = ?",
                (add_response.json()["id"],),
            ).fetchall()
            indexed_images = conn.execute(
                "SELECT COUNT(*) FROM berita_pdf_image_hashes WHERE berita_id = ?",
                (add_response.json()["id"],),
            ).fetchone()[0]
        finally:
            conn.close()
        assert indexed_pages == [(1,)]
        assert indexed_images == 1

        response = tc.post(
            "/api/cari",
            files={"file": ("gambar.jpg", query_image, "image/jpeg")},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["ditemukan"] is True
        assert body["hasil"][0]["judul"] == "Berita dari PDF"
        assert body["hasil"][0]["foto_url"] == ""
        assert body["hasil"][0]["pdf_url"].startswith("/files/pdf/")

    def test_legacy_pdf_without_page_index_is_indexed(self, client):
        """Startup helper mengindeks PDF lama yang belum memiliki hash halaman."""
        _, db_file = client
        pdf_name = "legacy.pdf"
        (main.PDF_DIR / pdf_name).write_bytes(_make_pdf_bytes())
        conn = sqlite3.connect(db_file)
        try:
            conn.execute(
                "INSERT INTO berita "
                "(judul, tanggal, foto_file, pdf_file, phash, dhash) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("Berita lama", "2024-07-20", "", pdf_name, "", ""),
            )
            conn.commit()
        finally:
            conn.close()

        assert index_missing_pdf_pages() == 1
        assert index_missing_pdf_pages() == 0
        conn = sqlite3.connect(db_file)
        try:
            page_count = conn.execute(
                "SELECT COUNT(*) FROM berita_pdf_hashes"
            ).fetchone()[0]
            image_count = conn.execute(
                "SELECT COUNT(*) FROM berita_pdf_image_hashes"
            ).fetchone()[0]
        finally:
            conn.close()
        assert page_count == 1
        assert image_count == 1

    def test_added_berita_visible_in_list(self, client):
        """Berita yang baru ditambahkan harus muncul di GET /api/admin/berita."""
        tc, _ = client
        add_resp = _post_berita(tc, judul="Terlihat di List")
        assert add_resp.status_code == 201
        berita_id = add_resp.json()["id"]

        list_resp = tc.get("/api/admin/berita", headers=ADMIN_HEADERS)
        assert list_resp.status_code == 200
        items = list_resp.json()
        assert len(items) == 1
        assert items[0]["id"] == berita_id
        assert items[0]["judul"] == "Terlihat di List"
        assert items[0]["tanggal"] == "2024-07-20"
        assert items[0]["foto_url"].startswith("/files/foto/")
        assert items[0]["pdf_url"].startswith("/files/pdf/")

    def test_delete_berita_returns_200(self, client):
        """DELETE /api/admin/berita/{id} dengan id yang valid harus mengembalikan HTTP 200."""
        tc, _ = client
        add_resp = _post_berita(tc, judul="Akan Dihapus")
        assert add_resp.status_code == 201
        berita_id = add_resp.json()["id"]

        del_resp = tc.delete(f"/api/admin/berita/{berita_id}", headers=ADMIN_HEADERS)
        assert del_resp.status_code == 200, f"Expected 200, got {del_resp.status_code}: {del_resp.text}"
        assert "dihapus" in del_resp.json().get("message", "").lower()

    def test_deleted_berita_gone_from_list(self, client):
        """Berita yang telah dihapus tidak boleh muncul di GET /api/admin/berita."""
        tc, _ = client
        add_resp = _post_berita(tc, judul="Akan Hilang")
        assert add_resp.status_code == 201
        berita_id = add_resp.json()["id"]

        del_resp = tc.delete(f"/api/admin/berita/{berita_id}", headers=ADMIN_HEADERS)
        assert del_resp.status_code == 200

        list_resp = tc.get("/api/admin/berita", headers=ADMIN_HEADERS)
        assert list_resp.status_code == 200
        ids = [item["id"] for item in list_resp.json()]
        assert berita_id not in ids, "Berita yang dihapus masih muncul di daftar"

    def test_full_lifecycle(self, client):
        """
        Full lifecycle: POST 201 → GET (muncul) → DELETE 200 → GET (hilang).

        Requirements: 4.1, 5.1
        """
        tc, _ = client

        # 1. Tambah
        add_resp = _post_berita(tc, judul="Berita Siklus Penuh", tanggal="2024-12-31")
        assert add_resp.status_code == 201, f"Langkah 1 gagal: {add_resp.text}"
        berita_id = add_resp.json()["id"]

        # 2. Verifikasi muncul di list
        list_resp = tc.get("/api/admin/berita", headers=ADMIN_HEADERS)
        assert list_resp.status_code == 200
        assert any(item["id"] == berita_id for item in list_resp.json()), (
            "Berita tidak ditemukan di daftar setelah ditambahkan"
        )

        # 3. Hapus
        del_resp = tc.delete(f"/api/admin/berita/{berita_id}", headers=ADMIN_HEADERS)
        assert del_resp.status_code == 200, f"Langkah 3 gagal: {del_resp.text}"

        # 4. Verifikasi hilang dari list
        list_resp2 = tc.get("/api/admin/berita", headers=ADMIN_HEADERS)
        assert list_resp2.status_code == 200
        assert not any(item["id"] == berita_id for item in list_resp2.json()), (
            "Berita masih ada di daftar setelah dihapus"
        )

    def test_list_sorted_descending_by_date(self, client):
        """
        Daftar berita dari GET /api/admin/berita harus terurut descending berdasarkan tanggal.

        Requirements: 5.1
        """
        tc, _ = client

        _post_berita(tc, judul="Berita Lama", tanggal="2023-01-01")
        _post_berita(tc, judul="Berita Baru", tanggal="2024-06-01")
        _post_berita(tc, judul="Berita Terbaru", tanggal="2024-12-01")

        list_resp = tc.get("/api/admin/berita", headers=ADMIN_HEADERS)
        assert list_resp.status_code == 200
        items = list_resp.json()
        assert len(items) == 3
        dates = [item["tanggal"] for item in items]
        assert dates == sorted(dates, reverse=True), (
            f"Daftar tidak terurut descending: {dates}"
        )


# ---------------------------------------------------------------------------
# 2. Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """
    Edge cases: DELETE id tidak ada, GET list kosong, cari dengan DB kosong.

    Requirements: 4.2, 5.2, 6.4, 6.5
    """

    def test_delete_nonexistent_id_returns_404(self, client):
        """
        DELETE /api/admin/berita/{id} dengan id yang tidak ada di DB harus 404.

        Requirements: 4.2
        """
        tc, _ = client
        resp = tc.delete("/api/admin/berita/99999", headers=ADMIN_HEADERS)
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        assert "detail" in resp.json()

    def test_get_list_empty_db_returns_empty_array(self, client):
        """
        GET /api/admin/berita saat tidak ada berita harus mengembalikan list kosong [].

        Requirements: 5.2
        """
        tc, _ = client
        resp = tc.get("/api/admin/berita", headers=ADMIN_HEADERS)
        assert resp.status_code == 200
        assert resp.json() == [], f"Expected [], got {resp.json()}"

    def test_cari_empty_db_returns_not_found(self, client):
        """
        POST /api/cari dengan gambar valid tetapi DB kosong harus mengembalikan
        {"ditemukan": false, "hasil": []}.

        Requirements: 6.4, 6.5
        """
        tc, _ = client
        resp = tc.post(
            "/api/cari",
            files={"file": ("gambar.jpg", _make_jpeg_bytes(), "image/jpeg")},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["ditemukan"] is False
        assert body["hasil"] == []

    def test_cari_skips_news_without_photo_hash_or_pdf_file(self, client):
        """Berita tanpa foto/hash/PDF yang tersedia diabaikan, bukan HTTP 500."""
        tc, db_file = client
        conn = sqlite3.connect(db_file)
        conn.execute(
            "INSERT INTO berita (judul, tanggal, foto_file, pdf_file, phash, dhash) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("Tanpa foto", "2024-01-01", "", "ada.pdf", "", ""),
        )
        conn.execute(
            "INSERT INTO berita (judul, tanggal, foto_file, pdf_file, phash, dhash) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("Foto hilang", "2024-01-02", "hilang.jpg", "ada.pdf", "a" * 64, "a" * 64),
        )
        conn.execute(
            "INSERT INTO berita (judul, tanggal, foto_file, pdf_file, phash, dhash) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("Dokumen valid", "2024-01-03", "tersedia.jpg", "tersedia.pdf", "a" * 64, "a" * 64),
        )
        conn.commit()
        conn.close()

        (main.FOTO_DIR / "tersedia.jpg").write_bytes(_make_jpeg_bytes())
        (main.PDF_DIR / "tersedia.pdf").write_bytes(_make_pdf_bytes())

        with patch("main.matcher.compute_hashes", return_value=("a" * 64, "a" * 64)):
            resp = tc.post(
                "/api/cari",
                files={"file": ("gambar.jpg", _make_jpeg_bytes(), "image/jpeg")},
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ditemukan"] is True
        assert len(body["hasil"]) == 1
        assert body["hasil"][0]["judul"] == "Dokumen valid"
        assert body["hasil"][0]["foto_url"] == "/files/foto/tersedia.jpg"
        assert body["hasil"][0]["pdf_url"] == "/files/pdf/tersedia.pdf"

    def test_cari_results_capped_at_three(self, client):
        """
        POST /api/cari harus mengembalikan maksimal 3 hasil meskipun ada lebih banyak
        berita yang cocok.

        Requirements: 6.4
        """
        tc, db_file = client

        # Masukkan 5 berita dengan hash yang identik (score 0 semuanya)
        conn = sqlite3.connect(db_file)
        # Hash dummy 64-char; gambar query nanti juga akan menghasilkan hash yang
        # berbeda, tapi semuanya akan di-return dengan score rendah
        # — yang penting kita verifikasi batas 3.
        # Masukkan berita dengan hash yang persis identik satu sama lain:
        hash_val = "a" * 64
        for i in range(5):
            (main.FOTO_DIR / f"foto{i}.jpg").write_bytes(_make_jpeg_bytes())
            (main.PDF_DIR / f"pdf{i}.pdf").write_bytes(_make_pdf_bytes())
            conn.execute(
                "INSERT INTO berita (judul, tanggal, foto_file, pdf_file, phash, dhash) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (f"Berita {i+1}", f"2024-0{(i % 9) + 1}-01", f"foto{i}.jpg", f"pdf{i}.pdf",
                 hash_val, hash_val),
            )
        conn.commit()
        conn.close()

        with patch("main.matcher.compute_hashes", return_value=(hash_val, hash_val)):
            resp = tc.post(
                "/api/cari",
                files={"file": ("gambar.jpg", _make_jpeg_bytes(), "image/jpeg")},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["hasil"]) <= 3, (
            f"Jumlah hasil melebihi 3: {len(body['hasil'])}"
        )

    def test_cari_results_sorted_ascending_by_score(self, client):
        """
        Hasil dari POST /api/cari harus terurut ascending berdasarkan score.

        Requirements: 6.4
        """
        tc, db_file = client

        # Masukkan beberapa berita dengan hash yang bervariasi
        conn = sqlite3.connect(db_file)
        for i in range(3):
            hash_val = "a" * 64
            (main.FOTO_DIR / f"foto{i}.jpg").write_bytes(_make_jpeg_bytes())
            (main.PDF_DIR / f"pdf{i}.pdf").write_bytes(_make_pdf_bytes())
            conn.execute(
                "INSERT INTO berita (judul, tanggal, foto_file, pdf_file, phash, dhash) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (f"Berita {i+1}", "2024-01-01", f"foto{i}.jpg", f"pdf{i}.pdf",
                 hash_val, hash_val),
            )
        conn.commit()
        conn.close()

        with patch("main.matcher.compute_hashes", return_value=("a" * 64, "a" * 64)):
            resp = tc.post(
                "/api/cari",
                files={"file": ("gambar.jpg", _make_jpeg_bytes(), "image/jpeg")},
            )
        assert resp.status_code == 200
        scores = [item["score"] for item in resp.json()["hasil"]]
        assert scores == sorted(scores), f"Hasil tidak terurut ascending: {scores}"


# ---------------------------------------------------------------------------
# 3. Error Handling — DB Failures
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """
    Mock DB failures dan verifikasi kode HTTP yang benar.

    Requirements: 5.4 (GET admin → 500), 6.8 (cari → 503)
    """

    def test_cari_db_failure_returns_503(self, client):
        """
        Mock DB failure saat POST /api/cari → harus mengembalikan HTTP 503.

        Requirements: 6.8
        """
        tc, db_file = client

        # Patch get_connection agar melempar exception saat dipanggil
        with patch.object(
            database,
            "get_connection",
            side_effect=Exception("Simulasi DB tidak dapat diakses"),
        ):
            resp = tc.post(
                "/api/cari",
                files={"file": ("gambar.jpg", _make_jpeg_bytes(), "image/jpeg")},
            )

        assert resp.status_code == 503, f"Expected 503, got {resp.status_code}: {resp.text}"
        assert "detail" in resp.json()

    def test_get_admin_berita_db_failure_returns_500(self, client):
        """
        Mock DB failure saat GET /api/admin/berita → harus mengembalikan HTTP 500.

        Requirements: 5.4
        """
        tc, _ = client

        with patch.object(
            database,
            "get_connection",
            side_effect=Exception("Simulasi DB tidak dapat diakses"),
        ):
            resp = tc.get("/api/admin/berita", headers=ADMIN_HEADERS)

        assert resp.status_code == 500, f"Expected 500, got {resp.status_code}: {resp.text}"
        assert "detail" in resp.json()

    def test_cari_tmp_file_cleaned_even_on_db_failure(self, client):
        """
        Saat DB failure pada POST /api/cari, tmp file tetap harus dihapus sebelum
        respons dikembalikan (tidak ada sisa file tmp_* di uploads/tmp/).

        Requirements: 6.8, 9.1, 9.2
        """
        tc, _ = client

        # Pastikan uploads/tmp ada
        os.makedirs("uploads/tmp", exist_ok=True)
        before = set(os.listdir("uploads/tmp"))

        with patch.object(
            database,
            "get_connection",
            side_effect=Exception("Simulasi DB tidak dapat diakses"),
        ):
            tc.post(
                "/api/cari",
                files={"file": ("gambar.jpg", _make_jpeg_bytes(), "image/jpeg")},
            )

        after = set(os.listdir("uploads/tmp"))
        tmp_files = [f for f in after - before if f.startswith("tmp_")]
        assert len(tmp_files) == 0, (
            f"Ditemukan file tmp_ yang tidak terhapus: {tmp_files}"
        )


# ---------------------------------------------------------------------------
# 4. File Deletion Failure on DELETE
# ---------------------------------------------------------------------------


class TestFileDeletionFailure:
    """
    Mock os.remove agar melempar OSError saat DELETE /api/admin/berita/{id}.
    Server harus tetap mengembalikan HTTP 200.

    Requirements: 4.4
    """

    def test_delete_returns_200_when_file_removal_fails(self, client):
        """
        DELETE /api/admin/berita/{id} harus tetap 200 meskipun penghapusan file
        foto dan PDF dari disk gagal (os.remove melempar OSError).

        Requirements: 4.4
        """
        tc, _ = client

        # Tambah berita terlebih dahulu
        add_resp = _post_berita(tc, judul="Berita File Gagal Hapus")
        assert add_resp.status_code == 201, f"Setup gagal: {add_resp.text}"
        berita_id = add_resp.json()["id"]

        # Patch os.remove di modul main agar selalu raise OSError
        with patch("main.os.remove", side_effect=OSError("Simulasi disk error")):
            del_resp = tc.delete(f"/api/admin/berita/{berita_id}", headers=ADMIN_HEADERS)

        assert del_resp.status_code == 200, (
            f"Expected 200 meski os.remove gagal, got {del_resp.status_code}: {del_resp.text}"
        )
        assert "dihapus" in del_resp.json().get("message", "").lower()

    def test_delete_removes_record_from_db_even_if_file_removal_fails(self, client):
        """
        Saat os.remove gagal, baris berita di DB tetap harus terhapus.

        Requirements: 4.1, 4.4
        """
        tc, _ = client

        add_resp = _post_berita(tc, judul="Berita DB Terhapus Meski File Gagal")
        assert add_resp.status_code == 201
        berita_id = add_resp.json()["id"]

        with patch("main.os.remove", side_effect=OSError("Simulasi disk error")):
            del_resp = tc.delete(f"/api/admin/berita/{berita_id}", headers=ADMIN_HEADERS)

        assert del_resp.status_code == 200

        # Verifikasi baris sudah hilang dari DB via GET list
        list_resp = tc.get("/api/admin/berita", headers=ADMIN_HEADERS)
        assert list_resp.status_code == 200
        ids = [item["id"] for item in list_resp.json()]
        assert berita_id not in ids, (
            "Baris berita masih ada di DB meskipun DELETE mengembalikan 200"
        )

    def test_delete_returns_200_when_only_foto_removal_fails(self, client):
        """
        DELETE tetap 200 ketika hanya penghapusan foto yang gagal (PDF berhasil).

        Requirements: 4.4
        """
        tc, _ = client

        add_resp = _post_berita(tc, judul="Berita Foto Gagal Hapus")
        assert add_resp.status_code == 201
        berita_id = add_resp.json()["id"]

        original_remove = os.remove
        call_count = {"n": 0}

        def fail_first_then_succeed(path):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise OSError("Gagal hapus foto")
            original_remove(path)

        with patch("main.os.remove", side_effect=fail_first_then_succeed):
            del_resp = tc.delete(f"/api/admin/berita/{berita_id}", headers=ADMIN_HEADERS)

        assert del_resp.status_code == 200


# ---------------------------------------------------------------------------
# 5. Authentication sanity checks (minimal — full coverage in test_api_happy_path.py)
# ---------------------------------------------------------------------------


class TestAuthSanity:
    """Sanity check autentikasi untuk memastikan endpoint admin terlindungi."""

    def test_get_list_without_key_returns_403(self, client):
        """GET /api/admin/berita tanpa header x-admin-key harus 403."""
        tc, _ = client
        resp = tc.get("/api/admin/berita")
        assert resp.status_code == 403

    def test_delete_without_key_returns_403(self, client):
        """DELETE /api/admin/berita/{id} tanpa header x-admin-key harus 403."""
        tc, _ = client
        resp = tc.delete("/api/admin/berita/1")
        assert resp.status_code == 403
