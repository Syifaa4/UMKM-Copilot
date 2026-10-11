# UMKM Copilot — Kontrak API (Backend Django REST Framework) — v2

Sumber: kode backend (`config/urls.py`, `apps/pesanan/*`, `apps/umkm/*`, `settings.py`).
Tanda **[BELUM TERVERIFIKASI]** = belum diperiksa langsung; jangan diasumsikan oleh frontend.

Base URL (dev): `http://127.0.0.1:8000` (frontend memakai proxy Vite `/api` → Django).

---

## 1. Autentikasi

Autentikasi: `TokenAuthentication` (terkonfirmasi di `REST_FRAMEWORK` settings.py).
Header untuk semua endpoint yang butuh login:
```
Authorization: Token <token>
```
Semua endpoint pesanan/katalog/memori memerlukan login **dan** keanggotaan UMKM aktif.
Data selalu dibatasi ke UMKM milik pengguna. Data UMKM lain → **404**.
`umkm_id` TIDAK pernah dikirim oleh klien.

### 1.1 Login — `POST /api/auth/token/`
```json
{ "username": "...", "password": "..." }
```
Sukses **200**: `{ "token": "..." }`
Gagal **400**: `{ "non_field_errors": ["Unable to log in with provided credentials."] }`
(Frontend menampilkan pesan sendiri: "Username atau password salah.")

### 1.2 Daftar — `POST /api/auth/daftar/` (BARU, publik, tanpa token)
Membuat akun + UMKM baru + keanggotaan (peran `pemilik`) + token + salinan katalog contoh,
semuanya dalam satu transaksi (gagal sebagian = tidak ada yang tersimpan).

Request:
```json
{
  "username": "string, wajib, maks 150, huruf/angka/@.+-_ saja, unik (tidak peka huruf besar/kecil)",
  "password": "string, wajib, divalidasi aturan password Django (min 8, tidak terlalu umum, tidak numerik semua, tidak mirip username)",
  "nama_umkm": "string, wajib, maks 100",
  "email": "string, opsional, format email"
}
```
Sukses **201**:
```json
{
  "token": "...",
  "username": "budi",
  "umkm": { "id": "U3FA91C0B", "nama": "Toko Budi" },
  "katalog_contoh": 20
}
```
- Token langsung bisa dipakai; frontend dapat langsung masuk tanpa login ulang.
- `katalog_contoh` = jumlah produk contoh yang disalin ke UMKM baru (0 jika templat tidak tersedia).

Error:
| Kode | Penyebab | Bentuk body |
|---|---|---|
| 400 | Validasi gagal | `{ "username": ["..."], "password": ["...", "..."], "nama_umkm": ["..."], "email": ["..."] }` — daftar pesan per field |
| 429 | Lebih dari 10 pendaftaran/jam dari satu alamat IP | `{ "detail": "..." }` |

Catatan UI: pesan error password bisa lebih dari satu; tampilkan semuanya.
Pesan dari backend berbahasa Inggris (bawaan Django) — tampilkan apa adanya atau petakan ke Indonesia di frontend.

---

## 2. Pesanan — `/api/pesanan/pesanan/`

### Status pesanan
`DRAFT → MENUNGGU_REVIEW → DIKONFIRMASI → SELESAI`, dan `DIBATALKAN`.

| Metode | URL | Fungsi | Body |
|---|---|---|---|
| GET | `/api/pesanan/pesanan/` | Daftar pesanan (paginasi) | – |
| POST | `/api/pesanan/pesanan/` | Buat pesanan baru (DRAFT) | 2.2 |
| GET | `/api/pesanan/pesanan/{id}/` | Detail | – |
| POST | `/api/pesanan/pesanan/{id}/proses-langflow/` | Proses teks chat dengan AI | – |
| PATCH | `/api/pesanan/pesanan/{id}/items/{item_id}/verifikasi/` | Operator memilih produk untuk satu item | 2.4 |
| POST | `/api/pesanan/pesanan/{id}/ajukan-review/` | DRAFT → MENUNGGU_REVIEW | – |
| POST | `/api/pesanan/pesanan/{id}/konfirmasi/` | MENUNGGU_REVIEW → DIKONFIRMASI | – |
| POST | `/api/pesanan/pesanan/{id}/selesai/` | DIKONFIRMASI → SELESAI | – |
| POST | `/api/pesanan/pesanan/{id}/batalkan/` | → DIBATALKAN | – |

