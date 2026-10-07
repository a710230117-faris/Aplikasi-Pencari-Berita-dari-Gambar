# Requirements Document

## Introduction

"Aplikasi Pencari Berita dari Gambar" (News Finder from Image) adalah sebuah website yang memungkinkan pengguna mengunggah gambar untuk mencari berita yang relevan berdasarkan kemiripan gambar menggunakan teknik perceptual hashing (pHash dan dHash). Aplikasi ini memiliki dua halaman utama: halaman pencarian publik dan halaman admin untuk mengelola data berita. Backend dibangun dengan Python/FastAPI, frontend menggunakan HTML, CSS, dan Vanilla JavaScript, serta SQLite sebagai penyimpanan data.

---

## Glossary

- **Server**: Aplikasi backend FastAPI yang berjalan dengan uvicorn
- **Search_Page**: Halaman publik (`/`) untuk mencari berita dengan mengunggah gambar
- **Admin_Page**: Halaman admin (`/admin`) untuk mengelola data berita
- **Matcher**: Modul Python (`matcher.py`) yang menghitung hash gambar dan jarak kesamaan
- **Database**: Modul Python (`database.py`) yang mengelola koneksi SQLite dan tabel `berita`
- **Admin_Client**: Browser pengguna yang mengakses halaman admin
- **Search_Client**: Browser pengguna yang mengakses halaman pencarian
- **Berita**: Entitas berita yang tersimpan di database, terdiri dari id, judul, tanggal, foto_file, pdf_file, phash, dhash
- **pHash**: Perceptual hash dengan hash_size=16 yang dihitung dari gambar berita
- **dHash**: Difference hash dengan hash_size=16 yang dihitung dari gambar berita
- **Similarity_Score**: Jumlah jarak Hamming pHash dan dHash antara dua gambar (lebih rendah berarti lebih mirip, 0 berarti identik)
- **MAX_JARAK**: Konstanta batas maksimum Similarity_Score untuk dianggap sebagai kecocokan (default: 80)
- **Admin_Key**: Kunci rahasia yang dibaca dari environment variable `ADMIN_KEY`, digunakan untuk mengautentikasi permintaan admin
- **Tmp_File**: File gambar sementara yang disimpan di `uploads/tmp/` dengan pola nama `tmp_<uuid>` selama proses hashing pencarian
- **PDF_Viewer**: Komponen iframe di Search_Page yang menampilkan file PDF hasil pencarian

---

## Requirements

### Requirement 1: Penyimpanan dan Pengelolaan Data Berita

**User Story:** Sebagai admin, saya ingin menyimpan data berita beserta foto dan file PDF-nya, sehingga berita dapat dicari dan diakses oleh pengguna.

#### Acceptance Criteria

1. THE Database SHALL membuat tabel `berita` dengan kolom: id (INTEGER PRIMARY KEY AUTOINCREMENT), judul (TEXT, maksimal 255 karakter), tanggal (TEXT, format YYYY-MM-DD), foto_file (TEXT), pdf_file (TEXT), phash (TEXT, panjang tepat 64 karakter heksadesimal), dhash (TEXT, panjang tepat 64 karakter heksadesimal), jika tabel belum ada saat Server pertama kali dijalankan.
2. IF tabel `berita` sudah ada saat Server dijalankan, THEN THE Database SHALL TIDAK membuat ulang atau mengubah struktur tabel yang sudah ada.
3. THE Server SHALL membuat folder `uploads/foto/`, `uploads/pdf/`, dan `uploads/tmp/` secara otomatis saat startup sebelum menerima request apapun, jika folder-folder tersebut belum ada.
4. WHEN Server melakukan startup, THE Server SHALL menghapus semua file (bukan subdirektori) dengan pola nama `tmp_*` yang ada di dalam folder `uploads/tmp/` sebelum menerima request apapun.
5. WHEN klien mengirimkan HTTP GET ke `/files/foto/{filename}` dan file tersebut ada di folder `uploads/foto/`, THE Server SHALL mengembalikan respons HTTP 200 dengan konten file foto tersebut.
6. WHEN klien mengirimkan HTTP GET ke `/files/foto/{filename}` dan file tersebut tidak ada di folder `uploads/foto/`, THE Server SHALL mengembalikan respons HTTP 404.
7. WHEN klien mengirimkan HTTP GET ke `/files/pdf/{filename}` dan file tersebut ada di folder `uploads/pdf/`, THE Server SHALL mengembalikan respons HTTP 200 dengan konten file PDF tersebut.
8. WHEN klien mengirimkan HTTP GET ke `/files/pdf/{filename}` dan file tersebut tidak ada di folder `uploads/pdf/`, THE Server SHALL mengembalikan respons HTTP 404.
9. WHEN klien mengirimkan HTTP GET ke path apapun yang dimulai dengan `/uploads/tmp/`, THE Server SHALL mengembalikan respons HTTP 404, tanpa mengekspos konten folder `uploads/tmp/`.

