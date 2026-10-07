# Implementation Plan: Aplikasi Pencari Berita dari Gambar

## Overview

Implementasi dilakukan secara incremental dari lapisan bawah ke atas: konfigurasi proyek → modul inti (database, matcher) → backend API (main.py) → frontend (HTML/CSS/JS) → pengujian property-based dan integrasi. Setiap langkah menghasilkan kode yang bisa langsung diintegrasikan ke langkah berikutnya.

## Tasks

- [x] 1. Buat struktur proyek dan konfigurasi dependensi
  - Buat file `requirements.txt` berisi: `fastapi`, `uvicorn[standard]`, `python-multipart`, `pillow`, `imagehash`, `pytest`, `hypothesis`, `httpx`
  - Buat folder `static/css/`, `static/js/`, `uploads/foto/`, `uploads/pdf/`, `uploads/tmp/`, `tests/` dengan file `.gitkeep` di masing-masing folder uploads
  - Buat file `tests/__init__.py` kosong agar pytest mengenali direktori test
  - _Requirements: 11.4, 11.7_

- [x] 2. Implementasi modul `database.py`
  - [x] 2.1 Tulis fungsi `get_connection()` dan `init_db()`
    - Implementasi `get_connection()` yang mengembalikan `sqlite3.Connection` dengan `row_factory=sqlite3.Row` ke file `berita.db`
    - Implementasi `init_db()` menggunakan `CREATE TABLE IF NOT EXISTS` dengan skema lengkap (id, judul, tanggal, foto_file, pdf_file, phash 64-char, dhash 64-char)
    - _Requirements: 1.1, 1.2, 11.2_
  - [x] 2.2 Tulis property test untuk idempotence `init_db()`
    - **Property 1: Idempotence Inisialisasi Database**
    - Panggil `init_db()` dua kali atau lebih pada database yang sama, verifikasi skema tabel identik dan data tidak hilang
    - Anotasi: `# Feature: news-finder-from-image, Property 1`
    - **Validates: Requirements 1.2**

- [x] 3. Implementasi modul `matcher.py`
  - [x] 3.1 Tulis fungsi `compute_hashes()`, `hamming_distance()`, dan `similarity_score()`
    - Implementasi `compute_hashes(image_path)` menggunakan `imagehash.phash` dan `imagehash.dhash` dengan `hash_size=16`, kembalikan tuple `(phash_hex, dhash_hex)` sebagai string hex 64 karakter lowercase
    - Implementasi `hamming_distance(hash_a, hash_b)` yang mengembalikan integer dalam `[0, 128]`
    - Implementasi `similarity_score(phash_a, dhash_a, phash_b, dhash_b)` sebagai penjumlahan dua hamming distance, hasil dalam `[0, 256]`
    - Raise `ValueError` jika file tidak bisa dibuka sebagai gambar
    - _Requirements: 3.7, 3.8, 6.2, 11.3_
  - [x] 3.2 Tulis property test untuk `compute_hashes()` (Property 4)
    - **Property 4: Validasi Format Hash**
    - Untuk sembarang file gambar valid (JPEG/PNG), `compute_hashes()` harus menghasilkan tuple dengan kedua string berupa hex lowercase 64 karakter
    - Anotasi: `# Feature: news-finder-from-image, Property 4`
    - **Validates: Requirements 3.7, 3.8**
  - [x] 3.3 Tulis property test untuk `similarity_score()` (Property 5)
    - **Property 5: Similarity Score dalam Rentang Valid**
    - Untuk sembarang 4 string hex 64-char, `similarity_score()` harus menghasilkan nilai dalam `[0, 256]` dan bersifat komutatif: `score(A,B) == score(B,A)`
    - Anotasi: `# Feature: news-finder-from-image, Property 5`
    - **Validates: Requirements 6.2**

- [x] 4. Checkpoint — Verifikasi modul inti
  - Pastikan semua tes di `tests/test_matcher.py` lulus, tanyakan kepada pengguna jika ada pertanyaan.

- [x] 5. Implementasi `main.py` — Setup awal, konstanta, dan startup
  - [x] 5.1 Tulis konstanta, startup event, dan static mounts
    - Definisikan `MAX_JARAK = 80` dan baca `ADMIN_KEY` dari environment tanpa nilai default; nonaktifkan endpoint admin jika tidak tersedia
    - Implementasi startup event: buat folder `uploads/foto/`, `uploads/pdf/`, `uploads/tmp/` jika belum ada; hapus semua file dengan pola `tmp_*` di `uploads/tmp/`
    - Mount `StaticFiles` untuk `/files/foto` → `uploads/foto` dan `/files/pdf` → `uploads/pdf`
    - Mount `StaticFiles` untuk `/` (HTML) dan route `GET /admin`
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 11.1_
  - [ ]* 5.2 Tulis property test untuk startup cleanup (Property 2)
    - **Property 2: Cleanup File Tmp Saat Startup**
    - Buat sejumlah file `tmp_*` di folder tmp, jalankan fungsi cleanup, verifikasi tidak ada `tmp_*` tersisa
    - Anotasi: `# Feature: news-finder-from-image, Property 2`
    - **Validates: Requirements 1.4**

