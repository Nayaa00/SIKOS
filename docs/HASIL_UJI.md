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

## Pembaruan label dan kategori 17 November 2026

27 tes lulus: 25 SQLite dan 2 integrasi MariaDB nyata (1 warning adapter httpx/Starlette). Tes tambahan memeriksa pencarian nama/label tanpa kode, impor label/kategori utama, dan migrasi idempoten yang mempertahankan stok serta riwayat. Migrasi pada database sikos berhasil; kelima kategori aktif dan belum ada produk. Snapshot stok, harga, identitas produk, pesanan, rincian, transaksi dan audit identik sebelum/sesudah migrasi. Browser menampilkan lima pilihan kategori dan placeholder Cari nama atau label. Workbook latihan revisi 30 baris lolos parser tanpa disimpan ke database. MySQL 8 tetap belum diuji.

## CardView dan foto produk 17 November 2026

Menu Produk berubah menjadi kartu responsif dengan foto, nama, label, kode, harga/satuan, kategori, stok, status dan aksi edit/arsip. Tiga puluh produk yang sudah ada mendapat foto lokal; beras medium/premium berbagi foto jenis beras. Harga, stok, kategori, label dan status diverifikasi tidak berubah. Foto Wikimedia Commons disimpan lokal beserta atribusi/lisensi pada app/static/products/sources.json dan credits.html. Merek/kemasan foto adalah ilustrasi dan dapat berbeda dari produk simulasi. Custom URL HTTPS tetap didukung; path lokal dibatasi ke aset produk yang ada. Katalog juga memakai foto yang sama dan fallback lokal tersedia bila gambar gagal. Browser memverifikasi 30 elemen foto tanpa kegagalan gambar yang terdeteksi dan form edit berhasil dibuka.

Pengujian: 29 passed, 1 warning (27 SQLite + 2 integrasi MariaDB). MySQL 8 belum diuji. Seluruh URL foto lokal diverifikasi melalui HTTP.

## Akses katalog dan keranjang 17 November 2026

30 tes lulus (28 SQLite + 2 integrasi MariaDB; 1 warning adapter httpx/Starlette). Admin tidak melihat menu Katalog/Keranjang dan GET katalog/keranjang serta POST tambah/ubah keranjang/buat pesanan ditolak 403. Pengujian memastikan request admin tidak membuat pesanan atau mengurangi stok; anggota tetap dapat menjalankan alur belanja. Menu Pesanan untuk admin tetap tersedia. Sidebar admin diverifikasi di browser setelah restart. Tidak ada perubahan database aplikasi pada pembatasan role ini. MySQL 8 belum diuji.

## Kategori tetap dan form lama 17 November 2026

31 tes lulus: 29 SQLite + 2 integrasi MariaDB, 1 warning adapter httpx/Starlette. Halaman Kategori tidak lagi memiliki form Tambah atau dropdown nama. Endpoint hanya mengubah active; nama kiriman tidak dapat mengganti nama kategori. Form Tambah versi lama diarahkan kembali dengan pemberitahuan tanpa insert/duplikat atau kehilangan sesi. Tes memeriksa jumlah kategori tetap, aktif/nonaktif, nama tidak berubah, stok tetap, serta akses admin tetap valid. Browser memverifikasi lima nama kategori sebagai teks, checkbox status, dan tombol Simpan. Tidak mengubah data database aplikasi pada perapihan halaman. MySQL 8 belum diuji.


## Tambah kategori dan kode otomatis 17 November 2026

36 tes lulus: 33 SQLite + 3 integrasi MariaDB nyata; 1 warning adapter httpx/Starlette.
Tes mencakup kategori kustom, awalan unik, penolakan duplikat, pratinjau tanpa reservasi,
pengabaian kode manipulasi form, edit tetap/perpindahan kategori, rollback counter,
migrasi idempoten, pelestarian snapshot dan penolakan impor ulang melalui kode asal.
Tes dua koneksi MariaDB menghasilkan dua kode berbeda saat penambahan produk paralel.

Migrasi database aplikasi sikos berhasil untuk 30 produk: BPK001–006, PRW001–006,
MKR001–006, MNM001–006 dan SHT001–006. Pemetaan sebelum migrasi dicadangkan lokal
di folder kerja; ID produk, harga, stok, gambar, status, pesanan, rincian, transaksi
dan audit diverifikasi identik. Snapshot kode order_lines tidak diubah. Tidak menambah
produk contoh. Browser memverifikasi form Tambah kategori serta pratinjau BPK007,
PRW007, MKR007, MNM007 dan SHT007 saat kategori dipilih. Tidak menyimpan produk dummy.
MySQL 8 nyata belum diuji; hasil database ini adalah MariaDB XAMPP.


## Dropdown label dan filter Produk 17 November 2026

38 tes lulus: 35 SQLite + 3 integrasi MariaDB, 1 warning adapter httpx/Starlette.
Tes baru memeriksa dropdown dari data tersimpan, label terpilih pada Edit, penolakan
label palsu tanpa membuat produk/mengubah stok, pencarian nama/kode/label, gabungan
filter kategori, pilihan yang dipertahankan, hasil kosong/reset, validasi ID kategori,
pencarian wildcard literal, dan pembatasan halaman Produk dari pembeli.
Tidak ada perubahan skema atau isi database aplikasi pada perubahan ini.
MySQL 8 nyata belum diuji.

## Integrasi luthfi setelah cipa — 17 November 2026

