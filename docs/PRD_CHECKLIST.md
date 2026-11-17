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
