/**
 * search.js — Logika halaman Pencari Berita dari Gambar
 * Vanilla JS ES2020+, tanpa dependensi eksternal.
 */

'use strict';

// ---------------------------------------------------------------------------
// Konstanta
// ---------------------------------------------------------------------------

const ALLOWED_TYPES  = ['image/jpeg', 'image/png', 'image/webp'];
const MAX_FILE_BYTES = 5 * 1024 * 1024; // 5 MB
const API_TIMEOUT_MS = 30_000;          // 30 detik

// ---------------------------------------------------------------------------
// Referensi elemen DOM (diambil sekali saat DOMContentLoaded)
// ---------------------------------------------------------------------------

let fileInput         = null;
let uploadArea        = null;
let previewImage      = null;
let previewContainer  = null;
let previewFilename   = null;
let btnGantiGambar    = null;
let btnHapusGambar    = null;
let btnCari           = null;
let loadingIndicator  = null;
let validationMessage = null;
let validationText    = null;
let errorMessage      = null;
let errorText         = null;
let resultsContainer  = null;
let noResultsContainer = null;
let pdfViewer         = null;
let pdfIframe         = null;
let pdfViewerTitle    = null;
let btnTutupPdf       = null;

/** File yang saat ini dipilih pengguna (File | null). */
let selectedFile = null;
let activeSearchController = null;
let searchRequestId = 0;

// ---------------------------------------------------------------------------
// Helper: tampil / sembunyi elemen via modifier class CSS
// ---------------------------------------------------------------------------

/**
 * Tampilkan elemen dengan menambahkan class `--visible`.
 * @param {HTMLElement} el
 */
function showElement(el) {
  const base = getBaseClass(el);
  if (base) {
    el.classList.add(`${base}--visible`);
  }
}

/**
 * Sembunyikan elemen dengan menghapus class `--visible`.
 * @param {HTMLElement} el
 */
function hideElement(el) {
  const base = getBaseClass(el);
  if (base) {
    el.classList.remove(`${base}--visible`);
  }
}

/**
 * Dapatkan nama kelas dasar elemen (kelas pertama yang bukan modifier).
 * @param {HTMLElement} el
 * @returns {string|null}
 */
function getBaseClass(el) {
  const classes = Array.from(el.classList);
  const base = classes.find(c => !c.includes('--') && !c.includes('hidden'));
  return base || null;
}

// ---------------------------------------------------------------------------
// Helper: pesan validasi & error
// ---------------------------------------------------------------------------

function showValidation(pesan) {
  validationText.textContent = pesan;
  showElement(validationMessage);
}

function hideValidation() {
  hideElement(validationMessage);
  validationText.textContent = '';
}

function showError(pesan) {
  errorText.textContent = pesan;
  showElement(errorMessage);
}

function hideError() {
  hideElement(errorMessage);
  errorText.textContent = '';
}

function clearSelectedImage() {
  cancelActiveSearch();
  selectedFile = null;
  fileInput.value = '';
  previewImage.removeAttribute('src');
  previewFilename.textContent = '';
  previewContainer.classList.remove('preview-container--visible');
  uploadArea.classList.remove('d-none');
  clearResults();
}

function cancelActiveSearch() {
  searchRequestId += 1;
  if (activeSearchController) {
    activeSearchController.abort();
    activeSearchController = null;
  }
  hideElement(loadingIndicator);
  btnCari.disabled = false;
}

// ---------------------------------------------------------------------------
// Format tanggal YYYY-MM-DD → DD/MM/YYYY
// ---------------------------------------------------------------------------

/**
 * @param {string} isoDate — "2024-01-15"
 * @returns {string} — "15/01/2024"
 */
function formatTanggal(isoDate) {
  if (!isoDate) return '-';
  const parts = isoDate.split('-');
  if (parts.length !== 3) return isoDate;
  const [yyyy, mm, dd] = parts;
  return `${dd}/${mm}/${yyyy}`;
}

