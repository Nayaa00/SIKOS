# SIKOS — Sistem Informasi Koperasi Sembako

Implementasi PRD 1.0 untuk studi kasus Koperasi Sejahtera. Proyek ini memakai FastAPI + MySQL, HTML/Jinja2 + Bootstrap/CSS/JavaScript, Pandas/openpyxl dan Chart.js.

Baca `docs/PRD_CHECKLIST.md` untuk pemetaan kebutuhan, keputusan bisnis, dan batas pengujian. ERD serta alur status ada di `docs/ERD.md`. Instruksi untuk melanjutkan di Codex ada di `file.txt`.

## Siapkan Windows

1. Ekstrak ZIP. Buka folder `sikos` yang memiliki `requirements.txt` sebagai folder proyek di Codex atau VS Code. Buat proyek terpisah dari DjangoMongoProject.
2. Pastikan Python 3.11+ tersedia. Buka terminal **Command Prompt (CMD)**. Jika terminal masih PowerShell, ketik `cmd`.
3. Jalankan satu per satu.

```cmd
python -m venv venv
venv\Scripts\activate.bat
python -m pip install -r requirements.txt
copy .env.example .env
```

Aktivasi `.bat` menghindari masalah PowerShell dengan spasi dan kurung siku di nama folder seperti yang pernah terjadi saat praktikum.

## Siapkan MySQL

Gunakan MySQL 8+ dengan engine InnoDB. Buka SQL editor dari MySQL Workbench/phpMyAdmin yang terhubung ke MySQL dan buat database.

```sql
CREATE DATABASE IF NOT EXISTS sikos CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Edit `.env`, isi `DATABASE_URL` memakai akun database lokalmu. Contoh bentuk URL:

```text
DATABASE_URL=mysql+pymysql://root:ISI_PASSWORD@127.0.0.1:3306/sikos?charset=utf8mb4
```

Jika root tidak memakai password, bentuknya `mysql+pymysql://root@127.0.0.1:3306/sikos?charset=utf8mb4`.
Karakter khusus dalam password URL perlu di-encode. Jangan mengirim password ke chat atau memasukkannya ke git. Akun MySQL berbeda dari akun login aplikasi SIKOS.

Isi SESSION_SECRET dengan teks acak minimal 32 karakter. Buat teks tersebut dengan:

```cmd
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Salin hasil ke SESSION_SECRET di `.env`. Jangan mengubah secret saat sesi pengguna masih dipakai karena cookie lama menjadi tidak valid.

## Inisialisasi dan jalankan

```cmd
python -m app.cli init-db
python -m app.cli create-admin
python -m app.cli seed-demo
python -m uvicorn app.main:app --reload
```

- `init-db` membuat tabel baru, tidak mereset data yang sudah ada. Skema SQLAlchemy adalah sumber skema versi awal ini.
- `create-admin` meminta email/password di terminal. Password tidak ditampilkan saat diketik.
- `seed-demo` opsional: menambah enam produk contoh dan stok awal dengan audit. Tidak mengubah produk dengan kode sama dan tidak menciptakan penjualan palsu.
- Buka http://127.0.0.1:8000 lalu login dengan admin yang dibuat.
- Matikan dengan Ctrl+C. Untuk menjalankan ulang cukup aktifkan venv dan jalankan uvicorn.
- Jika port 8000 dipakai Django lama, hentikan Django atau jalankan `python -m uvicorn app.main:app --reload --port 8001` dan buka http://127.0.0.1:8001.

## Alur pengurus

1. Dashboard menampilkan ringkasan, tren penjualan, barang terlaris dan stok tertinggi. Pilih periode/tanggal acuan.
2. Anggota: tambah/edit nomor, nama, email, telepon, alamat dan password. Hapus berarti nonaktif untuk mempertahankan riwayat.
3. Kategori: tambah/edit/aktifkan/nonaktifkan kategori.
4. Produk: tambah/edit data produk. Stok awal masuk catatan stok. Untuk gambar opsional, isi URL HTTPS gambar.
5. Persediaan: catat masuk/keluar dengan alasan. Stok negatif ditolak. Audit mencatat pelaku dan stok sesudah perubahan.
6. Impor Excel: unduh template, isi dan unggah. Header wajib `kode,nama,kategori,harga,stok,satuan`, deskripsi opsional. Kolom boleh beda urutan. Harga rupiah bulat, stok integer nonnegatif. Maksimal 5.000 baris / 10 MB. Ubah formula menjadi nilai.
7. Pesanan: konfirmasi pesanan anggota. Konfirmasi mengurangi stok tepat sekali dan mencatat transaksi. Selesaikan setelah barang diserahkan.
8. Pembatalan sebelum konfirmasi tidak memengaruhi stok. Pembatalan setelah konfirmasi mengembalikan stok tepat sekali dan membatalkan validitas transaksi. Pesanan Selesai tidak dapat dibatalkan pada versi ini.
9. Transaksi menampilkan catatan valid/batal. Laporan hanya menghitung transaksi valid dari tanggal konfirmasi.

## Alur anggota

1. Daftar anggota di `/daftar`, lalu login dengan email/password.
2. Cari produk atau pilih kategori di katalog. Produk habis ditandai.
3. Masukkan barang ke keranjang. Ubah jumlah, klik Perbarui keranjang. Isi 0 untuk menghapus baris.
4. Klik Buat pesanan. Harga snapshot disimpan, stok belum dikurangi sampai konfirmasi admin.
5. Lihat status dan rincian pesanan sendiri melalui Pesanan.

## Demonstrasi yang disarankan

- Admin memasukkan produk secara manual dan mengimpor Excel berisi satu baris valid, satu kode duplikat dan satu stok negatif. Tunjukkan ringkasan berhasil/gagal.
- Anggota memesan 2 beras dan 3 mi instan. Tunjukkan subtotal dan total di keranjang.
- Admin mengonfirmasi, lalu periksa stok dan riwayat Persediaan. Klik konfirmasi berulang tidak boleh mengurangi ulang.
- Batalkan satu pesanan terkonfirmasi dan tunjukkan stok kembali serta transaksi ditandai batal.
- Buat pesanan lain hingga Selesai. Tunjukkan terlaris berdasarkan unit, stok tertinggi, grafik tren.
- Tampilkan empat jenis laporan dan ekspor Excel. Pilih tanggal konfirmasi yang sesuai.
- Coba akses `/produk` sebagai anggota untuk menunjukkan batas peran.

## Pengujian otomatis

```cmd
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