---

### Requirement 2: Autentikasi Admin

**User Story:** Sebagai admin, saya ingin endpoint admin dilindungi oleh kunci rahasia, sehingga hanya saya yang dapat mengelola data berita.

#### Acceptance Criteria

1. THE Server SHALL membaca nilai Admin_Key dari environment variable `ADMIN_KEY`; IF environment variable `ADMIN_KEY` tidak diset atau bernilai kosong, THEN THE Server SHALL menonaktifkan endpoint admin dan mengembalikan HTTP 503.
2. WHEN permintaan ke endpoint admin diterima tanpa header `x-admin-key`, THEN THE Server SHALL mengembalikan respons HTTP 403 disertai pesan error yang mengindikasikan autentikasi diperlukan, tanpa memproses permintaan lebih lanjut.
3. WHEN permintaan ke endpoint admin diterima dengan header `x-admin-key` yang nilainya tidak sesuai dengan Admin_Key, THEN THE Server SHALL mengembalikan respons HTTP 403 disertai pesan error yang mengindikasikan kunci tidak valid, tanpa memproses permintaan lebih lanjut.
4. WHEN permintaan ke endpoint admin diterima dengan header `x-admin-key` yang nilainya sesuai dengan Admin_Key, THEN THE Server SHALL memproses permintaan tersebut dan mengembalikan respons sesuai logika endpoint yang dituju.
5. THE Server SHALL melakukan perbandingan nilai header `x-admin-key` terhadap Admin_Key secara case-sensitive dan berbasis kecocokan string penuh (exact match), sehingga nilai yang berbeda kapitalisasi atau mengandung karakter tambahan dianggap tidak valid.

---

### Requirement 3: Penambahan Berita oleh Admin

**User Story:** Sebagai admin, saya ingin menambahkan berita baru melalui form di halaman admin, sehingga berita tersebut tersedia untuk pencarian.

#### Acceptance Criteria

1. WHEN Admin_Client mengirimkan permintaan POST ke `/api/admin/berita` dengan Admin_Key yang valid, judul non-kosong (1–255 karakter), tanggal dalam format YYYY-MM-DD, file foto dengan ukuran ≤ 10 MB dan format JPG, JPEG, atau PNG, serta file PDF dengan ukuran ≤ 30 MB, THE Server SHALL menyimpan foto ke `uploads/foto/`, menyimpan PDF ke `uploads/pdf/`, menghitung pHash dan dHash dari foto, dan menyimpan seluruh metadata Berita ke Database, lalu mengembalikan respons HTTP 201 yang mengonfirmasi keberhasilan penambahan berita.
2. IF file yang diunggah sebagai foto bukan merupakan file dengan format JPG, JPEG, atau PNG, THEN THE Server SHALL mengembalikan respons HTTP 400 dengan pesan error yang mengindikasikan format foto tidak valid, tanpa menyimpan data apapun ke Database atau sistem penyimpanan file.
3. IF file yang diunggah sebagai PDF bukan merupakan file PDF yang valid, THEN THE Server SHALL mengembalikan respons HTTP 400 dengan pesan error yang mengindikasikan format PDF tidak valid, tanpa menyimpan data apapun ke Database atau sistem penyimpanan file.
4. IF ukuran file foto melebihi 10 MB, THEN THE Server SHALL mengembalikan respons HTTP 400 dengan pesan error yang mengindikasikan ukuran foto melebihi batas, tanpa menyimpan data apapun ke Database atau sistem penyimpanan file.
5. IF ukuran file PDF melebihi 30 MB, THEN THE Server SHALL mengembalikan respons HTTP 400 dengan pesan error yang mengindikasikan ukuran PDF melebihi batas, tanpa menyimpan data apapun ke Database atau sistem penyimpanan file.
6. IF Admin_Client mengirimkan permintaan POST ke `/api/admin/berita` dengan judul kosong atau tanggal tidak dalam format YYYY-MM-DD, THEN THE Server SHALL mengembalikan respons HTTP 400 dengan pesan error yang mengindikasikan field mana yang tidak valid, tanpa menyimpan data apapun.
7. THE Matcher SHALL menghitung pHash dengan hash_size=16 dari setiap foto berita yang diunggah.
8. THE Matcher SHALL menghitung dHash dengan hash_size=16 dari setiap foto berita yang diunggah.
9. IF proses penyimpanan file atau penghitungan hash gagal setelah validasi berhasil, THEN THE Server SHALL mengembalikan respons HTTP 500 dengan pesan error yang mengindikasikan kegagalan internal, dan tidak menyimpan metadata Berita yang tidak lengkap ke Database.

