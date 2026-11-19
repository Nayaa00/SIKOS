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

## Pembayaran otomatis saat Selesaikan — 18 November 2026

Klik Selesaikan pada pesanan Dikonfirmasi kini sekaligus mencatat pembayaran Lunas,
uang diterima sebesar total snapshot, kembalian 0 dan paid_at sama dengan completed_at.
Keduanya disimpan atomik dengan lock pesanan lalu transaksi. Klik berulang tidak mengubah
waktu/nominal lagi dan tidak mengurangi stok. Catatan pembayaran lama yang sudah Lunas
(dengan uang/kembalian aktual) tetap dipertahankan.

Form/kolom Aksi pembayaran di Transaksi dihapus. Endpoint manual lama menolak admin dengan
410 setelah pemeriksaan CSRF; pembeli tetap ditolak 403. Transaksi Saya mengikuti status baru.
Untuk data lama tersedia `python -m app.cli sync-completed-payments`: hanya transaksi valid,
Selesai, completed_at tersedia dan pembayaran benar-benar kosong yang diisi; aman diulang.
Pada database sikos lokal satu transaksi lama disinkronkan. Tidak ada gateway/transfer uang;
Selesaikan adalah keputusan admin bahwa pembayaran tunai dan penyerahan sudah selesai.

Verifikasi: suite 64 passed (59 SQLite/HTTP + 5 MariaDB) dalam 45.88 detik; setelah itu tes
MariaDB baru penyelesaian paralel 1 passed, 5 deselected. Total 65 skenario terverifikasi,
bukan satu eksekusi penuh 65 tes. MySQL 8 belum diuji. Snapshot, pembatalan, pembayaran lama,
sinkronisasi idempoten dan penutupan endpoint manual tercakup. Satu warning Starlette/httpx.

## Kolom Persediaan — 18 November 2026

Urutan setelah Produk: Stok Awal, Terjual, Stok Sesudah. Stok Awal diambil dari catatan
stok pertama produk pada seluruh riwayat (tidak hanya 300 baris yang ditampilkan), tetap
meskipun ada restok/penjualan. Terjual adalah unit pada masing-masing kejadian konfirmasi,
bukan total penjualan bersih; pembatalan tetap terlihat sebagai audit pengembalian.
Barang masuk/keluar manual dan pengembalian menampilkan 0 pada Terjual; delta aslinya tetap
ditampilkan di Alasan. Tidak ada perubahan data stok/audit. Untuk data lama tanpa catatan
stok awal, saldo sebelum pergerakan pertama digunakan sebagai saldo awal yang dapat ditelusuri.
Dua tes terarah lulus: halaman admin dan skenario stok awal, penjualan, restok, rusak, pembatalan.

## Validasi Cash sebelum Selesaikan — 18 November 2026

Alur ini menggantikan pencatatan otomatis sebesar total pada aksi Selesaikan. Admin membuka
/pesanan/{id}/selesaikan dan memilih Cash/Cashless. Cash aktif: isi Uang Pembayaran dalam
rupiah bulat, Kembalian readonly otomatis = uang pembayaran - total snapshot. Cashless
terlihat dalam pilihan tetapi belum dapat diproses. Server menolak metode lain, nominal
kurang, pecahan dan nominal melewati batas. Nilai kembalian dari browser tidak dipercaya.
Pembayaran dan status Selesai disimpan satu transaksi dengan lock order lalu sale;
stok tidak dikurangi lagi. Pembayaran lama lunas tidak ditimpa. Endpoint POST status Selesai
wajib menyertakan metode Cash dan jumlah_bayar. Menutup/kembali dari form tidak mengubah pesanan.

Tes suite: 68 passed, 1 warning dalam 53.35 detik (62 SQLite/HTTP + 6 MariaDB). Setelahnya
tes Cash paralel MariaDB baru lulus (1 passed, 6 deselected); 69 skenario terverifikasi
lintas dua eksekusi. MySQL 8 belum diuji. Tidak memproses uang nyata saat pengujian.

## Cashless dengan bukti pembayaran — 18 November 2026