Test memakai SQLite sementara agar cepat dijalankan tanpa mengubah data MySQL. Pengujian logika lulus tidak membuktikan konkurensi MySQL. Untuk tes konfirmasi paralel nyata, lihat `docs/TEST_MYSQL.md`.

## Aturan yang perlu dipahami tim

- Transaksi valid = pesanan Dikonfirmasi atau Selesai, belum dibatalkan. Laporan berdasarkan tanggal konfirmasi dalam WIB. Laporan menunjukkan omzet, bukan laba atau kas terpisah.
- Keranjang belum mereservasi stok. Stok diperiksa saat pesan dan saat konfirmasi. Jika stok sudah habis ketika admin mengonfirmasi, seluruh konfirmasi ditolak.
- Impor kode duplikat ditolak, tidak memperbarui barang/stok yang telah ada. Gunakan Edit atau catatan stok masuk untuk barang lama. File Excel sistem sebelumnya belum disediakan, jadi format header spesifik belum dipetakan.
- Data transaksi/audit tidak dihapus. Master data menggunakan soft delete.
- Pada prototipe ini semua daftar dimuat untuk skala praktikum. Riwayat stok menampilkan 300 entri terbaru. Pagination dapat ditambahkan jika data uji besar.
- Bootstrap/Chart.js dari CDN memerlukan internet untuk grafik. Tabel/form dasar memakai CSS lokal. Smoke test navigasi/empty state dan grafik telah dilakukan di browser lokal; lihat docs/HASIL_UJI.md.
- Proyek untuk demonstrasi lokal. Untuk deployment publik perlu HTTPS, COOKIE_SECURE=1, konfigurasi server dan manajemen secret, rate limiting login, serta pengujian tambahan.

## Masalah umum

- `Connection refused` / `Access denied`: pastikan layanan MySQL aktif, database sikos dibuat, dan DATABASE_URL benar.
- `SESSION_SECRET` belum diisi: salin `.env.example` ke `.env`, isi minimal 32 karakter, lalu restart uvicorn.
- Form kedaluwarsa/403 setelah login: muat ulang halaman untuk mendapatkan token CSRF baru.
- Password terminal tidak terlihat: memang disembunyikan saat create-admin.
- `No module named ...`: aktifkan venv dan install requirements pada interpreter yang sama.
- Produk kosong: buat kategori dan produk, impor template, atau jalankan seed-demo.
- Laporan kosong: buat dan konfirmasi pesanan, lalu pilih tanggal konfirmasinya.

## Referensi

- https://fastapi.tiangolo.com/advanced/templates/
- https://docs.sqlalchemy.org/en/20/orm/session_basics.html
- https://docs.sqlalchemy.org/en/20/core/selectable.html#sqlalchemy.sql.expression.Select.with_for_update

## Catatan setup Windows yang diverifikasi

Gunakan `cd /d "PATH_LENGKAP_FOLDER_SIKOS"` pada CMD. Tanda kutip diperlukan
untuk path berspasi. Jalankan pytest dengan argumen `tests` eksplisit karena
kurung siku pada path dapat dianggap sebagai parametrization oleh pytest.
Venv baru di folder `venv` memakai interpreter Python yang membuatnya.

XAMPP pada komputer ini membundel MariaDB 10.4.32. MariaDB bukan MySQL 8;
hasil pengujian pada MariaDB harus dilaporkan terpisah dari MySQL.
Jangan mengubah database proyek praktikum lain.

Tes integrasi opsional tersedia di `tests/test_mysql.py`. Isi
`SIKOS_TEST_DATABASE_URL` sendiri pada `.env` untuk database khusus yang namanya
berakhiran `_test` (contoh `sikos_test`), lalu jalankan:

```cmd
python -m pytest tests/test_mysql.py -q
```

Tanpa URL tersebut tes integrasi dilewati, bukan dinyatakan lulus. Tes tidak
menjatuhkan tabel/database; hanya membuat tabel yang belum ada dan membersihkan
baris fixture miliknya. Database uji harus sudah dibuat lebih dahulu.