---

### Requirement 4: Penghapusan Berita oleh Admin

**User Story:** Sebagai admin, saya ingin menghapus berita yang sudah tidak relevan, sehingga database tetap bersih dan akurat.

#### Acceptance Criteria

1. WHEN Admin_Client mengirimkan permintaan DELETE ke `/api/admin/berita/{id}` dengan Admin_Key yang valid dan id yang ada di Database, THE Server SHALL menghapus baris Berita dari Database, menghapus file foto terkait dari `uploads/foto/`, dan menghapus file PDF terkait dari `uploads/pdf/`, lalu mengembalikan respons HTTP 200.
2. WHEN Admin_Client mengirimkan permintaan DELETE ke `/api/admin/berita/{id}` dengan id yang tidak ada di Database, THEN THE Server SHALL mengembalikan respons HTTP 404 dengan pesan error yang mengindikasikan berita tidak ditemukan, tanpa melakukan perubahan pada Database atau file.
3. WHEN Admin_Client mengirimkan permintaan DELETE ke `/api/admin/berita/{id}` dengan Admin_Key yang tidak valid atau tidak ada, THEN THE Server SHALL mengembalikan respons HTTP 403, tanpa melakukan perubahan pada Database atau file.
4. WHEN baris Berita berhasil dihapus dari Database tetapi penghapusan file foto atau PDF dari disk gagal, THEN THE Server SHALL tetap mengembalikan respons HTTP 200 dan mencatat kegagalan penghapusan file tersebut ke log server.

---

### Requirement 5: Pengambilan Daftar Berita oleh Admin

**User Story:** Sebagai admin, saya ingin melihat semua berita yang telah terdaftar, sehingga saya dapat mengelola koleksi berita.

#### Acceptance Criteria

1. WHEN Admin_Client mengirimkan permintaan GET ke `/api/admin/berita` dengan Admin_Key yang valid, THE Server SHALL mengembalikan daftar semua Berita yang tersimpan di Database dengan status sukses, diurutkan berdasarkan tanggal dari yang terbaru ke yang terlama, dengan field: id, judul, tanggal, foto_url, pdf_url.
2. WHEN tidak ada Berita yang tersimpan di Database, THE Server SHALL mengembalikan daftar kosong dengan status sukses.
3. WHEN Admin_Client mengirimkan permintaan GET ke `/api/admin/berita` dengan Admin_Key yang tidak valid atau tidak ada, THEN THE Server SHALL mengembalikan respons HTTP 403.
4. IF Database tidak dapat diakses saat permintaan GET ke `/api/admin/berita` diproses, THEN THE Server SHALL mengembalikan respons HTTP 500 dengan pesan error yang mengindikasikan kegagalan internal.

---

### Requirement 6: Pencarian Berita Berdasarkan Gambar

**User Story:** Sebagai pengguna, saya ingin mengunggah gambar dan menemukan berita yang relevan, sehingga saya dapat mengakses informasi berita terkait dengan gambar tersebut.

#### Acceptance Criteria