Form penyelesaian kini mendukung Cashless: Ambil Foto (getUserMedia dengan izin kamera)
atau Unggah Gambar, pratinjau, dan konfirmasi wajib bahwa uang masuk/nominal sudah diperiksa
admin. Kamera berhenti saat ditutup, selesai mengambil foto, pindah metode, atau meninggalkan
halaman. Jika kamera tidak tersedia/izin ditolak, unggah gambar tetap dapat digunakan.
Bukti bukan verifikasi otomatis dari GoPay/bank; tidak ada gateway/API pembayaran eksternal.

Server memvalidasi gambar JPEG/PNG/WebP maksimal 5 MB dan 20 megapiksel, menormalkan ke JPEG
(tanpa metadata asli). Bukti disimpan sebagai MEDIUMBLOB privat/deferred di sales, disertai ID
admin pemeriksa. Tidak masuk folder static atau Git. Rute /transaksi/{sale_id}/bukti khusus
admin, no-store dan nosniff. Pembeli tidak dapat melihat bukti. Pada Transaksi tersedia metode
pembayaran dan Lihat bukti. Cashless mencatat nominal total, kembalian 0, status Lunas dan
pesanan Selesai secara atomik; submit ulang tidak menimpa bukti/pembayaran. Stok tetap.

Migrasi tambahan `python -m app.cli migrate-payments` sudah dijalankan pada database sikos,
hanya menambah payment_proof dan payment_verified_by; data lama tidak direset. Pillow ditambah
ke requirements. Untuk komputer anggota tim jalankan pip install -r requirements.txt lalu
migrate-payments sebelum menyalakan server.

Tes penuh: 71 passed, 1 warning dalam 51.03 detik (64 SQLite/HTTP + 7 MariaDB). Setelahnya
1 tes MariaDB baru bukti Cashless lulus (1 passed, 7 deselected), sehingga 72 skenario
terverifikasi lintas dua eksekusi. MySQL 8 belum diuji. Tes meliputi konfirmasi wajib,
file palsu/ukuran, bukti privat, pembayaran idempoten serta penyimpanan blob pada MariaDB.
Smoke browser: form Cashless beserta tombol foto/unggah, checkbox dan tombol simpan nonaktif
sebelum bukti/konfirmasi terlihat. Kamera fisik tidak diaktifkan dan tidak ada pembayaran nyata
disimpan. Jalur izin/perangkat kamera perlu dicoba pengguna; upload end-to-end diuji via HTTP.

### Penyederhanaan form bukti Cashless

Input file bawaan disembunyikan; pilih bukti melalui Unggah Gambar atau Ambil Foto.
Checkbox konfirmasi dihapus sesuai permintaan pengguna. Submit Simpan & selesaikan oleh
admin yang terautentikasi dianggap pernyataan pembayaran sudah diterima/nominal sesuai.
Bukti valid tetap wajib dan pemeriksa tercatat; tidak ada verifikasi otomatis ke bank.
Tes HTTP unggah Cashless tanpa checkbox lulus, termasuk privasi/idempotensi. Ini menggantikan
ketentuan checkbox pada catatan sebelumnya.

### Penyelesaian UI dan pengumpulan progres ke dzikri

Teks petunjuk kecil Cashless yang ditandai pengguna dihapus; pesan validasi kesalahan
masih tampil. Input bawaan Choose File disembunyikan, checkbox tidak digunakan, dan tombol
Simpan & selesaikan menjadi konfirmasi admin. Bukti gambar tetap wajib dan aksesnya khusus admin.
Progres yang dikumpulkan juga mencakup tabel Persediaan, CardView khusus impor, form Cash
beserta kembalian, Cashless dengan foto/unggah bukti, migrasi, dependency dan pengujian.

Verifikasi final sebelum push dzikri: 72 passed, 1 warning dalam 63.44 detik,
terdiri dari 64 tes SQLite/HTTP dan 8 tes MariaDB XAMPP. MySQL 8 belum diuji.

## Desain Tailwind lintas halaman — 18 November 2026

Branch codex/tailwind-ui memakai Tailwind build lokal untuk layout dan sistem komponen
seluruh halaman. Bootstrap sudah dilepas dari base. CSS historis ada di layer legacy untuk
layout widget, desain baru di layer components/utilities. Backend, stok, pembayaran dan
schema database tidak diubah oleh migrasi tampilan ini. Build berhasil; 72 tes lulus,
termasuk 8 MariaDB XAMPP (56.58 detik). Lihat docs/TAILWIND.md untuk setup, batas verifikasi
visual dan peringatan dependency build. Tidak ada push pada tahap ini.

