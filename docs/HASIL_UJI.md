# Hasil pengujian

Verifikasi lokal Windows pada 16 November 2026.

## Setup aplikasi

- Venv baru `venv`: Python 3.14.6, dibuat melalui CMD; dependensi terpasang.
- Koneksi XAMPP diverifikasi ke server **10.4.32-MariaDB**.
- `.env` dikonfigurasi secara lokal. SESSION_SECRET acak dibuat tanpa ditampilkan.
- Database aplikasi `sikos` dan database uji terpisah `sikos_prd_test` tersedia.
  Keduanya diperiksa kosong sebelum setup. Database proyek lain tidak diubah.
- `python -m app.cli init-db` berhasil. Ketujuh tabel diverifikasi memakai InnoDB.
- Pengguna membuat admin secara interaktif di CMD; akun aktif dan login browser
  berhasil diverifikasi. Password tidak dimasukkan ke source maupun chat.
- Aplikasi berjalan di http://127.0.0.1:8001.

## Pengujian otomatis

Perintah dari CMD, di folder proyek:

```cmd
set SIKOS_ALLOW_MARIADB=1
venv\Scripts\python.exe -m pytest tests -q -s -p no:cacheprovider
set SIKOS_ALLOW_MARIADB=
```

Hasil: **24 passed, 1 warning**. Rincian: 22 tes SQLite temporer dan 2 tes
integrasi MariaDB nyata. Waktu suite 19,79 detik berlaku untuk run SQLite
sebelumnya; durasi run gabungan tidak dicatat. Peringatan adapter httpx/Starlette
deprecated tidak menggagalkan pengujian.

Tes integrasi memakai dua koneksi untuk perebutan stok terakhir, konfirmasi
berulang/paralel, pembatalan paralel, satu transaksi/audit stok keluar, satu audit
pengembalian, rollback seluruh barang saat salah satu stok kurang, snapshot harga,
serta pengecualian transaksi batal dari analisis harian/mingguan/bulanan/tahunan.
Fixture dibersihkan dari database uji setelah pengujian, tanpa drop tabel/database.

Tes SQLite juga mencakup autentikasi, role, CSRF, CRUD HTTP, impor parsial, template
dan ekspor Excel, keranjang, pesanan, periode WIB, empat status, dan pemuatan ulang
data yang sudah tersimpan di sesi saat penguncian baris.

Perintah pytest harus menyebut `tests` secara eksplisit: kurung siku dalam path
Windows menyebabkan perintah tanpa path tes gagal saat pengumpulan.

## Smoke test browser

Login admin berhasil. Halaman dashboard, anggota, kategori, produk, persediaan,
impor, katalog, keranjang, pesanan, transaksi dan laporan berhasil dimuat.
Grafik Chart.js pada laporan terlihat ter-render. Tampilan dashboard dan laporan
diperiksa secara visual. Data aplikasi masih kosong selain admin; smoke test ini
memverifikasi navigasi dan empty state, bukan seluruh alur transaksi berisi data
melalui browser. Alur transaksi diuji otomatis seperti rincian di atas.

## Batas verifikasi

- **MySQL 8 nyata belum diuji.** MariaDB XAMPP tidak dilaporkan sebagai MySQL 8.
  Tanpa `SIKOS_ALLOW_MARIADB=1`, tes integrasi melewati server MariaDB dengan alasan
  eksplisit. Gunakan server MySQL 8 terpisah untuk memenuhi verifikasi stack persis.
- File Excel lama belum tersedia; pemetaan header spesifik belum dilakukan.
- Tabel baru memiliki constraint status dan engine InnoDB. `init-db` bukan migrasi
  tabel lama; database lama harus diperiksa sebelum perubahan skema tanpa reset data.