1. WHEN Search_Client mengirimkan permintaan POST ke `/api/cari` dengan file gambar, THE Server SHALL menyimpan file tersebut sebagai Tmp_File di `uploads/tmp/`, menghitung 64-bit pHash dan 64-bit dHash dari Tmp_File, membandingkan hash tersebut dengan semua hash Berita di Database, lalu menghapus Tmp_File.
2. THE Matcher SHALL menghitung Similarity_Score sebagai jumlah jarak Hamming pHash antara gambar pencarian dengan gambar Berita ditambah jarak Hamming dHash antara gambar pencarian dengan gambar Berita, dengan nilai hasil dalam rentang 0–128.
3. WHEN proses hashing Tmp_File gagal (karena file tidak valid atau error lainnya), THE Server SHALL tetap menghapus Tmp_File dan mengembalikan respons HTTP 400 dengan pesan error yang jelas.
4. WHEN hasil pencarian ditemukan (terdapat Berita dengan Similarity_Score kurang dari atau sama dengan MAX_JARAK), THE Server SHALL mengembalikan respons HTTP 200 dengan JSON `{"ditemukan": true, "hasil": [...]}` berisi hingga 3 Berita dengan Similarity_Score terendah, diurutkan secara ascending dari yang paling mirip.
5. WHEN tidak ada Berita yang memiliki Similarity_Score kurang dari atau sama dengan MAX_JARAK, THE Server SHALL mengembalikan respons HTTP 200 dengan JSON `{"ditemukan": false, "hasil": []}`.
6. THE Server SHALL mendefinisikan MAX_JARAK sebagai konstanta integer dengan nilai default 80, dalam rentang valid 0–128, yang mudah diubah di satu tempat dalam kode.
7. IF file yang diunggah ke `/api/cari` bukan merupakan file gambar dengan MIME type image/jpeg, image/png, atau image/webp, THEN THE Server SHALL menolak file sebelum menyimpannya dan mengembalikan respons HTTP 400 dengan pesan error yang jelas.
8. IF Database tidak dapat diakses saat proses perbandingan hash berlangsung, THEN THE Server SHALL menghapus Tmp_File dan mengembalikan respons HTTP 503 dengan pesan error yang jelas.

---

### Requirement 7: Halaman Pencarian (Search Page)

**User Story:** Sebagai pengguna, saya ingin menggunakan halaman pencarian yang intuitif untuk mencari berita dari gambar, sehingga proses pencarian mudah dan cepat.

#### Acceptance Criteria

1. THE Search_Page SHALL menampilkan input unggah gambar dan area pratinjau (preview) gambar yang dipilih.
2. THE Search_Page SHALL menampilkan tombol "Cari" untuk memulai pencarian.
3. WHEN Search_Client memilih file gambar dengan format JPEG, PNG, atau WebP dan ukuran ≤ 5 MB, THE Search_Page SHALL menampilkan pratinjau gambar tersebut sebelum pencarian dilakukan.
4. WHEN Search_Client memilih file dengan format selain JPEG, PNG, atau WebP, THE Search_Page SHALL menampilkan pesan validasi yang menyebutkan format yang didukung dan tidak melanjutkan ke langkah berikutnya.
5. WHEN Search_Client memilih file gambar dengan ukuran lebih dari 5 MB, THE Search_Page SHALL menampilkan pesan validasi yang menyebutkan batas ukuran file dan tidak melanjutkan ke langkah berikutnya.
6. WHEN Search_Client menekan tombol "Cari" tanpa memilih file gambar, THE Search_Page SHALL menampilkan pesan validasi yang meminta pengguna memilih gambar terlebih dahulu dan tidak mengirimkan permintaan ke server.
7. WHILE permintaan pencarian sedang diproses oleh Server, THE Search_Page SHALL menampilkan indikator status loading yang terlihat jelas dan menonaktifkan tombol "Cari" untuk mencegah permintaan duplikat.
8. WHEN hasil pencarian diterima dengan `ditemukan: true`, THE Search_Page SHALL menampilkan 1 hingga 3 kartu hasil yang masing-masing berisi judul, tanggal, Similarity_Score, dan tombol "Buka PDF".
9. WHEN hasil pencarian diterima dengan `ditemukan: false`, THE Search_Page SHALL menyembunyikan hasil sebelumnya (jika ada) dan menampilkan pesan "Berita tidak ditemukan".
10. WHEN Search_Client menekan tombol "Buka PDF" pada salah satu hasil, THE Search_Page SHALL menampilkan file PDF tersebut di dalam komponen PDF_Viewer (iframe) di dalam halaman tanpa membuka tab atau jendela baru.
11. WHEN hasil pencarian berhasil ditampilkan dengan `ditemukan: true`, THE Search_Page SHALL secara otomatis membuka PDF dari hasil dengan Similarity_Score terendah di dalam PDF_Viewer.
12. WHEN permintaan pencarian tidak mendapat respons dalam 30 detik, THE Search_Page SHALL menyembunyikan indikator loading, mengaktifkan kembali tombol "Cari", dan menampilkan pesan error yang meminta pengguna mencoba lagi.

