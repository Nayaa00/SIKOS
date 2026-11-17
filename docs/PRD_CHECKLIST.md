# Pemetaan PRD SIKOS 1.0 ke implementasi

Acuan: PRODUCT REQUIREMENTS DOCUMENT.docx yang dilampirkan pengguna. Isi identik dengan salinan bernama PRODUCT REQUIREMENTS DOCUMENT(1).docx.

| Kebutuhan | Implementasi | Pengujian / catatan |
| --- | --- | --- |
| FR-01 email/password, admin/anggota | /login, /logout, /daftar, dependency current/admin | Hash PBKDF2, CSRF, role, password salah, akses anonim |
| FR-02 CRUD anggota dan nomor unik | /anggota, form edit/tambah | Nomor/email unik di DB. Hapus menonaktifkan akun, riwayat tetap ada |
| Manajemen kategori | /kategori | Tambah, edit, aktif/nonaktif. Kategori nonaktif disembunyikan dari katalog |
| FR-03 produk | /produk | Kode unik, kategori, harga, stok, satuan, deskripsi, gambar opsional melalui URL HTTPS. Hapus berupa arsip |
| FR-04 impor Excel | /impor + /impor/template | Pandas + openpyxl. Header/angka/kosong/duplikat/formula. Baris valid disimpan, gagal diberi nomor baris dan alasan |
| FR-05 stok | /stok + services.movement | Masuk/keluar manual, audit actor/delta/stok akhir/alasan/pesanan. Row lock MySQL |
| FR-06 katalog | /katalog | Harga/stok/kategori, pencarian, filter kategori, stok habis |
| FR-07 keranjang/pesan | /keranjang dan /pesanan/buat | Multi-produk, ubah/hapus qty, subtotal/total dihitung server, stok diperiksa kembali |
| FR-08 transaksi/status | /pesanan dan /transaksi | Menunggu konfirmasi → Dikonfirmasi → Selesai atau Dibatalkan. Kurangi stok tepat sekali saat konfirmasi. Void dan kembalikan tepat sekali saat batal |
| FR-09 produk terlaris | Dashboard + laporan, analytics.analyze | Pandas groupby kode, sum unit, sort desc, filter periode, hanya Sale.valid |
| FR-10 stok tertinggi | Dashboard | Query stok terbaru produk/kategori aktif, lima teratas |
| FR-11 laporan | /laporan | Empat periode, jumlah transaksi unik, jumlah unit, omzet, rincian produk, grafik Chart.js, ekspor Excel |
| ETL dan analisis | importer.py + analytics.py | Extract workbook/transaksi, transform/validasi/normalisasi, load SQL, analisis Pandas |
| Keamanan | security.py + dependency admin | Hash password, signed HttpOnly session cookie, CSRF, validasi server, anggota hanya melihat pesanan sendiri |
| Integritas | services.py + constraint DB | Transaksi SQL, FK, unique, stok nonnegatif, row lock MySQL untuk pesanan/produk |
| Teknologi PRD | FastAPI, MySQL, Jinja HTML/CSS/Bootstrap/JS, Pandas/openpyxl, Chart.js | SQLite hanya backend pengujian otomatis portabel, bukan pilihan utama proyek |

## Keputusan implementasi dari hal yang belum ditetapkan PRD

1. Studi kasus memakai Koperasi Sejahtera, nama aplikasi SIKOS.
2. Laporan menghitung transaksi Dikonfirmasi dan Selesai, memakai waktu konfirmasi. Pembatalan membuat transaksi tidak valid dan mengeluarkannya dari laporan, termasuk periode konfirmasi sebelumnya.
3. Harga dikunci saat pesanan dibuat. Stok tidak direservasi pada tahap menunggu. Bila dua anggota memesan stok terakhir, admin hanya dapat mengonfirmasi yang masih tersedia. Konfirmasi kedua ditolak tanpa perubahan parsial.
4. Pembayaran dicatat secara operasional melalui konfirmasi admin dan penyelesaian pesanan; belum ada gateway atau pencatatan kas terpisah karena PRD tidak merincinya.
5. Hapus anggota, kategori, dan produk adalah soft delete. Data dapat diaktifkan kembali lewat edit. Pesanan dan audit historis tetap dipertahankan.
6. Impor Excel hanya membuat kode produk baru. Produk berkode sama dalam file/database dilaporkan gagal, tidak menimpa stok berjalan. File Excel lama belum diberikan, sehingga pemetaan header spesifik masih perlu disesuaikan setelah file tersedia.
7. Gambar opsional diinput berupa URL HTTPS. Upload file gambar tidak diwajibkan PRD.
8. Rupiah disimpan integer, tidak menggunakan float untuk nilai transaksi. Minggu mulai Senin dan waktu laporan WIB.
9. Tidak menambahkan Spark/Hadoop, payment gateway, aplikasi mobile atau multi-cabang. Pandas dan grafik merupakan analisis skala praktikum, bukan bukti pemrosesan Big Data berskala besar.
10. Template UI menggunakan CDN untuk Bootstrap dan Chart.js. CSS lokal membuat form/tabel tetap dapat dipakai tanpa Bootstrap. Grafik memerlukan internet; tabel dan ekspor tetap tersedia.

## Verifikasi dan keterbatasan

Pengujian otomatis 22 skenario SQLite (ditambah 2 skenario integrasi MySQL opsional) memakai SQLite temporer dengan tabel SQLAlchemy yang sama. Cakupan mencakup service bisnis, rollback, status, idempotensi, impor parsial, akun, role, CSRF, halaman, keranjang, transaksi, batas periode dan ekspor.

MariaDB XAMPP 10.4.32 telah diuji dengan dua koneksi dan smoke test navigasi/empty state browser telah dilakukan. MySQL 8 nyata belum diuji. Lihat docs/HASIL_UJI.md untuk hasil dan batas verifikasi. Tidak ada kredensial atau data pribadi yang dibundel.


## Akses pembeli dan pengaturan kategori

Katalog, Keranjang dan pembuatan pesanan khusus anggota/pembeli. Menu tersebut
tidak ditampilkan kepada admin dan akses langsung GET/POST ditolak 403. Admin
tetap mengelola barang melalui Produk dan memproses Pesanan/Transaksi/Laporan.

Halaman Kategori menampilkan nama sebagai teks biasa. Form tambah dan pengubahan
nama dihapus; admin hanya mengatur status aktif/nonaktif lalu Simpan. Request dari
form Tambah versi lama diarahkan kembali dengan pemberitahuan tanpa membuat data
duplikat. Dropdown pemilihan kategori di form produk tetap tersedia.
