# UMKM Order Copilot
### AI-Powered Order Management for Small Businesses

UMKM Order Copilot adalah aplikasi berbasis web yang dirancang untuk membantu UMKM mengubah pesan pelanggan menjadi data pesanan terstruktur menggunakan AI, katalog produk, dan validasi backend.

## Features
- **AI Order Extraction** — mengekstrak informasi pesanan dari pesan pelanggan.
- **Product Matching** — mencocokkan pesanan dengan katalog produk UMKM.
- **Price Validation** — memvalidasi harga berdasarkan data katalog.
- **Order Review** — membantu mengidentifikasi produk yang tidak ditemukan atau informasi yang ambigu.

## Tech Stack
- **Frontend:** React, TypeScript
- **Backend:** Python, Django
- **Database:** PostgreSQL
- **AI Workflow:** IBM Langflow
- **Development Assistant:** IBM Bob

## Architecture

```text
React Frontend
      ↓
Django Backend
      ↓
IBM Langflow
      ↓
Backend Validation
      ↓
PostgreSQL
```

## Project Status

Project masih dalam tahap pengembangan dan integrasi. Integrasi IBM Langflow sedang dalam proses debugging, sehingga alur pemrosesan pesanan secara menyeluruh masih perlu diuji.

## Getting Started

Clone repository:

```bash
git clone https://github.com/Syifaa4/UMKM-Copilot.git
cd UMKM-Copilot
```

Jalankan frontend:

```bash
cd frontend
npm install
npm run dev
```

Untuk menjalankan backend, siapkan virtual environment, instal dependency, konfigurasi koneksi PostgreSQL dan Langflow, lalu jalankan Django.

## Author
**Syifa Nurul Afifah**

GitHub: [Syifaa4](https://github.com/Syifaa4)
Repository: [UMKM-Copilot](https://github.com/Syifaa4/UMKM-Copilot)