---

### Requirement 8: Halaman Admin (Admin Page)

**User Story:** Sebagai admin, saya ingin menggunakan halaman admin yang lengkap untuk mengelola semua data berita dari satu tempat, sehingga pengelolaan berita efisien.

#### Acceptance Criteria

1. THE Admin_Page SHALL menampilkan input untuk memasukkan Admin_Key di bagian atas halaman, dan Admin_Key tersebut digunakan untuk semua aksi admin di halaman tersebut.
2. THE Admin_Page SHALL menampilkan form penambahan berita dengan field: Judul Berita (teks, maksimal 255 karakter), Tanggal (tanggal, format YYYY-MM-DD), Foto Berita (file gambar, format JPG/JPEG/PNG, maksimal 10 MB), File PDF (format PDF, maksimal 30 MB).
3. WHEN Admin_Client mengisi semua field form dan menekan tombol submit, THE Admin_Page SHALL mengirimkan permintaan POST ke `/api/admin/berita` dengan Admin_Key dari input dan data form.
4. WHEN Admin_Client menekan tombol submit dengan satu atau lebih field form yang belum diisi, THE Admin_Page SHALL menampilkan pesan validasi yang menyebutkan field mana yang kosong dan tidak mengirimkan permintaan ke server.
5. WHEN server mengembalikan respons sukses setelah penambahan berita, THE Admin_Page SHALL menampilkan pesan sukses, mengosongkan form, dan memperbarui daftar berita tanpa reload halaman penuh dalam waktu ≤ 2 detik setelah respons diterima.
6. WHEN server mengembalikan respons error setelah penambahan berita, THE Admin_Page SHALL menampilkan pesan error yang jelas kepada Admin_Client dengan data form tetap terisi sehingga pengguna dapat memperbaiki input.
7. THE Admin_Page SHALL menampilkan daftar semua Berita yang terdaftar, diurutkan dari yang terbaru, dengan thumbnail foto, judul, tanggal dalam format DD/MM/YYYY, dan tautan untuk membuka PDF-nya.
8. THE Admin_Page SHALL menampilkan jumlah total Berita yang terdaftar.
9. WHEN tidak ada Berita yang terdaftar, THE Admin_Page SHALL menampilkan pesan "Belum ada berita yang ditambahkan".
10. THE Admin_Page SHALL menampilkan input pencarian untuk memfilter daftar Berita berdasarkan judul secara client-side menggunakan pencocokan substring case-insensitive.
11. WHEN input pencarian menghasilkan nol kecocokan, THE Admin_Page SHALL menampilkan pesan yang mengindikasikan tidak ada berita yang cocok dengan kata kunci tersebut.
12. THE Admin_Page SHALL menampilkan tombol "Hapus" pada setiap item Berita di daftar.
13. WHEN Admin_Client menekan tombol "Hapus" pada sebuah item Berita, THE Admin_Page SHALL menampilkan dialog konfirmasi yang menyebutkan judul Berita tersebut sebelum mengirimkan permintaan DELETE.
14. WHEN Admin_Client mengkonfirmasi penghapusan, THE Admin_Page SHALL mengirimkan permintaan DELETE ke `/api/admin/berita/{id}` dengan Admin_Key dari input.
15. WHEN server mengembalikan respons sukses setelah penghapusan, THE Admin_Page SHALL menghapus item Berita tersebut dari daftar, memperbarui jumlah total Berita, dan menampilkan pesan sukses dalam waktu ≤ 2 detik, tanpa reload halaman penuh.
16. WHEN server mengembalikan respons error setelah penghapusan, THE Admin_Page SHALL menampilkan pesan error yang jelas kepada Admin_Client dengan daftar Berita tetap tidak berubah.

---

### Requirement 9: Penanganan File Sementara (Tmp_File)

**User Story:** Sebagai pengelola sistem, saya ingin file sementara selalu dibersihkan setelah digunakan, sehingga tidak terjadi penumpukan file yang tidak perlu di server.

#### Acceptance Criteria

