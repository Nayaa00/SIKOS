# Mulai mengembangkan tampilan dengan Tailwind

Branch awal migrasi: codex/tailwind-ui, dari progres dzikri yang sudah dipush.
Tahap pertama memigrasikan layout sidebar/topbar bersama dan Dashboard Anggota.
FastAPI, MySQL, endpoint, validasi dan alur stok/pembayaran tetap menggunakan implementasi sebelumnya.

## Build CSS di Windows CMD

Dari folder sikos (gunakan cd /d "PATH_FOLDER_SIKOS" agar path spasi/kurung siku aman):

```cmd
npm ci
npm run build:css
```

Node hanya diperlukan untuk mengubah/build CSS. CSS hasil build app/static/tailwind.css
ikut disimpan di Git, jadi menjalankan FastAPI tidak memerlukan Node/npm.
Gunakan Node 24+ untuk tool npm lokal yang digunakan pada komputer ini.

Jika npm belum terpasang tetapi node tersedia, gunakan npm lokal khusus proyek:

```cmd
venv\Scripts\python.exe scripts\bootstrap_npm.py
scripts\npm.cmd ci
scripts\npm.cmd run build:css
```

Bootstrap npm mengunduh paket dari registry resmi, memeriksa checksum SHA-512 dan
menyimpannya di .tools/npm (diabaikan Git), tanpa pemasangan global Windows.
Untuk mengembangkan CSS sambil berjalan:

```cmd
scripts\npm.cmd run watch:css
```

Biarkan terminal watch terbuka. Jalankan uvicorn di terminal CMD lain seperti biasa.
Setelah mengubah kelas template, build CSS dan refresh browser; Ctrl+F5 bila masih tercache.
Sebelum commit jalankan build:css dan sertakan package-lock.json serta CSS hasil build.
node_modules dan .tools tidak boleh ikut commit.

## Pola styling

- Sumber Tailwind: assets/tailwind.css. Hasil build: app/static/tailwind.css.
- Template menggunakan prefix tw:, misalnya tw:rounded-2xl tw:bg-white tw:p-6.
- Responsif: tw:sm:grid-cols-2, tw:lg:grid-cols-4. Tulis nama kelas lengkap di Jinja.
- Warna: emerald untuk identitas koperasi, lime untuk aksen, stone untuk latar, red untuk logout.
- Hindari membentuk kelas dinamis seperti tw:bg-{{ warna }}. Pilih string kelas lengkap.
- Komponen berulang memakai macro/partial Jinja; navigasi bersama ada pada macro nav_link di base.html.

## Batas transisi

Bootstrap dan app.css masih dimuat untuk halaman lama. Tailwind tidak mengimpor Preflight,
memakai prefix tw:, serta important utilities agar hanya elemen yang sengaja dimigrasikan
yang menimpa CSS lama. Jangan menghapus stylesheet lama sebelum semua pemakainya dimigrasi.
Halaman selanjutnya yang disarankan: Katalog/Produk, lalu Keranjang, Pesanan, Profil,
Transaksi, Persediaan/Impor dan Laporan. Migrasikan dan periksa satu kelompok per perubahan.
Periksa form, tabel lebar, state kosong/error, tombol disabled, fokus keyboard dan layar sempit.

Mengganti kelas tidak boleh menghapus input CSRF, mengganti route/action form, mengubah
role yang berhak mengakses menu, atau mengubah data/stok/transaksi. Pengujian Python tetap dijalankan.

## Verifikasi tahap awal

Build lokal Tailwind berhasil. Suite Python 72 passed, 1 warning (63.99 detik), termasuk
8 integrasi MariaDB XAMPP; MySQL 8 belum diuji. Layout bersama diperiksa melalui sesi admin
aktif di browser. Dashboard Anggota tercakup pada pengujian HTTP; pemeriksaan visual dengan
sesi anggota masih perlu dilakukan setelah pengguna masuk sebagai anggota.

npm audit melaporkan 4 high pada rantai development-only CLI/watcher/picomatch.
npm audit fix sudah dicoba tetapi peringatan tetap ada. Registry saat pemeriksaan menyediakan
picomatch 4.0.7; versi patch 4.0.8 belum tersedia. Tidak melakukan force fix atau mengubah
kode dependency secara manual. Tool Node hanya untuk build; browser memuat CSS hasil build.
Periksa kembali npm audit dan patch dependency saat tersedia sebelum deployment publik.

## Pembaruan desain lintas halaman

Bootstrap CDN dan link langsung app.css sudah dihapus dari base.html. Stylesheet runtime
utama adalah app/static/tailwind.css. app.css masih diimpor pada layer legacy di sumber
Tailwind untuk geometri widget khusus; @apply pada layer components mengatur desain aktif
kartu, tabel, form, tombol, badge, katalog/produk, keranjang, profil, impor dan halaman akun.
Ini adalah migrasi desain lintas halaman, bukan penghapusan seluruh selector historis.

Dashboard admin mendapat hero hijau gelap, kartu ringkasan dan filter periode baru.
Form memakai fokus keyboard konsisten, status memakai warna semantik, tabel lebar dapat
digulir dalam kartu. Prefers-reduced-motion dan atribut hidden dipertahankan eksplisit.

Verifikasi setelah Bootstrap dilepas: 72 passed, 1 warning dalam 56.58 detik (64 SQLite/HTTP
+ 8 MariaDB XAMPP). MySQL 8 belum diuji. Browser sesi admin: dashboard, produk, kategori,
impor, laporan dan form tambah produk diperiksa tanpa menyimpan data. Layout sempit laporan
juga diperiksa, kemudian override viewport dikembalikan. Browser melaporkan viewport efektif
sekitar 582px pada override 390, sehingga bukan bukti perangkat fisik 390 CSS px. Pemeriksaan
visual sesi anggota masih perlu dilakukan; alur anggota tercakup pada tes HTTP.

Gunakan CSS komponen pada assets/tailwind.css untuk perubahan lintas halaman. Untuk perubahan
khusus elemen, gunakan utility tw: pada template. Rebuild hasil CSS setiap selesai perubahan.