- [x] 6. Implementasi `main.py` — Dependency autentikasi admin
  - [x] 6.1 Tulis dependency `verify_admin_key`
    - Implementasi `async def verify_admin_key(x_admin_key: Optional[str] = Header(default=None))` yang raise `HTTPException(403)` jika header tidak ada atau tidak cocok dengan `ADMIN_KEY`
    - Gunakan perbandingan case-sensitive exact match
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  - [ ]* 6.2 Tulis property test untuk autentikasi (Property 3)
    - **Property 3: Auth Gagal untuk Semua Non-Key**
    - Untuk sembarang string yang tidak sama persis dengan `ADMIN_KEY`, semua endpoint admin harus mengembalikan HTTP 403
    - Anotasi: `# Feature: news-finder-from-image, Property 3`
    - **Validates: Requirements 2.3, 2.5**

- [x] 7. Implementasi `main.py` — Endpoint pencarian `POST /api/cari`
  - [x] 7.1 Tulis handler `POST /api/cari`
    - Validasi MIME type file (hanya `image/jpeg`, `image/png`, `image/webp`); tolak dengan HTTP 400 sebelum membuat tmp file jika tidak valid
    - Simpan ke `uploads/tmp/tmp_<uuid4>` dalam blok `try/finally` untuk jaminan penghapusan
    - Panggil `matcher.compute_hashes()`; tangani `ValueError` → HTTP 400 + hapus tmp
    - Query semua berita dari DB, hitung `similarity_score` per berita
    - Filter `score <= MAX_JARAK`, urutkan ascending, ambil top 3
    - Kembalikan `{"ditemukan": bool, "hasil": [...]}` dengan field `score`, `foto_url`, `pdf_url`
    - Tangani DB tidak dapat diakses → HTTP 503
    - Log error jika penghapusan tmp file gagal
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 9.1, 9.2, 9.3, 9.4_
  - [ ]* 7.2 Tulis property test untuk tmp file cleanup (Property 6)
    - **Property 6: Tmp File Selalu Dihapus Setelah Pencarian**
    - Untuk sembarang permintaan POST `/api/cari` (berhasil maupun gagal), verifikasi tidak ada `tmp_*` tersisa setelah respons dikembalikan
    - Anotasi: `# Feature: news-finder-from-image, Property 6`
    - **Validates: Requirements 6.1, 9.1, 9.2**
  - [ ]* 7.3 Tulis property test untuk isolasi storage (Property 7)
    - **Property 7: Gambar Pencarian Tidak Tersimpan di Folder Permanen**
    - Verifikasi isi `uploads/foto/` dan `uploads/pdf/` tidak berubah setelah permintaan pencarian apapun
    - Anotasi: `# Feature: news-finder-from-image, Property 7`
    - **Validates: Requirements 9.4**
  - [ ]* 7.4 Tulis property test untuk penolakan MIME tidak valid (Property 8)
    - **Property 8: Penolakan Format File Tidak Valid pada Pencarian**
    - Untuk sembarang MIME type di luar `{image/jpeg, image/png, image/webp}`, harus HTTP 400 dan tidak boleh ada file baru di `uploads/tmp/`
    - Anotasi: `# Feature: news-finder-from-image, Property 8`
    - **Validates: Requirements 6.7**
  - [ ]* 7.5 Tulis property test untuk hasil terurut (Property 9)
    - **Property 9: Hasil Pencarian Terurut Ascending dan Terbatas 3**
    - Seed DB dengan kumpulan berita, jalankan pencarian, verifikasi jumlah hasil ≤ 3 dan scores dalam urutan ascending
    - Anotasi: `# Feature: news-finder-from-image, Property 9`
    - **Validates: Requirements 6.4**

- [ ] 8. Checkpoint — Verifikasi endpoint pencarian
  - Pastikan semua tes terkait `/api/cari` lulus, tanyakan kepada pengguna jika ada pertanyaan.