1. WHEN Server menerima permintaan pencarian dengan lampiran gambar, THE Server SHALL menyimpan gambar pencarian sebagai Tmp_File dengan nama `tmp_<uuid>` di folder `uploads/tmp/`.
2. WHEN proses hashing Tmp_File selesai (berhasil maupun gagal), THE Server SHALL menghapus Tmp_File dalam waktu ≤ 5 detik setelah proses hashing berakhir, sehingga Tmp_File tidak tersisa di disk terlepas dari hasil hashing.
3. IF penghapusan Tmp_File gagal, THE Server SHALL mencatat nama file dan waktu kegagalan ke log server dan melanjutkan proses tanpa menampilkan error kepada pengguna.
4. THE Server SHALL TIDAK pernah menyimpan gambar pencarian di folder `uploads/foto/` atau `uploads/pdf/`.

---

### Requirement 10: Kompatibilitas dan Desain Responsif

**User Story:** Sebagai pengguna, saya ingin website dapat diakses dengan baik dari berbagai perangkat dan browser, sehingga pengalaman penggunaan konsisten.

#### Acceptance Criteria

1. THE Search_Page SHALL dapat menampilkan elemen, menerima input file, mengirim form, dan menampilkan notifikasi tanpa error visual di versi terbaru Chrome, Firefox, Edge, dan Safari.
2. THE Admin_Page SHALL dapat menampilkan elemen, menerima input file, mengelola data berita, dan menampilkan notifikasi tanpa error visual di versi terbaru Chrome, Firefox, Edge, dan Safari.
3. WHEN Search_Page diakses dari perangkat dengan lebar layar ≥ 1024px, THE Search_Page SHALL menampilkan tata letak multi-kolom tanpa scroll horizontal, dengan elemen yang dapat diklik.
4. WHEN Search_Page diakses dari perangkat dengan lebar layar < 768px, THE Search_Page SHALL menampilkan tata letak satu kolom tanpa scroll horizontal, dengan elemen yang dapat disentuh (touch-friendly).
5. WHEN Admin_Page diakses dari perangkat dengan lebar layar ≥ 1024px, THE Admin_Page SHALL menampilkan tata letak multi-kolom tanpa scroll horizontal, dengan elemen yang dapat diklik.
6. WHEN Admin_Page diakses dari perangkat dengan lebar layar < 768px, THE Admin_Page SHALL menampilkan tata letak satu kolom tanpa scroll horizontal, dengan elemen yang dapat disentuh (touch-friendly).
7. THE Search_Page SHALL menggunakan Bahasa Indonesia untuk seluruh label, tombol, pesan error, dan placeholder input.
8. THE Admin_Page SHALL menggunakan Bahasa Indonesia untuk seluruh label, tombol, pesan error, dan placeholder input.

---

### Requirement 11: Struktur Proyek dan Kode

**User Story:** Sebagai developer, saya ingin kode proyek terorganisasi dengan baik dan mudah di-setup, sehingga pengembangan dan pemeliharaan lebih mudah.

#### Acceptance Criteria

1. THE Server SHALL diimplementasikan dalam satu file `main.py` yang berisi aplikasi FastAPI dan seluruh rute API.
2. THE Database SHALL diimplementasikan dalam file terpisah `database.py` yang berisi koneksi SQLite dan fungsi pembuatan tabel.
3. THE Matcher SHALL diimplementasikan dalam file terpisah `matcher.py` yang berisi fungsi perhitungan hash dan fungsi perhitungan jarak hash.
4. THE Server SHALL menyertakan file `requirements.txt` yang memuat seluruh dependensi berikut: fastapi, uvicorn[standard], python-multipart, pillow, imagehash.
5. THE Search_Page SHALL memuat tepat satu file CSS dari direktori `static/css/` dan tepat satu file JavaScript `static/js/search.js`.
6. THE Admin_Page SHALL memuat tepat satu file CSS dari direktori `static/css/` dan tepat satu file JavaScript `static/js/admin.js`.
7. WHEN developer menjalankan perintah `pip install -r requirements.txt` di dalam virtual environment yang aktif, THE Server SHALL dapat dijalankan dengan perintah `uvicorn main:app --reload` tanpa error.
8. IF file `requirements.txt` tidak ditemukan atau dependensi tidak terpasang, THEN THE Server SHALL menampilkan pesan error yang menginformasikan dependensi yang hilang sebelum proses startup berhenti.