## Notifikasi admin dan anggota — 18 November 2026

78 tes lulus (69 SQLite/HTTP + 9 MariaDB XAMPP), 1 warning deprecation, 53.53 detik.
MySQL 8 belum diuji. Tes baru meliputi privasi feed/mark-read/gambar bukti, CSRF, pembacaan
idempoten, mark-all berbatas snapshot (notifikasi yang baru datang tidak ikut terbaca),
rollback bisnis, stok menipis/habis, notifikasi konfirmasi ganda pada konkurensi MariaDB,
serta bukti anggota tidak melunaskan pembayaran dan bisa dipakai ulang oleh admin.

Pemeriksaan JavaScript dengan Node: polling memperbarui badge/list, pause/resume tab,
render teks tanpa HTML injection, dan pembersihan daftar ketika akun berubah. Syntax JS
lulus dan Tailwind berhasil dibangun. Tes regresi riwayat transaksi tetap memeriksa bahwa
pesanan menunggu tidak masuk catatan transaksi, sementara bell boleh menampilkan notifikasi
pesanan menunggu milik akun sendiri. Dashboard kini diharapkan menampilkan notifikasi sendiri.

Smoke test browser sesi admin: lonceng buka/tutup, empty state, tautan Riwayat dan halaman
notifikasi tampil sesuai tema. Endpoint polling di server lokal mengembalikan 200. Tidak
membuat pesanan, pembayaran atau notifikasi dummy di database operasional. Alur anggota,
pengajuan bukti dan mark-read diuji HTTP; belum smoke test visual dengan sesi anggota.
Migrasi dua tabel sudah dijalankan pada database SIKOS lokal. Tidak mengubah database lain.

## Integrasi terpilih ke luthfi — 18 November 2026

Branch luthfi sebelumnya berada di 005bcfe. Fondasi SIKOS terintegrasi dan Tailwind lokal
(commit 30029a7) digabungkan sebagai prasyarat. Di atas fondasi tersebut hanya ditambahkan
notifikasi, pengajuan bukti anggota yang memicu notifikasi, dan perapian kartu produk,
katalog/Produk Pilihan serta padding kartu transaksi anggota. Redesign workspace/sidebar,
susunan dashboard admin terbaru dan perubahan grafik tidak disertakan pada integrasi ini.

Worktree integrasi: build Tailwind berhasil, syntax JS lulus, 78 tes lulus dalam 62.19 detik
(69 SQLite/HTTP + 9 MariaDB XAMPP, 1 warning deprecation). MySQL 8 belum diuji. Tidak mengubah
.env atau database operasional saat pengujian; database nyata memakai URL khusus _test.

## Integrasi sisa tampilan ke Octavian — 18 November 2026

Meneruskan fondasi branch luthfi (daa624c) dengan redesign workspace/sidebar, navigasi
responsif, susunan dashboard admin, ringkasan pesanan, tata letak profil/persediaan, dan
grafik Garis/Batang bergradasi. Tidak menghapus fitur notifikasi dan perapian kartu yang
sudah masuk luthfi. Branch tujuan adalah Octavian; pian tidak dibuat di remote.

Hasil pada worktree integrasi: 78 tes lulus dalam 59.64 detik (69 SQLite/HTTP dan 9 MariaDB
XAMPP), 1 warning deprecation. MySQL 8 belum diuji. Pemeriksaan JavaScript grafik dan
notifikasi lulus. CSS hasil build yang sudah diverifikasi di folder utama disertakan.


## HPP dan laba kotor tahap pertama — 18 November 2026

84 tes lulus dalam 62.35 detik: 74 SQLite/HTTP dan 10 MariaDB XAMPP, 1 warning deprecation.
MySQL 8 belum diuji. Tes tambahan memeriksa snapshot HPP saat konfirmasi, perubahan HPP
produk sesudahnya, konfirmasi ulang dan konkurensi MariaDB, pengecualian pembatalan,
perbedaan null/biaya nol, laba negatif, validasi dan hak akses admin, ekspor HPP/laba,
kolom HPP impor opsional serta migrasi additive idempoten yang mempertahankan null historis.