- [x] 9. Implementasi `main.py` — Endpoint admin GET dan DELETE
  - [x] 9.1 Tulis handler `GET /api/admin/berita`
    - Query semua berita dengan `ORDER BY tanggal DESC`
    - Kembalikan daftar dengan field: `id`, `judul`, `tanggal`, `foto_url` (`/files/foto/<foto_file>`), `pdf_url` (`/files/pdf/<pdf_file>`)
    - Kembalikan daftar kosong jika tidak ada berita
    - Tangani DB error → HTTP 500
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - [ ]* 9.2 Tulis property test untuk urutan daftar admin (Property 10)
    - **Property 10: Daftar Berita Admin Terurut Descending by Tanggal**
    - Seed DB dengan berita berbagai tanggal, verifikasi respons selalu descending berdasarkan `tanggal`
    - Anotasi: `# Feature: news-finder-from-image, Property 10`
    - **Validates: Requirements 5.1**
  - [x] 9.3 Tulis handler `DELETE /api/admin/berita/{id}`
    - Query berita by id → 404 jika tidak ada
    - Hapus baris dari DB
    - Hapus file foto dan PDF dalam blok `try/except` terpisah; log error jika gagal, tetap return HTTP 200
    - Gunakan dependency `verify_admin_key`
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 10. Implementasi `main.py` — Endpoint admin `POST /api/admin/berita`
  - [x] 10.1 Tulis handler `POST /api/admin/berita`
    - Validasi semua input sebelum menyimpan file apapun: `judul` 1–255 char, `tanggal` format `^\d{4}-\d{2}-\d{2}$`, `foto.content_type` in `{image/jpeg, image/png}`, ukuran foto ≤ 10 MB, `pdf.content_type == "application/pdf"`, ukuran PDF ≤ 30 MB
    - Baca ukuran file via `len(await file.read())` + `await file.seek(0)`
    - Simpan foto ke `uploads/foto/<uuid4>.<ext>` dan PDF ke `uploads/pdf/<uuid4>.pdf`
    - Implementasi atomisitas: gunakan flag `foto_saved`/`pdf_saved`; jika gagal setelah simpan, rollback dengan hapus file yang sudah tersimpan → HTTP 500
    - Panggil `matcher.compute_hashes(foto_path)`, INSERT ke DB, kembalikan HTTP 201
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_
  - [ ]* 10.2 Tulis property test untuk validasi upload admin (Property 11)
    - **Property 11: Validasi Format File Upload Admin**
    - Untuk sembarang file dengan MIME type tidak valid atau ukuran melebihi batas, harus HTTP 400 tanpa menyimpan file ke disk atau DB
    - Anotasi: `# Feature: news-finder-from-image, Property 11`
    - **Validates: Requirements 3.2, 3.3, 3.4, 3.5**

- [x] 11. Checkpoint — Verifikasi semua endpoint backend
  - Pastikan semua tes backend lulus termasuk happy path (tambah → list → hapus), tanyakan kepada pengguna jika ada pertanyaan.

- [x] 12. Implementasi frontend — CSS bersama (`static/css/style.css`)
  - [x] 12.1 Tulis `static/css/style.css` dengan layout responsif
    - Implementasi CSS untuk kedua halaman dengan variabel CSS (`--primary`, `--bg`, dll.)
    - Desktop (≥1024px): tata letak multi-kolom menggunakan CSS Grid atau Flexbox
    - Mobile (<768px): media query untuk tata letak satu kolom, ukuran sentuh minimal 44×44px
    - Gaya untuk komponen: kartu hasil berita, form admin, tabel daftar berita, thumbnail foto, iframe PDF viewer, loading indicator, pesan error/sukses, dialog konfirmasi
    - Semua teks placeholder, label, dan tombol dalam Bahasa Indonesia
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8_

- [x] 13. Implementasi frontend — Halaman Pencarian
  - [x] 13.1 Tulis `static/index.html`
    - Struktur HTML5 dengan `<input type="file" accept="image/jpeg,image/png,image/webp">`, area preview gambar, tombol "Cari", area hasil pencarian, container iframe PDF viewer
    - Semua label, placeholder, dan teks dalam Bahasa Indonesia
    - Link ke `static/css/style.css` dan `static/js/search.js`
    - _Requirements: 7.1, 7.2, 11.5_
  - [x] 13.2 Tulis `static/js/search.js`
    - `handleFileSelect(event)`: validasi format (JPEG/PNG/WebP) dan ukuran ≤ 5 MB; tampilkan pesan validasi Bahasa Indonesia jika tidak valid; tampilkan preview via `FileReader.readAsDataURL`
    - `handleSearch(event)`: cegah jika tidak ada file; bangun `FormData`; kirim `fetch('/api/cari')` dengan `AbortController` timeout 30 detik; tampilkan loading indicator + disable tombol Cari
    - `renderResults(data)`: tampilkan kartu hasil dengan judul, tanggal, score, tombol "Buka PDF"; auto-buka PDF pertama di iframe; tampilkan "Berita tidak ditemukan" jika `ditemukan: false`
    - `openPDF(url)`: set `src` pada elemen iframe
    - Tangani timeout → sembunyikan loading, aktifkan tombol, tampilkan pesan error
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11, 7.12_