// ---------------------------------------------------------------------------
// handleFileSelect — validasi & pratinjau file
// ---------------------------------------------------------------------------

/**
 * Dipanggil saat pengguna memilih file melalui input atau drag-and-drop.
 * @param {Event} event — change event dari <input type="file">
 */
function handleFileSelect(event) {
  const file = event.target.files?.[0] ?? null;

  hideValidation();
  hideError();

  if (!file) {
    return;
  }
  cancelActiveSearch();
  clearResults();

  // Validasi format
  if (!ALLOWED_TYPES.includes(file.type)) {
    showValidation('Format file tidak didukung. Harap unggah gambar JPEG, PNG, atau WebP.');
    fileInput.value = '';
    selectedFile = null;
    hideElement(previewContainer);
    uploadArea.classList.remove('d-none');
    return;
  }

  // Validasi ukuran
  if (file.size > MAX_FILE_BYTES) {
    showValidation('Ukuran file melebihi batas maksimum 5 MB. Pilih gambar yang lebih kecil.');
    fileInput.value = '';
    selectedFile = null;
    hideElement(previewContainer);
    uploadArea.classList.remove('d-none');
    return;
  }

  // Tahan pencarian sampai preview selesai dibaca.
  selectedFile = null;
  hideElement(previewContainer);
  uploadArea.classList.remove('d-none');

  // Tampilkan pratinjau via FileReader
  const reader = new FileReader();
  reader.onload = (e) => {
    if (typeof e.target.result !== 'string') {
      showValidation('Gambar tidak dapat ditampilkan. Silakan pilih file lain.');
      selectedFile = null;
      fileInput.value = '';
      previewImage.removeAttribute('src');
      previewFilename.textContent = '';
      return;
    }
    selectedFile = file;
    previewImage.src = e.target.result;
    previewFilename.textContent = file.name;
    showElement(previewContainer);
    uploadArea.classList.add('d-none');
    handleSearch(new Event('submit'));
  };
  reader.onerror = () => {
    showValidation('Gambar tidak dapat dibaca. Silakan pilih file lain.');
    selectedFile = null;
    fileInput.value = '';
    previewImage.removeAttribute('src');
    previewFilename.textContent = '';
    hideElement(previewContainer);
    uploadArea.classList.remove('d-none');
  };
  reader.readAsDataURL(file);
}

// ---------------------------------------------------------------------------
// handleSearch — kirim permintaan pencarian ke API
// ---------------------------------------------------------------------------

/**
 * Dipanggil saat tombol "Cari" diklik.
 * @param {Event} event — click event
 */
