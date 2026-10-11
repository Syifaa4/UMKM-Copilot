# UMKM Copilot — Kontrak API (Backend Django REST Framework)

Sumber: `config/urls.py`, `apps/pesanan/urls.py`, `apps/pesanan/views.py`, `apps/pesanan/serializers.py`.
Tanda **[BELUM TERVERIFIKASI]** = belum terlihat di kode yang diperiksa; jangan diasumsikan oleh frontend.

Base URL (dev): `http://127.0.0.1:8000`

---

## 1. Autentikasi

| Metode | Endpoint | Keterangan |
|---|---|---|
| POST | `/api/auth/token/` | `obtain_auth_token` bawaan DRF |

Request body (format bawaan DRF):
```json
{ "username": "...", "password": "..." }
```
Response sukses:
```json
{ "token": "..." }
```
Header untuk request berikutnya (jika `TokenAuthentication` aktif di settings) **[BELUM TERVERIFIKASI — cek `REST_FRAMEWORK` di settings.py]**:
```
Authorization: Token <token>
```

Semua endpoint pesanan memakai permission `HasUMKMMembership`: pengguna harus punya keanggotaan UMKM aktif.
Data selalu dibatasi ke UMKM milik pengguna. Pesanan UMKM lain akan menghasilkan **404**.

**Penting:** `umkm_id` TIDAK dikirim klien. Saat membuat pesanan, backend memakai keanggotaan aktif pertama milik pengguna.
Belum ada mekanisme pindah UMKM.

---

## 2. Pesanan — `/api/pesanan/pesanan/`

### Status pesanan
`DRAFT → MENUNGGU_REVIEW → DIKONFIRMASI → SELESAI`, dan `DIBATALKAN` (dari status mana pun, menurut docstring urls.py).

### Daftar endpoint

| Metode | URL | Fungsi | Body |
|---|---|---|---|
| GET | `/api/pesanan/pesanan/` | Daftar pesanan (paginasi) | – |
| POST | `/api/pesanan/pesanan/` | Buat pesanan baru (status DRAFT) | lihat 2.2 |
| GET | `/api/pesanan/pesanan/{id}/` | Detail pesanan | – |
| POST | `/api/pesanan/pesanan/{id}/proses-langflow/` | Kirim teks chat ke AI, simpan item, ke MENUNGGU_REVIEW | – |
| PATCH | `/api/pesanan/pesanan/{id}/items/{item_id}/verifikasi/` | Operator memilih produk yang benar untuk satu item | lihat 2.4 |
| POST | `/api/pesanan/pesanan/{id}/ajukan-review/` | DRAFT → MENUNGGU_REVIEW | – |
| POST | `/api/pesanan/pesanan/{id}/konfirmasi/` | MENUNGGU_REVIEW → DIKONFIRMASI | – |
| POST | `/api/pesanan/pesanan/{id}/selesai/` | DIKONFIRMASI → SELESAI | – |
| POST | `/api/pesanan/pesanan/{id}/batalkan/` | → DIBATALKAN | – |

### 2.1 Daftar pesanan (GET)
Query params:
- `status` — opsional, salah satu status valid (huruf besar/kecil diabaikan). Nilai tidak valid diabaikan (tidak error).
- `page`, `page_size` — default 20, maksimum 100.

Urutan: `dibuat_pada` terbaru dulu.

Bentuk response (paginasi bawaan DRF `PageNumberPagination`) **[BELUM TERVERIFIKASI — format persisnya perlu dicek dengan satu panggilan nyata]**:
```json
{ "count": 0, "next": null, "previous": null, "results": [ /* objek Pesanan */ ] }
```

### 2.2 Buat pesanan (POST)
Request:
```json
{
  "nama_pelanggan": "string, wajib, maks 200 karakter",
  "teks_chat_asli": "string, wajib",
  "catatan": "string, opsional"
}
```
Response: **201** + objek Pesanan (lihat 2.5).
Error: **403** `{"detail": "Tidak ada keanggotaan UMKM aktif."}`, atau **400** berisi error validasi per field.

### 2.3 Proses dengan AI (POST `.../proses-langflow/`)
Tanpa body. Hanya untuk pesanan DRAFT. Harga diambil dari database, bukan dari AI.
Response sukses: **200** + objek Pesanan lengkap (status `MENUNGGU_REVIEW`, `item_pesanan` terisi).

| Kode | Penyebab | Body |
|---|---|---|
| 400 | Aturan bisnis/status tidak terpenuhi | `{"detail": "..."}` |
| 502 | Langflow gagal (koneksi, HTTP error, respons tidak valid) | `{"detail": "Gagal menghubungi layanan AI. Coba lagi nanti."}` |
| 504 | Langflow timeout (batas 60 detik) | `{"detail": "Langflow tidak merespons. Coba lagi beberapa saat."}` |