- [x] 14. Implementasi frontend — Halaman Admin
  - [x] 14.1 Tulis `static/admin.html`
    - Struktur HTML5 dengan input Admin_Key di bagian atas, form penambahan berita (judul max 255 char, tanggal, input foto JPG/PNG/JPEG max 10MB, input PDF max 30MB), area daftar berita dengan input filter, area pesan status
    - Semua label, placeholder, dan teks dalam Bahasa Indonesia
    - Link ke `static/css/style.css` dan `static/js/admin.js`
    - _Requirements: 8.1, 8.2, 11.6_
  - [x] 14.2 Tulis `static/js/admin.js`
    - `loadBerita()`: `GET /api/admin/berita` dengan header `x-admin-key`, render daftar dengan thumbnail foto, judul, tanggal format DD/MM/YYYY, link PDF, tombol "Hapus"; tampilkan jumlah total; tampilkan "Belum ada berita yang ditambahkan" jika kosong
    - `handleAddBerita(event)`: validasi semua field client-side (tampilkan field kosong); `POST /api/admin/berita` dengan `FormData`; pada sukses: tampilkan pesan sukses, kosongkan form, reload daftar ≤ 2 detik; pada error: tampilkan pesan error, pertahankan isian form
    - `handleDeleteBerita(id, judul)`: tampilkan dialog konfirmasi dengan judul berita; pada konfirmasi: `DELETE /api/admin/berita/{id}` dengan header `x-admin-key`; pada sukses: hapus item dari DOM, perbarui jumlah, tampilkan pesan sukses ≤ 2 detik; pada error: tampilkan pesan error
    - `filterBerita(query)`: filter client-side dengan `toLowerCase().includes()` pada judul; tampilkan pesan jika nol kecocokan
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 8.12, 8.13, 8.14, 8.15, 8.16_

- [x] 15. Tulis integration tests non-property (`tests/test_api.py`)
  - [x]* 15.1 Tulis integration tests happy path dan edge cases
    - Happy path: tambah berita (POST 201) → verifikasi muncul di GET list → hapus (DELETE 200) → verifikasi hilang dari GET list
    - Edge cases: DELETE id tidak ada → 404; GET list saat DB kosong → daftar kosong; POST `/api/cari` tanpa berita di DB → `{"ditemukan": false, "hasil": []}`
    - Error handling: mock DB failure pada `/api/cari` → 503; mock DB failure pada GET admin → 500
    - File deletion failure on DELETE: mock `os.remove` throw error → verifikasi tetap return 200
    - _Requirements: 4.1, 4.2, 4.4, 5.1, 5.2, 6.4, 6.5, 6.8_

- [ ] 16. Final checkpoint — Semua tes lulus
  - Pastikan semua tes (unit, property-based, integration) lulus dengan `pytest tests/` tanpa error, tanyakan kepada pengguna jika ada pertanyaan.

## Notes

- Task bertanda `*` adalah opsional dan dapat dilewati untuk MVP yang lebih cepat
- Setiap task mereferensikan requirement spesifik untuk traceability
- Checkpoint memastikan validasi incremental di setiap fase
- Property tests menggunakan Hypothesis dengan `@settings(max_examples=100)`
- Setiap property test diberi anotasi `# Feature: news-finder-from-image, Property N`
- Atomisitas pada `POST /api/admin/berita` kritis: rollback file jika DB insert gagal
- Pola `try/finally` wajib digunakan pada semua operasi tmp file
- Frontend tidak menggunakan framework JS eksternal — hanya Vanilla JS ES2020+
- Server dijalankan dengan `uvicorn main:app --reload` setelah `pip install -r requirements.txt`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "3.3"] },
    { "id": 3, "tasks": ["5.1", "6.1"] },
    { "id": 4, "tasks": ["5.2", "6.2", "7.1"] },
    { "id": 5, "tasks": ["7.2", "7.3", "7.4", "7.5", "9.1", "9.3"] },
    { "id": 6, "tasks": ["9.2", "10.1"] },
    { "id": 7, "tasks": ["10.2", "12.1"] },
    { "id": 8, "tasks": ["13.1", "14.1"] },
    { "id": 9, "tasks": ["13.2", "14.2"] },
    { "id": 10, "tasks": ["15.1"] }
  ]
}
```