### 2.1 Daftar (GET)
Query: `status` (opsional, nilai tidak valid diabaikan), `page`, `page_size` (default 20, maks 100).
Urutan: terbaru dulu. Response paginasi DRF:
```json
{ "count": 0, "next": null, "previous": null, "results": [ /* Pesanan */ ] }
```

### 2.2 Buat pesanan (POST)
```json
{ "nama_pelanggan": "wajib, maks 200", "teks_chat_asli": "wajib", "catatan": "opsional" }
```
**201** + objek Pesanan. Error: **403** `{"detail": "Tidak ada keanggotaan UMKM aktif."}`, **400** per-field.

### 2.3 Proses dengan AI (POST `.../proses-langflow/`)
Tanpa body. Hanya untuk DRAFT. Harga diambil dari database, bukan dari AI.
Sukses **200** + objek Pesanan (status `MENUNGGU_REVIEW`, `item_pesanan` terisi).

| Kode | Penyebab | Body |
|---|---|---|
| 400 | Status/aturan bisnis tidak terpenuhi (mis. pesanan sudah punya item) | `{"detail": "..."}` |
| 502 | Langflow gagal | `{"detail": "Gagal menghubungi layanan AI. Coba lagi nanti."}` |
| 504 | Langflow timeout (batas 60 detik) | `{"detail": "Langflow tidak merespons. Coba lagi beberapa saat."}` |

UI: tampilkan loading yang jelas (bisa ~60 detik), nonaktifkan tombol selama menunggu.

### 2.4 Verifikasi item (PATCH)
```json
{ "produk_id": 1, "kuantitas": 2 }
```
`produk_id` wajib dan harus milik UMKM pengguna (kalau tidak **404**); `kuantitas` integer ≥ 1.
Sukses **200** + objek Pesanan lengkap. Error **400** `{"detail": "..."}`.

### 2.5 Objek Pesanan
```json
{
  "id": 1, "umkm_id": "U001", "nomor_pesanan": "ORD-...", "nama_pelanggan": "...",
  "teks_chat_asli": "...", "status": "MENUNGGU_REVIEW", "catatan": "",
  "item_pesanan": [ /* Item */ ], "dibuat_pada": "...", "diperbarui_pada": "..."
}
```

### 2.6 Objek Item
```json
{
  "id": 1, "produk": 12, "teks_asli": "...", "nama_ditafsirkan": "...",
  "kuantitas": 2, "harga_satuan": "70000.00", "subtotal": "140000.00",
  "hpp_snapshot": null, "status_item": "DITEMUKAN", "catatan_validasi": "..."
}
```
- `produk` = ID angka atau `null` (bukan objek). Nama produk resmi dari endpoint katalog.
- `harga_satuan`, `subtotal` = string desimal. Format untuk tampilan; jangan dijumlah sebagai float.
- `status_item`: `DITEMUKAN`, `AMBIGU`, `TIDAK_DITEMUKAN`, dan `DIKONFIRMASI` (setelah verifikasi operator).

---

## 3. Katalog dan Memori (hanya baca)
| Metode | URL |
|---|---|
| GET | `/api/katalog/produk/` (paginasi) |
| GET | `/api/katalog/produk/{id}/` |
| GET | `/api/memori/memori/` (hanya status DISETUJUI) |
| GET | `/api/memori/memori/{id}/` |

Field produk/memori: **[BELUM TERVERIFIKASI]** — cek satu respons nyata sebelum membuat UI-nya.
Katalog tidak bisa ditambah/diedit lewat API.

---

## 4. Format error
- Aturan bisnis: `{"detail": "pesan"}` (400/403/404/502/504, dan 429 untuk throttle).
- Validasi serializer (400): objek per field, nilai berupa array pesan.
- Token tidak ada/salah: 401 `{"detail": "..."}` (bawaan DRF).

---

## 5. Aturan untuk IBM Bob
- Gunakan **hanya** endpoint di dokumen ini. Jangan membuat endpoint baru.
- **Jangan mengubah folder `backend/`.** Jika butuh perubahan backend, berhenti dan laporkan.
- Jangan menaruh secret atau API key di kode frontend. Hanya token pengguna di penyimpanan browser.
- Item `AMBIGU` / `TIDAK_DITEMUKAN` harus tampil menonjol dengan aksi "Verifikasi".
- "Konfirmasi" hanya aktif untuk status `MENUNGGU_REVIEW`.
- Jangan menghitung harga/total sendiri; tampilkan nilai dari API.
- Perintah yang menulis file atau memasang paket → minta persetujuan manusia satu per satu.
