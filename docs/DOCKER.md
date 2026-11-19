# Menjalankan SIKOS dengan Docker di Windows

Docker menjalankan aplikasi dan MySQL dalam container. Deployment lokal ini belum memberikan alamat internet publik. Untuk publik, gunakan server/VPS Docker dan domain dengan HTTPS.

## Berkas dan data

- `Dockerfile`: Python 3.12, aplikasi berjalan sebagai pengguna non-root.
- `compose.yaml`: FastAPI dan MySQL 8.4 dalam project `sikos-deploy`.
- `.env.docker`: password dan session secret privat; jangan unggah ke Git atau bagikan.
- Volume `sikos-deploy_sikos_mysql`: data MySQL permanen. Jangan gunakan `docker compose down -v`, karena menghapus volume database.
- Bukti pembayaran disimpan di database. Foto produk lokal disertakan dalam image aplikasi.
- Database Docker merupakan salinan database XAMPP saat backup. Perubahan berikutnya pada kedua database tidak otomatis tersinkron. Setelah berpindah, gunakan satu aplikasi sebagai sumber data utama.

## Jalankan dari CMD

Masuk dengan `cd /d "PATH_LENGKAP_FOLDER_SIKOS"` (gunakan kutip untuk spasi dan kurung siku), kemudian:

```cmd
docker compose --env-file .env.docker up -d --build
docker compose --env-file .env.docker ps
```

Buka http://127.0.0.1:8002. Akun yang dipulihkan dari backup tetap dapat dipakai. Tidak ada akun admin bawaan baru. Untuk instalasi kosong, buat admin interaktif:

```cmd
docker compose --env-file .env.docker exec web python -m app.cli create-admin
```

## Pembaruan dan rollback

1. Backup database Docker sebelum setiap perubahan skema. Backup XAMPP lama tidak mencakup transaksi baru di Docker.
2. Simpan versi kode atau tag Git dan image sebelumnya.
3. Tarik kode branch yang dipilih, jalankan tes dan bangun CSS jika berubah.
4. Jalankan `docker compose --env-file .env.docker up -d --build web`.
5. Periksa status, login, produk, pesanan, dan laporan. Startup menjalankan `init-db` yang tidak mereset database.

Untuk rollback kode, bangun ulang versi kode sebelumnya. Rollback skema mungkin memerlukan pemulihan backup database yang sesuai; jangan menimpa transaksi baru tanpa rencana pemulihan.

## Backup database Docker dari CMD

Simpan hasil di folder privat di luar repository:

```cmd
docker compose --env-file .env.docker exec -T db sh -c "MYSQL_PWD=$MYSQL_ROOT_PASSWORD exec mysqldump -uroot --single-transaction --quick --hex-blob --no-tablespaces --set-gtid-purged=OFF sikos" > "C:\LOKASI_BACKUP_PRIVAT\sikos-docker.sql"
```

Perintah di atas untuk CMD, bukan PowerShell. Periksa exit code dan ukuran file; uji restore ke database kosong terpisah. Cadangkan juga `.env.docker`, kode, foto, dan manifest hash. Password tidak perlu ditulis dalam perintah.

## Server publik

Pindahkan kode, backup database, dan konfigurasi privat melalui kanal aman ke server. Gunakan reverse proxy HTTPS; set `SIKOS_COOKIE_SECURE=1`. Jangan membuka port MySQL. Konfigurasi bawaan mengikat aplikasi ke loopback `127.0.0.1:8002` untuk reverse proxy pada host yang sama. Atur trusted proxy secara eksplisit jika diperlukan; jangan mempercayai header proxy dari semua alamat.

Sebelum publikasi, tentukan domain/server dan siapa yang boleh mengakses. Data backup mengandung akun dan transaksi; jangan menjadikan folder backup sebagai direktori web.

Referensi: https://docs.docker.com/compose/how-tos/startup-order/ , https://docs.docker.com/engine/storage/volumes/ , https://fastapi.tiangolo.com/deployment/docker/

## Tautan publik sementara
Jalankan scripts\public.cmd dari CMD setelah Docker berjalan. Skrip memakai .tools\cloudflared.exe dari rilis resmi Cloudflare. Biarkan terminal berjalan; Ctrl+C menghentikan tunnel. Link dapat berubah saat dijalankan ulang. Untuk HTTPS publik, gunakan SIKOS_COOKIE_SECURE=1 di .env.docker; sesi login melalui HTTP lokal tidak dapat dipakai dengan cookie Secure. Referensi: https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/ .


## Hasil deployment lokal 18 November 2026
Image web berhasil dibangun dengan requirements.lock. Tes Linux/container: 90 lulus; tes database nyata MySQL 9.4.0 pada sikos_test: 12 lulus. Backup XAMPP dipulihkan ke sikos pada container baru; jumlah baris 11 tabel cocok. Nama CHECK pada dump MariaDB dibuat unik untuk kompatibilitas MySQL; logika CHECK tidak berubah.

Karena unduhan MySQL 8.4 berulang kali timeout/EOF, deployment percobaan lokal memakai image MySQL 9.4.0 yang sudah tersedia dan dipatok digest melalui SIKOS_MYSQL_IMAGE di .env.docker. Container proyek lain tidak digunakan. Default Compose untuk instalasi baru tetap mysql:8.4. Jangan mengganti image database ke 8.4 dengan volume 9.4 yang sama; perpindahan versi memerlukan database/volume baru dan uji pemulihan SQL yang sesuai.

Tunnel sementara dijalankan terpisah di Windows. Docker restart tidak otomatis membuat tunnel. Jalankan scripts\public.cmd untuk membuat link baru setelah laptop dihidupkan kembali. Jangan menjalankannya dua kali jika tunnel sebelumnya masih aktif.

## Antarmuka database Docker lokal
Buka http://127.0.0.1:8082/ untuk phpMyAdmin khusus SIKOS Docker. Ini berbeda dari phpMyAdmin XAMPP di http://127.0.0.1/phpmyadmin/. Identitas server ditandai SIKOS Docker (data aplikasi port 8002).
Akun sikos_browser hanya memiliki SELECT dan SHOW VIEW pada sikos.*. Password acak disimpan pada SIKOS_DB_VIEWER_PASSWORD dalam .env.docker dan tidak ditampilkan. Antarmuka hanya terikat 127.0.0.1:8082 dan tidak diarahkan melalui tunnel publik. Perubahan data dilakukan melalui aplikasi SIKOS.
Untuk instalasi baru, jalankan python scripts/init-db-viewer.py setelah database Docker sehat. Lalu: docker compose --env-file .env.docker --profile tools up -d db-viewer . Profil tools bersifat opsional. Image phpMyAdmin lokal yang diuji dipatok digest agar tidak mengubah container proyek lain.
Verifikasi 19 November 2026: koneksi akun baca-saja berhasil, jumlah anggota 4, config PHP lolos lint, HTTP 200, tampilan tabel diperiksa melalui browser. MySQL dan aplikasi SIKOS tetap berjalan.
