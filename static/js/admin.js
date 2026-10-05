/**
 * admin.js — Logika halaman Admin Pencari Berita dari Gambar
 * Vanilla JS ES2020+, tanpa dependensi eksternal.
 * Semua teks antarmuka dalam Bahasa Indonesia.
 */

'use strict';

// ---------------------------------------------------------------------------
// Konstanta validasi (sinkron dengan server-side limits)
// ---------------------------------------------------------------------------

const FOTO_MAX_BYTES  = 10 * 1024 * 1024; // 10 MB
const PDF_MAX_BYTES   = 30 * 1024 * 1024; // 30 MB
const FOTO_TYPES      = ['image/jpeg', 'image/png'];
const FOTO_EXTS       = ['.jpg', '.jpeg', '.png'];

// ---------------------------------------------------------------------------
// State modul
// ---------------------------------------------------------------------------

/** Array semua data berita yang terakhir dimuat dari API. */
let daftarBerita = [];

// ---------------------------------------------------------------------------
// Referensi elemen DOM (diambil saat DOMContentLoaded)
// ---------------------------------------------------------------------------

let elAdminKeyInput       = null;
let elBtnMuatBerita       = null;
let elStatusSuccess       = null;
let elStatusSuccessText   = null;
let elStatusError         = null;
let elStatusErrorText     = null;
let elBtnTutupSukses      = null;
let elBtnTutupError       = null;
let elFormTambah          = null;
let elInputJudul          = null;
let elInputTanggal        = null;
let elInputFoto           = null;
let elInputPdf            = null;
let elJudulError          = null;
let elTanggalError        = null;
let elFotoError           = null;
let elPdfError            = null;
let elBtnTambah           = null;
let elInputFilter         = null;
let elJumlahBerita        = null;
let elLoadingDaftar       = null;
let elDaftarBerita        = null;
let elTbodyBerita         = null;
let elPesanKosong         = null;
let elPesanFilterKosong   = null;
let elDialogHapus         = null;
let elDialogHapusJudul    = null;
let elBtnBatalHapus       = null;
let elBtnKonfirmasiHapus  = null;
let elToastContainer      = null;

// ---------------------------------------------------------------------------
// Utilitas tampilan elemen — berbasis class `--visible`
// ---------------------------------------------------------------------------

/**
 * Tampilkan elemen dengan menambahkan class `--visible` pada kelas dasar pertama.
 * Jika tidak ada kelas dasar ditemukan, gunakan style.display sebagai fallback.
 * @param {HTMLElement} el
 */
function showEl(el) {
  if (!el) return;
  const base = Array.from(el.classList).find(c => !c.includes('--'));
  if (base) {
    el.classList.add(`${base}--visible`);
  } else {
    el.style.display = '';
  }
}

/**
 * Sembunyikan elemen dengan menghapus class `--visible`.
 * @param {HTMLElement} el
 */
function hideEl(el) {
  if (!el) return;
  const base = Array.from(el.classList).find(c => !c.includes('--'));
  if (base) {
    el.classList.remove(`${base}--visible`);
  } else {
    el.style.display = 'none';
  }
}

// ---------------------------------------------------------------------------
// Format tanggal YYYY-MM-DD → DD/MM/YYYY
// ---------------------------------------------------------------------------

/**
 * Ubah format ISO date ke format tampilan DD/MM/YYYY.
 * @param {string} isoDate — contoh: "2024-01-15"
 * @returns {string} — contoh: "15/01/2024"
 */
function formatTanggal(isoDate) {
  if (!isoDate) return '-';
  const parts = String(isoDate).split('-');
  if (parts.length !== 3) return isoDate;
  const [yyyy, mm, dd] = parts;
  return `${dd}/${mm}/${yyyy}`;
}

// ---------------------------------------------------------------------------
// Pesan Status Global (alert banner)
// ---------------------------------------------------------------------------

/**
 * Tampilkan pesan status (banner sukses atau error) di area global.
 * @param {string} pesan — teks pesan
 * @param {'sukses'|'error'} tipe
 */