Catatan untuk UI: panggilan ini bisa memakan waktu hingga ~60 detik. Tampilkan loading dan nonaktifkan tombol selama menunggu.
Perilaku jika dipanggil dua kali pada pesanan yang sudah punya item: **[BELUM TERVERIFIKASI]** (ada di daftar tugas backend).

### 2.4 Verifikasi item (PATCH)
Dipakai operator untuk item `AMBIGU` / `TIDAK_DITEMUKAN`.
Request:
```json
{ "produk_id": 1, "kuantitas": 2 }
```
- `produk_id`: integer, wajib. Produk harus milik UMKM pengguna, kalau tidak **404**.
- `kuantitas`: integer, wajib, minimal 1.

Response: **200** + objek Pesanan lengkap (bukan hanya item). Error: **400** `{"detail": "..."}`.

### 2.5 Objek Pesanan
```json
{
  "id": 1,
  "umkm_id": "U001",
  "nomor_pesanan": "ORD-U001-20261011-AEBB18E1",
  "nama_pelanggan": "...",
  "teks_chat_asli": "...",
  "status": "MENUNGGU_REVIEW",
  "catatan": "",
  "item_pesanan": [ /* objek Item */ ],
  "dibuat_pada": "...",
  "diperbarui_pada": "..."
}
```
Semua field read-only.

### 2.6 Objek Item
```json
{
  "id": 1,
  "produk": 12,
  "teks_asli": "...",
  "nama_ditafsirkan": "...",
  "kuantitas": 2,
  "harga_satuan": "70000.00",
  "subtotal": "140000.00",
  "hpp_snapshot": null,
  "status_item": "DITEMUKAN",
  "catatan_validasi": "..."
}
```
- `produk`: ID produk (angka) atau `null`. **Bukan** objek bersarang. Nama produk resmi harus diambil dari endpoint katalog.
- `harga_satuan`, `subtotal`: dikirim sebagai **string desimal**. Format untuk tampilan, jangan dijumlah sebagai float.
- `status_item` yang terlihat di kode: `DITEMUKAN`, `AMBIGU`, `TIDAK_DITEMUKAN`. Status lain (mis. setelah verifikasi) **[BELUM TERVERIFIKASI — cek konstanta di models.py]**.

---

## 3. Katalog dan Memori (hanya baca)
Dari docstring `config/urls.py`. Serializer dan view belum diperiksa, jadi field-nya **[BELUM TERVERIFIKASI]**.

| Metode | URL |
|---|---|
| GET | `/api/katalog/produk/` (paginasi) |
| GET | `/api/katalog/produk/{id}/` |
| GET | `/api/memori/memori/` (hanya status DISETUJUI) |
| GET | `/api/memori/memori/{id}/` |

Catatan: docstring hanya mencantumkan GET untuk katalog. Jadi frontend **tidak bisa** menambah/mengedit produk lewat API saat ini. Halaman CRUD katalog di luar cakupan sampai backend-nya ditambah.

---

## 4. Format error
- Error aturan bisnis: `{"detail": "pesan"}` (400/403/404/502/504).
- Error validasi serializer (400): objek per field, bentuk bawaan DRF, mis. `{"nama_pelanggan": ["This field is required."]}`.
- 401/403 karena token tidak ada/salah: **[BELUM TERVERIFIKASI]**.

---

## 5. Hal yang harus diselesaikan sebelum frontend bisa memanggil API dari browser
1. **CORS**: frontend (mis. `http://localhost:5173`) berbeda origin dari Django (`:8000`). Browser akan memblokir request kecuali backend memasang `django-cors-headers`.
   Cek `requirements.txt` dan `settings.py`. Ini hampir pasti perlu ditambahkan.
2. Konfirmasi `DEFAULT_AUTHENTICATION_CLASSES` memuat `TokenAuthentication`.
3. Frontend tidak boleh menyimpan secret apa pun. Hanya token pengguna.

---

## 6. Aturan untuk IBM Bob
- Gunakan **hanya** endpoint di dokumen ini. Jangan membuat endpoint baru di frontend.
- Jangan mengubah backend tanpa persetujuan manusia.
- Item `AMBIGU` / `TIDAK_DITEMUKAN` harus tampil jelas dan diberi aksi "Verifikasi".
- Tombol "Konfirmasi" hanya aktif untuk pesanan `MENUNGGU_REVIEW`.
- Jangan menghitung harga/total sendiri di frontend. Tampilkan nilai dari API.
