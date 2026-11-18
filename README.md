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
6. Impor Excel: unduh template, isi dan unggah. Header wajib `kode,nama,label,kategori,harga,stok,satuan`, deskripsi opsional. Kolom boleh beda urutan. Harga rupiah bulat, stok integer nonnegatif. Maksimal 5.000 baris / 10 MB. Ubah formula menjadi nilai.
7. Pesanan: konfirmasi pesanan anggota. Konfirmasi mengurangi stok tepat sekali dan mencatat transaksi. Selesaikan setelah pembayaran tunai dan penyerahan selesai; pembayaran otomatis Lunas sebesar total pesanan dengan kembalian Rp0.
8. Pembatalan sebelum konfirmasi tidak memengaruhi stok. Pembatalan setelah konfirmasi mengembalikan stok tepat sekali dan membatalkan validitas transaksi. Pesanan Selesai tidak dapat dibatalkan pada versi ini.
9. Transaksi menampilkan catatan valid/batal. Laporan hanya menghitung transaksi valid dari tanggal konfirmasi.

## Alur anggota

1. Daftar anggota di `/daftar`, lalu login dengan email/password.
2. Cari produk atau pilih kategori di katalog. Produk habis ditandai.
3. Masukkan barang ke keranjang. Ubah jumlah, klik Perbarui keranjang. Isi 0 untuk menghapus baris.
4. Klik Buat pesanan. Harga snapshot disimpan, stok belum dikurangi sampai konfirmasi admin.
5. Dashboard menampilkan jumlah pesanan pribadi per status. Buka Pesanan Saya untuk melihat rincian, filter status dan halaman riwayat (20 pesanan per halaman).
6. Anggota dapat membatalkan pesanan sendiri yang masih Menunggu konfirmasi. Setelah admin memprosesnya, pembatalan oleh anggota ditolak. Pembatalan menunggu tidak mengubah stok.
7. Transaksi Saya menampilkan transaksi milik akun sendiri setelah dikonfirmasi, rincian harga saat pesan, pembayaran tunai dan kembalian. Transaksi dibatalkan tetap terlihat sebagai riwayat dan tidak dihitung dalam penjualan.
8. Profile menampilkan nomor anggota dan role tetap; nama, email, telepon dan alamat dapat diperbarui. Ubah password membutuhkan password lama dan konfirmasi password baru. Kesalahan form mempertahankan input non-password.

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
- Pesanan dan Transaksi Saya dibatasi 20 entri per halaman. Produk dan daftar master masih dimuat untuk skala praktikum. Riwayat stok menampilkan 300 entri terbaru.
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


## Label dan kategori produk

Kategori utama: Bahan pokok, Perawatan, Makanan ringan, Minuman, Kesehatan.
Label menjelaskan jenis yang lebih spesifik, misalnya Beras, Sabun mandi atau Teh.
Pencarian katalog memakai nama atau label, bukan kode; filter kategori tetap ada.
Template Excel baru memuat `kode,nama,label,kategori,harga,stok,satuan,deskripsi`.
Kategori kustom harus dibuat di menu Kategori sebelum digunakan saat impor. Format lama dengan kategori Beras/Minyak/Gula
dan jenis lama yang dikenali otomatis dipetakan menjadi label dan kategori utama.
Kode produk yang sudah ada tetap ditolak sehingga impor tidak menimpa stok.

Untuk database lama, jalankan `python -m app.cli migrate-labels` sebelum restart
aplikasi. Migrasi menambahkan kolom label, membuat lima kategori utama jika belum
ada, dan memetakan kategori lama yang aktif. Kategori lama dinonaktifkan setelah
dipindahkan; kategori lama yang sudah nonaktif dibiarkan untuk menjaga visibilitas.
Kategori khusus lain tidak dipetakan sembarangan. Migrasi tidak mengubah stok,
harga, pesanan, transaksi, atau audit dan aman dijalankan ulang.

## Foto dan kartu produk

Menu Produk memakai CardView. Foto ilustrasi lokal dipilih sesuai nama produk; gambar HTTPS khusus bisa diisi di form Edit. Kosongkan gambar untuk memakai foto otomatis. Sumber dan lisensi tersedia melalui tautan Sumber foto di halaman Produk/Katalog dan file app/static/products/credits.html. Penghapusan tetap berupa arsip agar riwayat stok dan transaksi terjaga.


