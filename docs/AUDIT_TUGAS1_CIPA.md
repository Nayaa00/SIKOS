# Audit Tugas 1 dari branch cipa

Tanggal: 17 November 2026. Sumber: origin/cipa pada 8f46bc9; digabung fast-forward ke dzikri lokal.

Sudah tersedia:
- Login email/password, logout, role anggota, pendaftaran dengan nomor anggota otomatis.
- Dashboard anggota dan katalog kartu produk dengan foto, label, kategori, harga, stok.
- Pencarian nama/label dan filter kategori; produk nonaktif disembunyikan dan stok habis tidak dapat ditambahkan.
- Pembatasan akses admin/anggota.

Perbaikan integrasi setelah penggabungan:
- Memulihkan GET /daftar yang hilang.
- Menambahkan konfirmasi password pada form daftar; validasinya khusus pendaftaran agar CRUD anggota admin tetap bekerja.
- Memulihkan tautan atribusi foto dan fallback gambar dashboard.
- Menambahkan pengujian regresi pendaftaran, duplikasi email, role, dashboard, dan katalog.

Yang masih perlu diselesaikan atau diputuskan untuk Tugas 1:
1. Tujuan login: rancangan awal langsung ke katalog, implementasi cipa menuju dashboard anggota. Tentukan alur final sebelum menyatakan sesuai rancangan.
2. Navigasi: dashboard anggota belum mempunyai tautan sidebar; penanda menu aktif belum tersedia untuk menu anggota, dan tulisan Pesanan belum menjadi Pesanan Saya.
3. Validasi form: kesalahan masih membuka halaman error umum; nilai input belum dipertahankan dan pesan email duplikat masih menyebut beberapa jenis duplikasi lain.
4. Tampilan login/daftar belum diselaraskan dengan tampilan baru dashboard/katalog.
5. Smoke test browser dengan akun pembeli dan pemeriksaan tampilan seluler belum dilakukan pada hasil gabungan ini. Pengujian HTTP otomatis tidak menggantikan pemeriksaan visual tersebut.

Keranjang/checkout adalah Tugas 2. Pesanan dan transaksi pengguna adalah Tugas 3; bukan kekurangan Tugas 1.

Validasi: 40 tes lulus (37 tes SQLite/HTTP dan 3 tes integrasi konkurensi pada MariaDB XAMPP dengan database uji khusus). Tidak mengklaim pengujian MySQL 8. Satu warning deprecation Starlette/httpx. git diff --check bersih.

Penggabungan dan perbaikan disimpan di branch lokal dzikri; belum dipush ke remote.
