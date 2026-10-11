
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.umkm.models import UMKM
from apps.katalog.models import Produk
from apps.memori.models import Memori


class Command(BaseCommand):
    help = "Impor data katalog dan memori dari CSV ke database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validasi data tanpa menyimpan perubahan.",
        )

    def handle(self, *args, **options):
        base_dir = Path(__file__).resolve().parents[4]
        seed_dir = base_dir / "seed_data"

        katalog_path = seed_dir / "katalog_multi.csv"
        memori_path = seed_dir / "memori_multi.csv"

        for path in (katalog_path, memori_path):
            if not path.is_file():
                raise CommandError(f"File tidak ditemukan: {path}")

        dry_run = options["dry_run"]

        try:
            katalog_rows = self.read_csv(katalog_path)
            memori_rows = self.read_csv(memori_path)

            self.validate_katalog(katalog_rows)
            self.validate_memori(memori_rows)

            if dry_run:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Validasi berhasil: {len(katalog_rows)} produk "
                        f"dan {len(memori_rows)} memori. "
                        "Tidak ada perubahan disimpan."
                    )
                )
                return

            with transaction.atomic():
                umkm_ids = {
                    row["UMKM_ID"].strip()
                    for row in katalog_rows + memori_rows
                }

                for umkm_id in sorted(umkm_ids):
                    UMKM.objects.get_or_create(
                        id=umkm_id,
                        defaults={
                            "nama": f"UMKM {umkm_id}",
                            "deskripsi": "Nama sementara; silakan perbarui "
                            "dengan nama bisnis sebenarnya.",
                        },
                    )

                for row in katalog_rows:
                    umkm = UMKM.objects.get(id=row["UMKM_ID"].strip())

                    Produk.objects.update_or_create(
                        umkm=umkm,
                        sku=row["SKU"].strip(),
                        defaults={
                            "nama_produk": row["Nama_Produk"].strip(),
                            "kategori": row["Kategori"].strip(),
                            "warna": row["Warna"].strip(),
                            "ukuran": row["Ukuran"].strip(),
                            "harga": Decimal(row["Harga"].strip()),
                            "stok": int(row["Stok"].strip()),
                            "aktif": row["Aktif"].strip().upper() == "TRUE",
                        },
                    )

                for row in memori_rows:
                    umkm = UMKM.objects.get(id=row["UMKM_ID"].strip())

                    Memori.objects.update_or_create(
                        umkm=umkm,
                        id_memori=row["ID_Memori"].strip(),
                        defaults={
                            "istilah": row["Istilah"].strip(),
                            "makna": row["Makna"].strip(),
                            "sumber": row["Sumber"].strip(),
                            "status": row["Status"].strip().upper(),
                            "versi": int(row["Versi"].strip()),
                            "makna_sebelumnya": row[
                                "Makna_Sebelumnya"
                            ].strip(),
                            "dibuat_pada": datetime.strptime(
                                row["Dibuat_Pada"].strip(), "%Y-%m-%d"
                            ).date(),
                            "disetujui_oleh": row["Disetujui_Oleh"].strip(),
                            "tindakan": row["Tindakan"].strip(),
                            "catatan": row["Catatan"].strip(),
                        },
                    )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Impor berhasil: {len(katalog_rows)} produk "
                    f"dan {len(memori_rows)} memori."
                )
            )

        except (ValueError, KeyError, InvalidOperation) as exc:
            raise CommandError(f"Data CSV tidak valid: {exc}") from exc

    @staticmethod
    def read_csv(path):
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if not reader.fieldnames:
                raise ValueError(f"CSV kosong: {path.name}")

            reader.fieldnames = [
                name.strip().lstrip("\ufeff")
                for name in reader.fieldnames
            ]
            return list(reader)

    @staticmethod
    def validate_katalog(rows):
        required = {
            "UMKM_ID", "SKU", "Nama_Produk", "Kategori",
            "Warna", "Ukuran", "Harga", "Stok", "Aktif",
        }

        if not rows:
            raise ValueError("CSV katalog tidak memiliki data.")

        if not required.issubset(rows[0].keys()):
            raise ValueError("Kolom katalog tidak sesuai.")

        seen = set()

        for number, row in enumerate(rows, start=2):
            umkm_id = row["UMKM_ID"].strip()
            sku = row["SKU"].strip()
            key = (umkm_id, sku)

            if not umkm_id or not sku or key in seen:
                raise ValueError(
                    f"Katalog baris {number}: UMKM_ID/SKU kosong "
                    "atau duplikat."
                )

            seen.add(key)

            harga = Decimal(row["Harga"].strip())
            stok = int(row["Stok"].strip())
            aktif = row["Aktif"].strip().upper()

            if harga < 0 or stok < 0:
                raise ValueError(
                    f"Katalog baris {number}: harga/stok negatif."
                )

            if aktif not in {"TRUE", "FALSE"}:
                raise ValueError(
                    f"Katalog baris {number}: Aktif harus TRUE/FALSE."
                )

    @staticmethod
    def validate_memori(rows):
        required = {
            "UMKM_ID", "ID_Memori", "Istilah", "Makna", "Sumber",
            "Status", "Versi", "Makna_Sebelumnya", "Dibuat_Pada",
            "Disetujui_Oleh", "Tindakan", "Catatan",
        }

        if not rows:
            raise ValueError("CSV memori tidak memiliki data.")

        if not required.issubset(rows[0].keys()):
            raise ValueError("Kolom memori tidak sesuai.")

        seen = set()
        approved_terms = set()

        for number, row in enumerate(rows, start=2):
            umkm_id = row["UMKM_ID"].strip()
            memory_id = row["ID_Memori"].strip()
            term = row["Istilah"].strip()
            status = row["Status"].strip().upper()

            key = (umkm_id, memory_id)

            if not umkm_id or not memory_id or key in seen:
                raise ValueError(
                    f"Memori baris {number}: ID kosong atau duplikat."
                )

            seen.add(key)

            if status not in {"DISETUJUI", "DIGANTIKAN", "PENDING"}:
                raise ValueError(
                    f"Memori baris {number}: status tidak dikenal."
                )

            int(row["Versi"].strip())
            datetime.strptime(
                row["Dibuat_Pada"].strip(), "%Y-%m-%d"
            )

            if status == "DISETUJUI":
                approved_key = (umkm_id, term.casefold())
                if approved_key in approved_terms:
                    raise ValueError(
                        f"Memori baris {number}: istilah memiliki "
                        "lebih dari satu versi DISETUJUI."
                    )
                approved_terms.add(approved_key)