Build Tailwind berhasil. Smoke test browser admin: ringkasan omzet/HPP/laba kotor dan
status Belum lengkap pada laporan transaksi lama tampil, kolom HPP dan harga jual terpisah
terlihat pada form edit produk. Tidak menyimpan perubahan produk, HPP atau transaksi
operasional saat smoke test. Migrasi dua kolom nullable sudah dijalankan pada database
SIKOS lokal. HPP produk dan snapshot lama tidak diisi otomatis. Belum di-push ke GitHub.

## Markup kategori dan pembulatan otomatis — 18 November 2026

93 tes lulus (83 SQLite/HTTP + 10 MariaDB XAMPP), 1 warning deprecation, 59.75 detik.
MySQL 8 belum diuji. Setelah penyederhanaan header Excel, 16 tes impor/pricing terkait
juga lulus (6.98 detik). Tes memastikan HPP positif wajib, nominal harga palsu diabaikan,
pembulatan integer/Decimal, batas markup, repricing kategori dan snapshot pesanan tetap,
serta migrasi idempoten yang mempertahankan persentase khusus dan harga produk lama.
Kasus lama yang menerima HPP nol/kosong untuk penyimpanan baru disesuaikan dengan aturan
baru; snapshot historis nol/null tetap ditangani sebagai sebelumnya.

Smoke test browser admin: kategori menampilkan default 10/20/25/15/10; form tambah produk
memilih Makanan ringan 25% dan HPP 3000 menampilkan harga otomatis 3800. Tidak menyimpan
produk, kategori atau transaksi operasional saat smoke test. Syntax product-pricing.js lulus.
Migrasi markup dijalankan pada database SIKOS lokal; harga lama tidak ditulis ulang.
Belum di-push ke GitHub.

## Integrasi HPP dan markup ke cipa — 18 November 2026

Dasar integrasi f0933cc (Octavian), yang sudah mencakup riwayat cipa sebelumnya, agar
fitur notifikasi dan tampilan tetap tersedia. Penambahan: HPP/modal wajib, snapshot saat
konfirmasi, laporan omzet/HPP/laba kotor, ekspor Excel, persentase markup kategori dan
pembulatan harga jual ke atas kelipatan Rp100. Harga jual manual diabaikan oleh server.

Instalasi lama perlu menjalankan migrate-hpp dan migrate-pricing, lalu restart server;
init-db juga mencakup migrasi tersebut. Data historis tidak diberi HPP fiktif dan migrasi
tidak menulis ulang harga produk lama. Folder kerja utama dan branch main tetap.

Verifikasi worktree cipa: 93 tes lulus dalam 61.96 detik (83 SQLite/HTTP dan 10 MariaDB XAMPP), 1 warning deprecation. MySQL 8 belum diuji. Syntax product-pricing.js dan git diff --check lulus.


## Biaya operasional dan estimasi HPP awal — 18 November 2026

97 tes lulus dalam 80.93 detik: 86 SQLite/HTTP dan 11 MariaDB XAMPP, 1 warning deprecation.
MySQL 8 belum diuji. Tes meliputi total/laba bersih pada empat periode WIB, biaya dibatalkan
idempoten, periode tanpa penjualan menghasilkan rugi, HPP historis belum lengkap, hak akses
anggota, CSRF, token anti-duplikasi, ekspor biaya/net profit, persistensi/void MariaDB,
serta inisialisasi HPP hanya pada NULL dengan harga/stok/HPP lama/snapshot tetap.

Pengisian data operasional yang diotorisasi: 31 produk, 29 HPP kosong diisi estimasi dan
2 HPP yang sudah terisi dipertahankan. Nol HPP NULL tersisa. Backup JSON di luar Git proyek
tersedia sebelum commit transaksi. Harga jual, stok dan snapshot diperiksa sama sebelum
dan sesudah. Tidak membuat biaya operasional atau transaksi palsu di database operasional.

Smoke test browser admin: navigasi Biaya Operasional, form tanggal/kategori/nominal/
keterangan, empty state riwayat, serta ringkasan biaya dan laba bersih pada laporan tampil.
Tidak menyimpan form biaya atau mengubah transaksi saat smoke test. Migrasi satu tabel
biaya dan dua penanda estimasi dijalankan di database SIKOS lokal. Build Tailwind lulus.
Belum di-push ke GitHub.

## Total HPP historis dan simulasi bulanan — 18 November 2026