Branch sumber: origin/luthfi pada 005bcfe. Digabung ke Octavian lokal setelah cipa.
Konflik main.py, member_form.html dan test_sikos.py diselesaikan dengan mempertahankan
form pendaftaran/konfirmasi password yang sudah digunakan dan seluruh tes kedua alur.
Pencatatan pembayaran tunai admin masuk, termasuk validasi nominal, kembalian,
penolakan pembayaran ganda dan batas akses. init-db kini menjalankan migrasi pembayaran.

Aturan PRD tetap berlaku: pesanan Dikonfirmasi dapat dibatalkan, stok kembali tepat satu
kali dan transaksi menjadi tidak valid untuk analisis. Riwayat pembayaran yang pernah
tercatat tetap disimpan; pembatalan bukan bukti bahwa uang sudah dikembalikan. Belum ada
alur pencatatan refund. Pembayaran dan pembatalan memakai urutan lock order lalu sale.

Migrasi tambah kolom hanya pada database sikos. Pemeriksaan sebelum/sesudah menunjukkan
stok/harga produk, status/total pesanan, snapshot baris, transaksi dan jumlah audit tetap.
Pengujian: 56 skenario, 55 langsung lulus; satu tes lama gagal karena teks kosong berubah
menjadi Keranjang masih kosong. Setelah menyesuaikan assertion, tes itu diulang dan lulus
(1 passed, 52 deselected). Termasuk 3 tes MariaDB XAMPP nyata yang lulus; MySQL 8 belum diuji.
Satu warning deprecation Starlette/httpx. Smoke test browser akun anggota: profil dan riwayat
pesanan terbuka. Pencatatan pembayaran akun nyata tidak dilakukan dalam smoke test.

Yang masih perlu dilengkapi: Transaksi Saya, nama menu Pesanan Saya, pembatalan mandiri
anggota untuk status Menunggu konfirmasi, telepon/alamat/nomor pada profil, validasi form
pendaftaran yang mempertahankan input, dan pemeriksaan visual mobile. Integrasi belum dipush.


## Penyelesaian fitur anggota — 17 November 2026

Perintah CMD: `venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider --tb=short`
dengan `SIKOS_ALLOW_MARIADB=1` dan URL database uji khusus dari .env (nilainya tidak dicetak).
Hasil akhir: **64 passed, 1 warning in 48.40s**; 59 SQLite/HTTP dan 5 MariaDB XAMPP.
Warning merupakan deprecation Starlette/httpx. MySQL 8 belum diuji.

Tambahan cakupan: privasi Transaksi Saya, snapshot setelah produk diedit, riwayat pembayaran
dan void, pembatalan mandiri pemilik hanya saat menunggu, CSRF/role, pagination/filter,
pendaftaran dengan input dipertahankan tanpa password, escaping input, profil atomic dan
perlindungan nomor/role, serta hitungan dashboard yang tidak memasukkan pesanan orang lain.
Tes MariaDB baru memakai dua koneksi untuk balapan pembatalan anggota versus konfirmasi
admin dan pembayaran versus pembatalan admin. Baris fixture dibersihkan di database uji.

Smoke browser memakai sesi anggota yang sudah login: menu/dashboard hitungan pribadi,
Pesanan Saya beserta tombol pembatalan menunggu, Transaksi Saya keadaan kosong, profil
lengkap dan form daftar dibuka. Katalog -> tambah air mineral 1 unit -> ubah menjadi 2 unit
(subtotal/total Rp7.000) -> Perbarui -> reload -> Hapus berhasil. Keranjang dipulihkan kosong.
Tidak membuat/membatalkan pesanan nyata atau mengubah profil/password nyata dalam smoke test.
Transaksi berisi barang serta checkout/pembatalan penuh diverifikasi melalui HTTP otomatis
dan tes database; belum ada smoke klik pembayaran nyata menggunakan akun admin.

Tampilan desktop dan breakpoint sempit diperiksa. Override layar 390x844 dipakai tetapi
browser melaporkan viewport efektif 582px; bukan bukti perangkat HP fisik/390 CSS px.
Screenshot layout sempit pesanan berhasil, tabel berada dalam kontainer scroll; lebar halaman
profil tidak melebihi viewport. Override dikembalikan ke ukuran awal. Screenshot lokal ada di
workspace kerja Codex, bukan menyimpan data pribadi ke repository.

Tidak ada migrasi skema tambahan pada penyelesaian anggota ini. Server berjalan di port 8001.
Perubahan belum dipush; pengiriman ke branch remote menunggu instruksi pengguna.

## Penyesuaian UI malam 17 November 2026

- Nomor anggota pada Profile berupa kolom disabled; backend tetap mengabaikan perubahan nomor/role dari pengguna.
- Kolom Role Akun dihapus dari form Profile.
- Tombol Keluar pada layout admin dan anggota memakai tema merah, termasuk hover dan fokus.
- Bagian Informasi Akun / Ringkasan Anggota di dashboard anggota dihapus, termasuk query jumlah produk/kategori yang tidak dipakai lagi.
- Sapaan, ringkasan status pesanan dan produk pilihan tetap tersedia. Identitas anggota dilihat melalui Profile.

Hasil pekerjaan malam ini mencakup integrasi cipa/luthfi, pembayaran tunai, penyelesaian
Transaksi Saya/pembatalan mandiri, perbaikan form akun/profil, optimasi query dan riwayat,
serta penyesuaian UI di atas. Perubahan dikumpulkan ke branch nayaa sesuai instruksi pengguna.