## Pemisahan halaman admin dan pembeli

Katalog, Keranjang, tambah/ubah keranjang dan pembuatan pesanan khusus role anggota (pembeli). Menu tersebut disembunyikan dari admin dan akses langsung GET/POST oleh admin ditolak 403. Admin melihat barang melalui Produk dan tetap dapat memproses pesanan melalui Pesanan, Transaksi dan Laporan.

## Kategori dan kode produk otomatis

Admin dapat menambah kategori melalui nama, status aktif, dan awalan kode opsional.
Awalan terdiri dari tiga huruf unik. Jika kosong, sistem membuatnya dari nama kategori.
Nama kategori pada daftar tetap berupa teks; statusnya dapat diubah melalui Simpan.

| Kategori utama | Awalan | Contoh |
| --- | --- | --- |
| Bahan pokok | BPK | BPK001 |
| Perawatan | PRW | PRW001 |
| Makanan ringan | MKR | MKR001 |
| Minuman | MNM | MNM001 |
| Kesehatan | SHT | SHT001 |

Pada Tambah produk, pilih kategori untuk mengisi pratinjau Kode produk secara otomatis.
Kode tidak dapat diketik manual. Server mengalokasikan nomor final secara atomik saat
menyimpan, dengan row lock kategori dan counter dalam transaksi yang sama. Pratinjau
tidak memesan nomor. Nomor minimal tiga digit, dapat bertambah setelah 999 dan tidak
dipakai ulang ketika produk diarsipkan. Mengedit tanpa mengganti kategori mempertahankan
kode; perpindahan kategori menghasilkan kode baru sesuai kategori tujuan.

Untuk database lama jalankan `python -m app.cli migrate-codes` sebelum restart aplikasi.
Migrasi menambah code_prefix/code_counter pada kategori dan source_code unik pada produk,
lalu mengubah kode produk tanpa mengganti ID, harga, stok, foto, status, transaksi atau audit.
Snapshot kode/nama/harga pada order_lines tetap menjadi riwayat saat pesanan dibuat.
Kode lama disimpan sebagai referensi anti-duplikat, sehingga impor ulang Excel lama tetap
ditolak tanpa menimpa stok. Migrasi aman dijalankan ulang. `init-db` menyertakan migrasi ini.

Header Excel tetap memiliki kolom kode: nilainya adalah referensi asal untuk anti-duplikat,
sedangkan kode yang ditampilkan aplikasi dihasilkan sesuai kategori. Kategori utama yang
belum ada dapat dibuat saat impor; kategori kustom harus ditambahkan di menu Kategori dahulu.


## Label dropdown dan pencarian Produk

Pada Tambah/Edit produk, Label dipilih dari dropdown berdasarkan nilai label unik
yang sudah tersimpan di data produk, termasuk produk arsip. Backend menolak label
di luar pilihan tersebut. Jika belum ada label, impor data produk terlebih dahulu;
tidak ada label baru yang dibuat hanya dengan mengetik pada form ini.

Menu Produk memiliki pencarian nama/kode/label dan filter kategori dropdown yang dapat
digabungkan. Hasil tetap berupa CardView, meliputi produk aktif maupun arsip untuk
keperluan administrasi. Filter menyertakan kategori nonaktif agar datanya tetap dapat
dikelola. Jumlah hasil, pilihan kategori dan kata pencarian dipertahankan; Reset
mengembalikan seluruh produk. Tidak ada hasil menampilkan pesan khusus.

### Keranjang anggota (Tugas 2)

Keranjang sekarang memiliki foto barang, tombol Hapus per barang dan ringkasan belanja.
Ubah jumlah lalu klik Perbarui keranjang, atau langsung Buat pesanan untuk memakai jumlah
terbaru. Total pada layar mengikuti input; server memeriksa ulang harga, ketersediaan dan stok.
Jika stok berubah atau barang nonaktif, sesuaikan jumlah atau hapus barang sebelum melanjutkan.
Checkout tidak mengurangi stok. Pesanan menunggu konfirmasi admin.