async function handleSearch(event) {
  event.preventDefault();

  // Cegah pencarian jika tidak ada file dipilih
  if (!selectedFile) {
    showValidation('Silakan pilih gambar terlebih dahulu sebelum mencari.');
    return;
  }

  if (activeSearchController) {
    activeSearchController.abort();
  }
  const requestId = ++searchRequestId;

  hideValidation();
  hideError();

  // Bersihkan hasil sebelumnya
  clearResults();

  // Tampilkan loading + nonaktifkan tombol
  showElement(loadingIndicator);
  btnCari.disabled = true;

  // Bangun FormData
  const formData = new FormData();
  formData.append('file', selectedFile);

  // AbortController untuk timeout 30 detik
  const controller = new AbortController();
  activeSearchController = controller;
  const timeoutId  = setTimeout(() => controller.abort(), API_TIMEOUT_MS);

  try {
    const response = await fetch('/api/cari', {
      method: 'POST',
      body:   formData,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      let pesanError = `Terjadi kesalahan pada server (HTTP ${response.status}).`;
      try {
        const errData = await response.json();
        if (errData?.detail) {
          const detail = typeof errData.detail === 'string'
            ? errData.detail
            : JSON.stringify(errData.detail);
          pesanError = response.status === 500
            ? `Server mengalami gangguan saat memproses gambar (HTTP 500). ${detail}`
            : `Kesalahan (HTTP ${response.status}): ${detail}`;
        }
      } catch (_) {
        // Abaikan jika respons bukan JSON
      }
      if (response.status === 500 && pesanError === 'Terjadi kesalahan pada server (HTTP 500).') {
        pesanError = 'Server mengalami gangguan saat memproses gambar (HTTP 500). Silakan coba lagi beberapa saat.';
      }
      showError(pesanError);
      return;
    }

    const data = await response.json();
    renderResults(data);

  } catch (err) {
    clearTimeout(timeoutId);

    if (requestId !== searchRequestId) {
      return;
    } else if (err.name === 'AbortError') {
      showError('Permintaan melebihi batas waktu (30 detik). Silakan coba lagi.');
    } else {
      showError('Gagal terhubung ke server. Periksa koneksi internet Anda dan coba lagi.');
    }
  } finally {
    if (requestId === searchRequestId) {
      activeSearchController = null;
      hideElement(loadingIndicator);
      btnCari.disabled = false;
    }
  }
}

// ---------------------------------------------------------------------------
// clearResults — hapus kartu hasil sebelumnya
// ---------------------------------------------------------------------------

function clearResults() {
  resultsContainer.innerHTML = '';
  hideElement(noResultsContainer);
  hideElement(pdfViewer);
  pdfIframe.src = '';
  pdfViewerTitle.textContent = 'Tampilan PDF';
}

// ---------------------------------------------------------------------------
// renderResults — tampilkan kartu hasil
// ---------------------------------------------------------------------------

/**
 * Render kartu hasil pencarian dari respons API.
 * @param {{ ditemukan: boolean, hasil: Array }} data
 */
function renderResults(data) {
  if (!data.ditemukan || !data.hasil || data.hasil.length === 0) {
    showElement(noResultsContainer);
    return;
  }

  // Hasil sudah terurut ascending dari API — tampilkan sesuai urutan
  data.hasil.forEach((item, index) => {
    const card = buildResultCard(item);
    resultsContainer.appendChild(card);

    // Auto-buka PDF pertama di iframe
    if (index === 0) {
      openPDF(item.pdf_url, item.judul);
    }
  });
}

// ---------------------------------------------------------------------------
// buildResultCard — buat elemen kartu HTML untuk satu berita
// ---------------------------------------------------------------------------

/**
 * @param {{ id: number, judul: string, tanggal: string, score: number, foto_url: string, pdf_url: string }} item
 * @returns {HTMLElement}
 */
function buildResultCard(item) {
  const card = document.createElement('article');
  card.className = 'result-card';

  if (item.foto_url) {
    const thumbnail = document.createElement('img');
    thumbnail.className = 'result-card__thumbnail';
    thumbnail.src = item.foto_url;
    thumbnail.alt = `Foto berita: ${item.judul}`;
    thumbnail.loading = 'lazy';
    card.appendChild(thumbnail);
  }

  const body = document.createElement('div');
  body.className = 'result-card__body';

  const judul = document.createElement('h3');
  judul.className = 'result-card__title';
  judul.textContent = item.judul;

  const tanggal = document.createElement('p');
  tanggal.className = 'result-card__date';
  tanggal.textContent = formatTanggal(item.tanggal);

  const score = document.createElement('p');
  score.className = 'result-card__score';
  score.textContent = `Skor: ${Math.round(item.score)}`;

  const btnBukaPdf = document.createElement('button');
  btnBukaPdf.type      = 'button';
  btnBukaPdf.className = 'btn btn--secondary btn--sm';
  btnBukaPdf.textContent = 'Buka PDF';
  btnBukaPdf.setAttribute('aria-label', `Buka PDF: ${item.judul}`);
  btnBukaPdf.addEventListener('click', () => {
    openPDF(item.pdf_url, item.judul);
  });

  body.appendChild(judul);
  body.appendChild(tanggal);
  body.appendChild(score);
  body.appendChild(btnBukaPdf);
  card.appendChild(body);

  return card;
}

// ---------------------------------------------------------------------------
// openPDF — tampilkan PDF di iframe
// ---------------------------------------------------------------------------

/**
 * Muat URL PDF ke dalam elemen iframe dan tampilkan viewer.
 * @param {string} url   — URL file PDF, mis. "/files/pdf/abc.pdf"
 * @param {string} [judul] — Judul berita untuk ditampilkan di header viewer
 */
function openPDF(url, judul = 'Tampilan PDF') {
  pdfIframe.src          = url;
  pdfViewerTitle.textContent = judul;
  showElement(pdfViewer);

  // Scroll ke PDF viewer agar langsung terlihat
  pdfViewer.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ---------------------------------------------------------------------------
// tutupPDF — sembunyikan PDF viewer
// ---------------------------------------------------------------------------

function tutupPDF() {
  hideElement(pdfViewer);
  pdfIframe.src = '';
  pdfViewerTitle.textContent = 'Tampilan PDF';
}

// ---------------------------------------------------------------------------
// Inisialisasi — daftarkan semua event listener setelah DOM siap
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  // Ambil referensi elemen
  fileInput          = document.getElementById('file-input');
  uploadArea         = document.getElementById('upload-area');
  previewImage       = document.getElementById('preview-image');
  previewContainer   = document.getElementById('preview-container');
  previewFilename    = document.getElementById('preview-filename');
  btnGantiGambar     = document.getElementById('btn-ganti-gambar');
  btnHapusGambar     = document.getElementById('btn-hapus-gambar');
  btnCari            = document.getElementById('btn-cari');
  loadingIndicator   = document.getElementById('loading-indicator');
  validationMessage  = document.getElementById('validation-message');
  validationText     = document.getElementById('validation-message-text');
  errorMessage       = document.getElementById('error-message');
  errorText          = document.getElementById('error-message-text');
  resultsContainer   = document.getElementById('results-container');
  noResultsContainer = document.getElementById('no-results-container');
  pdfViewer          = document.getElementById('pdf-viewer');
  pdfIframe          = document.getElementById('pdf-iframe');
  pdfViewerTitle     = document.getElementById('pdf-viewer-title');
  btnTutupPdf        = document.getElementById('btn-tutup-pdf');

  // Klik pada upload-area → delegasikan ke file input
  uploadArea.addEventListener('click', (e) => {
    // Hindari trigger ganda jika input yang diklik
    if (e.target !== fileInput) {
      fileInput.click();
    }
  });

  // Aksesibilitas: Enter/Space pada upload-area berfungsi seperti klik
  uploadArea.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      fileInput.click();
    }
  });

  // Drag-and-drop
  uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('upload-area--dragover');
  });

  uploadArea.addEventListener('dragleave', () => {
    uploadArea.classList.remove('upload-area--dragover');
  });

  uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('upload-area--dragover');
    const files = e.dataTransfer?.files;
    if (files && files.length > 0) {
      // Simulasikan event change dengan file yang di-drop
      const dt  = new DataTransfer();
      dt.items.add(files[0]);
      fileInput.files = dt.files;
      fileInput.dispatchEvent(new Event('change'));
    }
  });

  // Perubahan file input
  fileInput.addEventListener('change', handleFileSelect);
  btnGantiGambar.addEventListener('click', () => {
    fileInput.value = '';
    fileInput.click();
  });
  btnHapusGambar.addEventListener('click', () => {
    clearSelectedImage();
    hideValidation();
    hideError();
  });

  // Tombol Cari
  btnCari.addEventListener('click', handleSearch);

  // Tombol Tutup PDF
  btnTutupPdf.addEventListener('click', tutupPDF);
});