101 tes lulus dalam 70.03 detik (89 SQLite/HTTP + 12 MariaDB XAMPP), 1 warning deprecation.
MySQL 8 belum diuji. Tes tambahan: snapshot NULL saja diisi estimasi/idempoten termasuk
persistensi MariaDB, HPP yang sudah ada/harga/jumlah/stok tetap, total HPP menjadi lengkap,
rumus BEP/margin/markup minimal dan skenario rugi/markup nol, rencana khusus admin dan
tidak menambah ledger biaya nyata, serta hilangnya kartu laba kotor.

Data operasional yang diotorisasi: 10 baris snapshot HPP historis kosong diisi estimasi;
backup JSON tersimpan di luar Git. Tidak mengubah harga, jumlah, subtotal, total atau status.
Smoke test browser admin: laporan menampilkan total HPP numerik dan laba bersih beserta
penanda estimasi, empat kartu tanpa kartu laba kotor, serta contoh biaya Rp1.500.000,
target Rp20.000.000, BEP Rp16.500.000 dan proyeksi Rp318.181. Tidak menyimpan rencana atau
membuat biaya/transaksi dummy saat smoke test. Harga produk tidak diubah oleh simulasi.
Build Tailwind berhasil. Belum di-push ke GitHub.

## Pembaruan biaya operasional ke cipa — 18 November 2026

Integrasi melanjutkan commit 340e07c pada cipa. Memuat menu biaya operasional, laba bersih
tercatat, sumber HPP estimasi, perintah pengisian HPP produk/historis kosong secara eksplisit,
serta simulasi rencana bulanan/BEP. Migrasi untuk instalasi lama: migrate-expenses, restart.
Rencana simulasi tidak menjadi expense dan tidak mengubah harga jual otomatis. Backup dan
isi database lokal tidak disertakan dalam Git; perintah pengisian data tidak dijalankan
secara otomatis setelah pull. Snapshot HPP yang sudah ada dipertahankan.

Verifikasi worktree cipa: 101 tes lulus dalam 82.53 detik (89 SQLite/HTTP + 12 MariaDB XAMPP), 1 warning deprecation. MySQL 8 belum diuji. git diff --check lulus.

## Tampilan mobile 390 x 844 (18 November 2026)
- Penyesuaian CSS dibatasi layar maksimal 480 px; tampilan laptop dipertahankan.
- Kartu produk dua kolom, profil rata tengah, kartu tindak lanjut lebih ringkas, dan banner anggota memakai tema bersama.
- Build Tailwind berhasil. Pengujian integrasi worktree: 102 passed, termasuk suite database MariaDB XAMPP (bukan MySQL 8).
- Pratinjau browser memakai bingkai 390 x 844; pemeriksaan visual katalog anggota terbatas karena sesi browser admin.

## Deployment Docker (18 November 2026)
- 90 tes aplikasi lulus di image Python 3.12 Linux dengan SQLite terisolasi.
- 12 tes database nyata lulus pada MySQL 9.4.0 Docker, database sikos_test terpisah.
- Restore backup database XAMPP ke database Docker baru berhasil; jumlah baris 11 tabel cocok. CHECK bernama sama diberi nama unik untuk kompatibilitas MariaDB/MySQL.
- Compose web/db healthy. Halaman login HTTPS publik HTTP 200, cookie Secure, dan tampilan login diperiksa melalui browser. Alur login dengan akun asli belum diuji manual di alamat publik.
- Unduhan 8.4 gagal karena TLS timeout/EOF; runtime percobaan memakai image lokal MySQL 9.4.0 dipatok digest. Bukan deployment hosting permanen.

## Finalisasi main (19 November 2026)
- Seluruh 102 tes lulus pada worktree main: 90 tes aplikasi/SQLite dan 12 tes MariaDB XAMPP pada database khusus pengujian. Ini bukan pengulangan tes MySQL Docker; 12 tes MySQL 9.4 Docker sebelumnya juga lulus sebagaimana catatan deployment.
- Antarmuka database Docker lokal http://127.0.0.1:8082 memakai akun sikos_browser dengan SELECT dan SHOW VIEW pada sikos.*; koneksi dan hak baca-saja diverifikasi.
- Docker Compose lolos validasi dengan profil tools; konfigurasi PHP lolos lint dan tampilan tabel phpMyAdmin Docker diperiksa melalui browser.
- Pemindaian nilai konfigurasi privat pada file baru lolos. File .env, .env.docker, dump database, backup dan executable lokal tidak ikut commit.
