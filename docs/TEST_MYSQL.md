# Smoke test MySQL dan konfirmasi bersamaan

Gunakan database uji terpisah, misalnya sikos_test, agar data asli tidak berubah.

1. Siapkan MySQL 8+ InnoDB. Salin konfigurasi lingkungan, ganti DATABASE_URL menuju sikos_test.
2. Jalankan init-db, create-admin, seed-demo. Buka aplikasi.
3. Sebagai anggota buat dua pesanan berbeda masing-masing 1 unit produk yang stoknya tepat 1. Keduanya masih Menunggu konfirmasi dan stok tetap 1.
4. Dari dua browser/sesi admin berbeda konfirmasi kedua pesanan hampir bersamaan.
5. Hasil yang diharapkan: hanya satu Dikonfirmasi, satu tetap Menunggu konfirmasi/ditolak karena stok tidak cukup. Stok akhir 0. Satu Sale valid dan satu audit keluar. Jika MySQL mendeteksi deadlock, request gagal tanpa commit parsial dan aman dicoba ulang.
6. Klik konfirmasi lagi pada pesanan yang sama. Stok tidak turun ulang, Sale.order_id tetap unik.
7. Batalkan pesanan terkonfirmasi dari dua sesi hampir bersamaan. Stok kembali 1, hanya satu audit pengembalian, Sale menjadi tidak valid.
8. Buat pesanan multi-barang, lalu habiskan salah satu stok lewat menu Persediaan sebelum konfirmasi. Konfirmasi harus gagal dan stok semua barang lainnya tetap sama.
9. Uji tambah/edit anggota, kategori, produk, perubahan stok, impor Excel dan ekspor laporan pada MySQL yang sama.
10. Uji UI desktop/mobile termasuk form, tabel, grafik CDN dan seluruh tombol.

Row locking MySQL berada di services.transition/create_order dengan SELECT FOR UPDATE. Service tidak commit sendiri, route melakukan commit setelah seluruh proses berhasil. Exception dependency mengeksekusi rollback. Urutan penguncian produk berdasarkan ID agar konsisten. Constraint FK/unique/check ada di models.py.


## XAMPP MariaDB

Server XAMPP lokal terverifikasi MariaDB 10.4.32. Untuk menguji transaksi dan
konkurensi pada server ini secara eksplisit, jalankan melalui CMD:

```cmd
set SIKOS_ALLOW_MARIADB=1
venv\Scripts\python.exe -m pytest tests/test_mysql.py -q -s
set SIKOS_ALLOW_MARIADB=
```

Laporkan hasilnya sebagai **MariaDB**, bukan MySQL 8. Tanpa flag tersebut,
tes integrasi yang terhubung ke MariaDB dilewati dengan alasan yang jelas.
`SIKOS_TEST_DATABASE_URL` di `.env` harus menunjuk database terpisah berakhiran
`_test`. Tidak ada fallback ke database aplikasi.
