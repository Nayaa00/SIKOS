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

Verifikasi terbaru 17 November 2026: 64 tes lulus (59 SQLite/HTTP dan 5 integrasi MariaDB XAMPP 10.4.32). Mencakup hak akses, privasi transaksi, validasi form, stok, snapshot, impor, laporan, pembatalan dan konkurensi nyata. MySQL 8 belum diuji. Lihat docs/HASIL_UJI.md untuk batas smoke test browser. Tidak ada kredensial akun nyata yang dibundel.


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

## Tugas 2: keranjang anggota

Keranjang menampilkan foto, kategori, harga satuan, stok, jumlah, subtotal dan total.
Tombol Hapus bekerja per barang, termasuk barang yang dinonaktifkan atau kehabisan stok.
Jumlah 0 juga menghapus barang saat diperbarui. Ringkasan berubah saat jumlah diketik;
server tetap menghitung harga dan total final. Checkout membaca jumlah terbaru langsung
dari formulir sehingga tidak perlu menekan Perbarui terlebih dahulu.

Perubahan keranjang divalidasi seluruhnya sebelum disimpan. Jika stok berubah atau barang
nonaktif, keranjang tetap tersedia dengan pesan kesalahan dan tidak ada pesanan parsial.
Submit ulang token pesanan yang sama tidak membuat pesanan kedua. Stok tidak berkurang
saat checkout; snapshot harga tetap dibuat di server saat pesanan berhasil dibuat.

Verifikasi 17 November 2026: 44 tes lulus, mencakup 41 tes SQLite/HTTP dan 3 tes integrasi
konkurensi MariaDB XAMPP pada database uji khusus. MySQL 8 belum diuji. Smoke test browser
halaman keranjang kosong berhasil; keranjang berisi barang dan tampilan HP belum diverifikasi
secara visual pada perubahan ini. Satu warning deprecation Starlette/httpx.

## Integrasi cipa terbaru — 17 November 2026

Branch sumber origin/cipa adc656a digabung ke Octavian lokal dengan mempertahankan
keranjang Tugas 2. Konflik sidebar dan CSS diselesaikan; CSS profil ditempatkan di luar
media query katalog, dan cache CSS diperbarui. Validasi email profil mengikuti kolom
190 karakter dan format email; password baru dibatasi 8–128 karakter.

Verifikasi: 43 tes SQLite/HTTP lulus. Percobaan awal 3 tes MariaDB error karena koneksi
terputus dan layanan XAMPP berhenti. Setelah pengguna menjalankan kembali layanan,
3 tes MariaDB diulang dan lulus (3.29 detik). Ini bukan pengujian MySQL 8. Halaman login
berhasil dibuka di browser; smoke test akun anggota/profil setelah login masih perlu
pengguna masuk sendiri. Tidak ada perubahan profil atau password akun nyata oleh agen.

Pekerjaan lanjutan: Transaksi Saya belum tersedia di cipa; Pesanan masih menggunakan
nama umum dan belum memiliki pembatalan mandiri anggota. Profil cipa mengubah nama,
email dan password, belum menyediakan telepon/alamat/nomor anggota. Progres luthfi
terlihat pada fetch tetapi belum digabung karena permintaan saat ini mengambil cipa.
Tidak ada push remote pada integrasi ini.

### Pembayaran tunai hasil integrasi luthfi

Admin dapat mencatat uang diterima dan kembalian pada Transaksi. Jalankan `python -m app.cli init-db`
atau `python -m app.cli migrate-payments` untuk database lama; migrasi hanya menambah kolom.
Pembayaran tidak mengubah stok atau snapshot. Pembatalan pesanan terkonfirmasi tetap membuat
transaksi tidak valid untuk analisis dan mengembalikan stok tepat sekali. Catatan uang diterima
historis tetap ada; belum tersedia pencatatan pengembalian uang.


## Penyelesaian fitur anggota (17 November 2026)