function showMessage(pesan, tipe) {
  // Sembunyikan dulu keduanya
  hideEl(elStatusSuccess);
  hideEl(elStatusError);

  if (tipe === 'sukses') {
    elStatusSuccessText.textContent = pesan;
    showEl(elStatusSuccess);
    elStatusSuccess.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } else {
    elStatusErrorText.textContent = pesan;
    showEl(elStatusError);
    elStatusError.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

function hideMessages() {
  hideEl(elStatusSuccess);
  hideEl(elStatusError);
}

// ---------------------------------------------------------------------------
// Toast notifikasi kecil
// ---------------------------------------------------------------------------

/**
 * Tampilkan toast notifikasi kecil di pojok layar.
 * @param {string} pesan
 * @param {'sukses'|'error'} tipe
 * @param {number} [durasi=4000] — milidetik sebelum otomatis hilang
 */
function showToast(pesan, tipe, durasi = 4000) {
  if (!elToastContainer) return;

  const toast = document.createElement('div');
  toast.className = `toast toast--${tipe === 'sukses' ? 'success' : 'error'}`;
  toast.setAttribute('role', tipe === 'error' ? 'alert' : 'status');
  toast.setAttribute('aria-live', tipe === 'error' ? 'assertive' : 'polite');
  toast.textContent = pesan;

  elToastContainer.appendChild(toast);

  // Paksa reflow agar transisi CSS berjalan
  void toast.offsetWidth;
  toast.classList.add('toast--visible');

  setTimeout(() => {
    toast.classList.remove('toast--visible');
    toast.addEventListener('transitionend', () => toast.remove(), { once: true });
    // Fallback jika transisi tidak terjadi
    setTimeout(() => toast.remove(), 500);
  }, durasi);
}

// ---------------------------------------------------------------------------
// Validasi field-level pada form tambah berita
// ---------------------------------------------------------------------------

/**
 * Tampilkan atau bersihkan pesan error pada satu field form.
 * @param {HTMLElement} elError — span error field
 * @param {HTMLElement} elInput — input yang bersangkutan
 * @param {string|null} pesan — null untuk bersihkan error
 */
function setFieldError(elError, elInput, pesan) {
  if (pesan) {
    elError.textContent = pesan;
    elInput.setAttribute('aria-invalid', 'true');
    elInput.classList.add('form-control--error');
  } else {
    elError.textContent = '';
    elInput.removeAttribute('aria-invalid');
    elInput.classList.remove('form-control--error');
  }
}

function clearAllFieldErrors() {
  setFieldError(elJudulError,   elInputJudul,   null);
  setFieldError(elTanggalError, elInputTanggal, null);
  setFieldError(elFotoError,    elInputFoto,    null);
  setFieldError(elPdfError,     elInputPdf,     null);
}

/**
 * Validasi seluruh form secara client-side.
 * @returns {boolean} true jika valid, false jika ada error
 */
function validateForm() {
  clearAllFieldErrors();
  let valid = true;

  // Judul
  const judul = elInputJudul.value.trim();
  if (!judul) {
    setFieldError(elJudulError, elInputJudul, 'Judul berita tidak boleh kosong.');
    valid = false;
  } else if (judul.length > 255) {
    setFieldError(elJudulError, elInputJudul, 'Judul berita maksimal 255 karakter.');
    valid = false;
  }

  // Tanggal
  const tanggal = elInputTanggal.value.trim();
  if (!tanggal) {
    setFieldError(elTanggalError, elInputTanggal, 'Tanggal tidak boleh kosong.');
    valid = false;
  } else if (!/^\d{4}-\d{2}-\d{2}$/.test(tanggal)) {
    setFieldError(elTanggalError, elInputTanggal, 'Format tanggal harus YYYY-MM-DD.');
    valid = false;
  }

  // Foto
  const fotoFile = elInputFoto.files?.[0] ?? null;
  if (!fotoFile) {
    setFieldError(elFotoError, elInputFoto, 'Foto berita harus dipilih.');
    valid = false;
  } else {
    const ext = fotoFile.name.toLowerCase().slice(fotoFile.name.lastIndexOf('.'));
    const fotoTypeOk = FOTO_TYPES.includes(fotoFile.type) || FOTO_EXTS.includes(ext);
    if (!fotoTypeOk) {
      setFieldError(elFotoError, elInputFoto, 'Format foto tidak valid. Gunakan JPG, JPEG, atau PNG.');
      valid = false;
    } else if (fotoFile.size > FOTO_MAX_BYTES) {
      setFieldError(elFotoError, elInputFoto, 'Ukuran foto melebihi batas maksimum 10 MB.');
      valid = false;
    }
  }

  // PDF
  const pdfFile = elInputPdf.files?.[0] ?? null;
  if (!pdfFile) {
    setFieldError(elPdfError, elInputPdf, 'File PDF harus dipilih.');
    valid = false;
  } else {
    const pdfTypeOk = pdfFile.type === 'application/pdf' ||
                      pdfFile.name.toLowerCase().endsWith('.pdf');
    if (!pdfTypeOk) {
      setFieldError(elPdfError, elInputPdf, 'Format file tidak valid. Hanya file PDF yang diizinkan.');
      valid = false;
    } else if (pdfFile.size > PDF_MAX_BYTES) {
      setFieldError(elPdfError, elInputPdf, 'Ukuran PDF melebihi batas maksimum 30 MB.');
      valid = false;
    }
  }

  return valid;
}

// ---------------------------------------------------------------------------
// updateJumlah — perbarui tampilan jumlah total berita
// ---------------------------------------------------------------------------

/**
 * Perbarui teks di #jumlah-berita berdasarkan panjang daftarBerita saat ini.
 */
function updateJumlah() {
  const n = daftarBerita.length;
  elJumlahBerita.textContent = `${n} berita`;
  elJumlahBerita.setAttribute('aria-label', `Jumlah total berita yang terdaftar: ${n}`);
}

// ---------------------------------------------------------------------------
// renderBeritaItem — bangun satu baris <tr> untuk tabel daftar berita
// ---------------------------------------------------------------------------

/**
 * Buat dan kembalikan elemen <tr> untuk satu item berita.
 * @param {{ id: number, judul: string, tanggal: string, foto_url: string, pdf_url: string }} berita
 * @returns {HTMLTableRowElement}
 */
function renderBeritaItem(berita) {
  const tr = document.createElement('tr');
  tr.dataset.id    = berita.id;
  tr.dataset.judul = berita.judul;

  // --- Kolom Foto (thumbnail) ---
  const tdFoto = document.createElement('td');
  const img = document.createElement('img');
  img.src    = berita.foto_url;
  img.alt    = `Foto berita: ${berita.judul}`;
  img.width  = 80;
  img.height = 60;
  img.loading = 'lazy';
  img.style.objectFit = 'cover';
  img.style.borderRadius = '4px';
  tdFoto.appendChild(img);

  // --- Kolom Judul ---
  const tdJudul = document.createElement('td');
  tdJudul.textContent = berita.judul;

  // --- Kolom Tanggal (format DD/MM/YYYY) ---
  const tdTanggal = document.createElement('td');
  tdTanggal.textContent = formatTanggal(berita.tanggal);

  // --- Kolom PDF (tautan) ---
  const tdPdf = document.createElement('td');
  const linkPdf = document.createElement('a');
  linkPdf.href   = berita.pdf_url;
  linkPdf.target = '_blank';
  linkPdf.rel    = 'noopener noreferrer';
  linkPdf.textContent = 'Buka PDF';
  linkPdf.setAttribute('aria-label', `Buka PDF berita: ${berita.judul}`);
  tdPdf.appendChild(linkPdf);

  // --- Kolom Aksi (tombol Hapus) ---
  const tdAksi = document.createElement('td');
  const btnHapus = document.createElement('button');
  btnHapus.type      = 'button';
  btnHapus.className = 'btn btn--danger btn--sm';
  btnHapus.textContent = 'Hapus';
  btnHapus.setAttribute('aria-label', `Hapus berita: ${berita.judul}`);
  btnHapus.addEventListener('click', () => {
    handleDeleteBerita(berita.id, berita.judul);
  });
  tdAksi.appendChild(btnHapus);

  tr.appendChild(tdFoto);
  tr.appendChild(tdJudul);
  tr.appendChild(tdTanggal);
  tr.appendChild(tdPdf);
  tr.appendChild(tdAksi);

  return tr;
}

// ---------------------------------------------------------------------------
// loadBerita — GET /api/admin/berita dan render daftar
// ---------------------------------------------------------------------------

/**
 * Muat semua berita dari server dan render ke tabel.
 * Menggunakan Admin Key dari #admin-key-input.
 */
async function loadBerita() {
  const adminKey = elAdminKeyInput.value;

  // Tampilkan loading, sembunyikan konten
  showEl(elLoadingDaftar);
  hideEl(elDaftarBerita);
  hideEl(elPesanKosong);
  hideEl(elPesanFilterKosong);
  elInputFilter.value = '';

  try {
    const response = await fetch('/api/admin/berita', {
      method: 'GET',
      headers: { 'x-admin-key': adminKey },
    });

    if (response.status === 403) {
      showMessage('Autentikasi gagal. Periksa Admin Key Anda.', 'error');
      daftarBerita = [];
      updateJumlah();
      return;
    }

    if (!response.ok) {
      let detail = `Gagal memuat berita (HTTP ${response.status}).`;
      try {
        const errData = await response.json();
        if (errData?.detail) detail = errData.detail;
      } catch (_) { /* abaikan */ }
      showMessage(detail, 'error');
      daftarBerita = [];
      updateJumlah();
      return;
    }

    const data = await response.json();
    // API mengembalikan array langsung atau objek dengan field tertentu
    daftarBerita = Array.isArray(data) ? data : (data.data ?? data.berita ?? []);

    renderDaftarBerita();

  } catch (err) {
    showMessage('Gagal terhubung ke server. Periksa koneksi Anda dan coba lagi.', 'error');
    daftarBerita = [];
    updateJumlah();
  } finally {
    hideEl(elLoadingDaftar);
  }
}

/**
 * Render ulang seluruh isi tbody dari daftarBerita.
 * Dipanggil setelah load atau setelah tambah/hapus berhasil.
 */
function renderDaftarBerita() {
  elTbodyBerita.innerHTML = '';

  if (daftarBerita.length === 0) {
    hideEl(elDaftarBerita);
    showEl(elPesanKosong);
    hideEl(elPesanFilterKosong);
  } else {
    daftarBerita.forEach(berita => {
      const tr = renderBeritaItem(berita);
      elTbodyBerita.appendChild(tr);
    });
    showEl(elDaftarBerita);
    hideEl(elPesanKosong);
    hideEl(elPesanFilterKosong);
  }

  updateJumlah();
}

// ---------------------------------------------------------------------------
// filterBerita — filter client-side berdasarkan judul
// ---------------------------------------------------------------------------

/**
 * Tampilkan/sembunyikan baris tabel berdasarkan query pencarian.
 * @param {string} query — kata kunci pencarian
 */
function filterBerita(query) {
  const q = query.toLowerCase().trim();
  const rows = elTbodyBerita.querySelectorAll('tr');
  let jumlahCocok = 0;

  rows.forEach(tr => {
    const judul = (tr.dataset.judul ?? '').toLowerCase();
    const cocok = q === '' || judul.includes(q);
    tr.style.display = cocok ? '' : 'none';
    if (cocok) jumlahCocok++;
  });

  // Tampilkan pesan jika tidak ada hasil filter
  if (q !== '' && jumlahCocok === 0 && daftarBerita.length > 0) {
    hideEl(elDaftarBerita);
    showEl(elPesanFilterKosong);
    hideEl(elPesanKosong);
  } else if (daftarBerita.length === 0) {
    // Daftar memang kosong — biarkan pesan kosong tetap tampil
    showEl(elPesanKosong);
    hideEl(elPesanFilterKosong);
    hideEl(elDaftarBerita);
  } else {
    showEl(elDaftarBerita);
    hideEl(elPesanFilterKosong);
    hideEl(elPesanKosong);
  }
}

// ---------------------------------------------------------------------------
// handleAddBerita — POST /api/admin/berita
// ---------------------------------------------------------------------------

/**
 * Tangani submit form penambahan berita.
 * @param {Event} event — submit event dari form
 */
async function handleAddBerita(event) {
  event.preventDefault();
  hideMessages();

  // Validasi client-side
  if (!validateForm()) {
    // Fokus ke field pertama yang error
    const firstErrorInput = elFormTambah.querySelector('[aria-invalid="true"]');
    if (firstErrorInput) firstErrorInput.focus();
    return;
  }

  const adminKey = elAdminKeyInput.value;

  // Bangun FormData
  const formData = new FormData();
  formData.append('judul',   elInputJudul.value.trim());
  formData.append('tanggal', elInputTanggal.value.trim());
  formData.append('foto',    elInputFoto.files[0]);
  formData.append('pdf',     elInputPdf.files[0]);

  // Nonaktifkan tombol submit selama proses
  elBtnTambah.disabled = true;
  elBtnTambah.textContent = 'Menyimpan…';

  try {
    const response = await fetch('/api/admin/berita', {
      method: 'POST',
      headers: { 'x-admin-key': adminKey },
      body:    formData,
    });

    if (response.ok) {
      // Sukses: kosongkan form, tampilkan pesan, reload daftar
      elFormTambah.reset();
      clearAllFieldErrors();
      showMessage('Berita berhasil ditambahkan.', 'sukses');
      showToast('Berita berhasil ditambahkan.', 'sukses');
      // Reload daftar dalam ≤ 2 detik (langsung reload, sudah ≤ 2 detik)
      await loadBerita();
    } else {
      // Error: tampilkan pesan, pertahankan isian form
      let detail = `Gagal menambahkan berita (HTTP ${response.status}).`;
      try {
        const errData = await response.json();
        if (errData?.detail) detail = errData.detail;
      } catch (_) { /* abaikan */ }
      showMessage(detail, 'error');
      showToast(detail, 'error');
    }

  } catch (err) {
    const pesanErr = 'Gagal terhubung ke server. Periksa koneksi Anda dan coba lagi.';
    showMessage(pesanErr, 'error');
    showToast(pesanErr, 'error');
  } finally {
    elBtnTambah.disabled = false;
    elBtnTambah.textContent = 'Tambah Berita';
  }
}

// ---------------------------------------------------------------------------
// handleDeleteBerita — tampilkan dialog konfirmasi lalu DELETE
// ---------------------------------------------------------------------------

/**
 * Tampilkan dialog konfirmasi hapus dan, jika dikonfirmasi, kirim DELETE.
 * @param {number|string} id — ID berita yang akan dihapus
 * @param {string} judul     — Judul berita untuk ditampilkan di dialog
 */
async function handleDeleteBerita(id, judul) {
  // Isi dialog konfirmasi
  elDialogHapusJudul.textContent = judul;
  elBtnKonfirmasiHapus.dataset.id = id;

  // Tampilkan dialog
  showEl(elDialogHapus);
  elBtnBatalHapus.focus();
}

/**
 * Eksekusi permintaan DELETE setelah pengguna mengkonfirmasi.
 * Dipanggil oleh event listener pada #btn-konfirmasi-hapus.
 * @param {number|string} id
 */
async function eksekusiHapus(id) {
  hideEl(elDialogHapus);
  hideMessages();

  const adminKey = elAdminKeyInput.value;

  try {
    const response = await fetch(`/api/admin/berita/${id}`, {
      method:  'DELETE',
      headers: { 'x-admin-key': adminKey },
    });

    if (response.ok) {
      // Hapus item dari DOM dan dari daftarBerita
      const trTarget = elTbodyBerita.querySelector(`tr[data-id="${id}"]`);
      if (trTarget) trTarget.remove();

      daftarBerita = daftarBerita.filter(b => String(b.id) !== String(id));
      updateJumlah();

      // Tampilkan pesan kosong jika tidak ada item tersisa
      if (daftarBerita.length === 0) {
        hideEl(elDaftarBerita);
        showEl(elPesanKosong);
      }

      showMessage('Berita berhasil dihapus.', 'sukses');
      showToast('Berita berhasil dihapus.', 'sukses');

    } else {
      let detail = `Gagal menghapus berita (HTTP ${response.status}).`;
      try {
        const errData = await response.json();
        if (errData?.detail) detail = errData.detail;
      } catch (_) { /* abaikan */ }
      showMessage(detail, 'error');
      showToast(detail, 'error');
    }

  } catch (err) {
    const pesanErr = 'Gagal terhubung ke server. Periksa koneksi Anda dan coba lagi.';
    showMessage(pesanErr, 'error');
    showToast(pesanErr, 'error');
  }
}

// ---------------------------------------------------------------------------
// init — kabel semua event listener setelah DOM siap
// ---------------------------------------------------------------------------

/**
 * Inisialisasi referensi DOM dan pasang semua event listener.
 * Dipanggil saat DOMContentLoaded.
 */
function init() {
  // Ambil referensi elemen
  elAdminKeyInput       = document.getElementById('admin-key-input');
  elBtnMuatBerita       = document.getElementById('btn-muat-berita');
  elStatusSuccess       = document.getElementById('status-message-success');
  elStatusSuccessText   = document.getElementById('status-message-success-text');
  elStatusError         = document.getElementById('status-message-error');
  elStatusErrorText     = document.getElementById('status-message-error-text');
  elBtnTutupSukses      = document.getElementById('btn-tutup-sukses');
  elBtnTutupError       = document.getElementById('btn-tutup-error');
  elFormTambah          = document.getElementById('form-tambah-berita');
  elInputJudul          = document.getElementById('input-judul');
  elInputTanggal        = document.getElementById('input-tanggal');
  elInputFoto           = document.getElementById('input-foto');
  elInputPdf            = document.getElementById('input-pdf');
  elJudulError          = document.getElementById('judul-error');
  elTanggalError        = document.getElementById('tanggal-error');
  elFotoError           = document.getElementById('foto-error');
  elPdfError            = document.getElementById('pdf-error');
  elBtnTambah           = document.getElementById('btn-tambah-berita');
  elInputFilter         = document.getElementById('input-filter');
  elJumlahBerita        = document.getElementById('jumlah-berita');
  elLoadingDaftar       = document.getElementById('loading-daftar');
  elDaftarBerita        = document.getElementById('daftar-berita');
  elTbodyBerita         = document.getElementById('tbody-berita');
  elPesanKosong         = document.getElementById('pesan-kosong');
  elPesanFilterKosong   = document.getElementById('pesan-filter-kosong');
  elDialogHapus         = document.getElementById('dialog-hapus');
  elDialogHapusJudul    = document.getElementById('dialog-hapus-judul');
  elBtnBatalHapus       = document.getElementById('btn-batal-hapus');
  elBtnKonfirmasiHapus  = document.getElementById('btn-konfirmasi-hapus');
  elToastContainer      = document.getElementById('toast-container');

  // --- Tombol Muat Berita ---
  elBtnMuatBerita.addEventListener('click', () => {
    hideMessages();
    loadBerita();
  });

  // Admin Key: tekan Enter untuk muat berita
  elAdminKeyInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      hideMessages();
      loadBerita();
    }
  });

  // --- Form Tambah Berita ---
  elFormTambah.addEventListener('submit', handleAddBerita);

  // Bersihkan error field saat pengguna mulai mengetik/memilih
  elInputJudul.addEventListener('input', () => {
    setFieldError(elJudulError, elInputJudul, null);
  });
  elInputTanggal.addEventListener('change', () => {
    setFieldError(elTanggalError, elInputTanggal, null);
  });
  elInputFoto.addEventListener('change', () => {
    setFieldError(elFotoError, elInputFoto, null);
  });
  elInputPdf.addEventListener('change', () => {
    setFieldError(elPdfError, elInputPdf, null);
  });

  // --- Tombol tutup pesan status ---
  elBtnTutupSukses.addEventListener('click', () => hideEl(elStatusSuccess));
  elBtnTutupError.addEventListener('click',  () => hideEl(elStatusError));

  // --- Filter daftar berita ---
  elInputFilter.addEventListener('input', (e) => {
    filterBerita(e.target.value);
  });

  // --- Dialog Hapus: tombol Batal ---
  elBtnBatalHapus.addEventListener('click', () => {
    hideEl(elDialogHapus);
  });

  // --- Dialog Hapus: klik pada backdrop (di luar dialog) ---
  elDialogHapus.addEventListener('click', (e) => {
    if (e.target === elDialogHapus) {
      hideEl(elDialogHapus);
    }
  });

  // --- Dialog Hapus: Escape key ---
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const isVisible = elDialogHapus.classList.contains('dialog-backdrop--visible');
      if (isVisible) {
        hideEl(elDialogHapus);
      }
    }
  });

  // --- Dialog Hapus: tombol Konfirmasi ---
  elBtnKonfirmasiHapus.addEventListener('click', async () => {
    const id = elBtnKonfirmasiHapus.dataset.id;
    if (id) {
      await eksekusiHapus(id);
    }
  });
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', init);