| Bagian | Hasil |
| --- | --- |
| Tugas 1: akun/katalog/dashboard | Daftar dengan error inline, input non-password dipertahankan, email duplikat spesifik, dashboard jumlah pesanan pribadi, navigasi aktif |
| Tugas 2: keranjang | Foto, ubah/hapus, total langsung, checkout memakai jumlah terbaru, validasi seluruh barang, token anti-duplikasi; smoke tambah/ubah/hapus berhasil |
| Tugas 3: pesanan/transaksi | Pesanan Saya dengan filter status dan 20 entri/halaman; pembatalan mandiri hanya Menunggu konfirmasi; Transaksi Saya privat, snapshot, status, nominal tunai/kembalian dan riwayat void |
| Profil | Nomor anggota/role hanya dilihat, edit nama/email/telepon/alamat, password lama dan konfirmasi untuk perubahan password; input non-password tetap pada error |
| Kinerja | Kategori produk dan rincian riwayat dimuat bersama untuk menghindari query per kartu/baris; query keranjang mengambil semua produk sekaligus |

Pembatalan anggota dan konfirmasi admin mengunci baris pesanan yang sama, sehingga hanya
status terbaru yang dipakai. Pembayaran/pembatalan mengunci order kemudian sale dengan
urutan konsisten. Stok, snapshot dan empat status PRD tetap dipertahankan.

Batas saat ini: pengembalian uang belum dicatat sebagai proses terpisah. Transaksi dibatalkan
yang sebelumnya dibayar menampilkan instruksi menghubungi koperasi, sambil mempertahankan
catatan pembayaran historis. Ini tidak mengubah aturan stok/analisis dan tidak menambah gateway.

### Pembayaran otomatis (18 November 2026)

Aturan ini menggantikan alur input uang manual sebelumnya. Di menu Pesanan, admin menekan
Selesaikan setelah pembayaran/penyerahan selesai. Sistem mencatat Lunas, uang diterima sama
dengan total, kembalian Rp0, dan waktu pembayaran otomatis. Form pembayaran manual di
Transaksi dihapus; halaman Transaksi Saya mengikuti hasil yang sama. Nominal pembayaran
lama yang sudah tercatat tidak ditimpa. Untuk pesanan lama yang Selesai namun belum punya
pembayaran, jalankan `python -m app.cli sync-completed-payments`. Stok tidak berubah saat Selesaikan.

## Notifikasi per akun

Notifikasi persisten per penerima untuk pesanan, pembayaran dan peringatan stok; lonceng,
riwayat, mark-read/mark-all, serta panel dashboard admin/anggota tersedia. Polling 15 detik
memperbarui UI tanpa refresh, dengan autentikasi, kepemilikan dan CSRF. Bukti pembayaran
anggota dapat diunggah sekali untuk pesanan Dikonfirmasi dan memicu notifikasi admin;
unggahan tidak membuat lunas. Migrasi additive: migrate-notifications. Notifikasi transaksi
lama tidak dibuat ulang. Rincian perilaku dan pengujian ada di README/HASIL_UJI.

## Tahap pertama HPP dan laba kotor

HPP produk per unit (opsional), snapshot saat konfirmasi, omzet/total HPP/laba kotor di
dashboard/laporan admin dan ekspor Excel tersedia. Data tanpa HPP diberi status belum
lengkap; null tidak dianggap nol, pembatalan dikeluarkan. Impor menerima hpp opsional.
Harga jual tetap snapshot saat pesan, stok dan empat status pesanan tidak berubah.
Biaya operasional/laba bersih belum termasuk tahap ini. Detail perilaku ada di README.

## Harga jual kategori dan HPP wajib

Pembaruan: HPP positif wajib pada form produk/impor; menggantikan aturan HPP opsional.
Harga jual otomatis = HPP ditambah markup kategori lalu dibulatkan ke atas kelipatan Rp100.
Admin dapat mengedit markup; perubahan menghitung ulang produk ber-HPP, tetap mempertahankan
snapshot pesanan. Default rekomendasi awal 10/20/25/15/10 untuk lima kategori utama; bukan
standar resmi pasar. Migrasi migrate-pricing tidak menebak HPP atau menimpa harga lama.
