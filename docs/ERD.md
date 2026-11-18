# ERD SIKOS

```mermaid
erDiagram
    USERS ||--o{ ORDERS : membuat
    USERS ||--o{ STOCK_MOVEMENTS : mencatat
    CATEGORIES ||--o{ PRODUCTS : mengelompokkan
    PRODUCTS ||--o{ ORDER_LINES : dipesan
    PRODUCTS ||--o{ STOCK_MOVEMENTS : memiliki
    ORDERS ||--|{ ORDER_LINES : berisi
    ORDERS ||--o| SALES : dikonfirmasi
    ORDERS ||--o{ STOCK_MOVEMENTS : memicu
    USERS {
        int id PK
        string nomor UK
        string nama
        string email UK
        string password_hash
        string telepon
        string alamat
        string role
        boolean active
    }
    CATEGORIES {
        int id PK
        string nama UK
        string code_prefix UK
        int code_counter
        boolean active
    }
    PRODUCTS {
        int id PK
        string kode UK
        string source_code UK
        string label
        int category_id FK
        string nama
        bigint harga
        int stok
        string satuan
        string deskripsi
        string gambar
        boolean active
    }
    ORDERS {
        int id PK
        string kode UK
        int member_id FK
        string token
        string status
        datetime created_at
        datetime confirmed_at
        datetime completed_at
        bigint total
    }
    ORDER_LINES {
        int id PK
        int order_id FK
        int product_id FK
        string kode
        string nama
        bigint harga
        int qty
        bigint subtotal
    }
    SALES {
        int id PK
        int order_id FK,UK
        datetime created_at
        string metode_pembayaran
        string status_pembayaran
        bigint jumlah_bayar
        bigint kembalian
        datetime paid_at
        blob payment_proof
        int payment_verified_by FK
        boolean valid
        bigint total
    }
    STOCK_MOVEMENTS {
        int id PK
        int product_id FK
        int actor_id FK
        int order_id FK
        int delta
        int after
        string alasan
        datetime created_at
    }
```

`ORDERS(member_id, token)` unik untuk mencegah submit pesanan yang sama dua kali.
`ORDER_LINES` menyimpan snapshot nama/kode/harga saat pemesanan agar riwayat stabil setelah produk diedit.
Datetime disimpan dalam UTC dan ditampilkan/diagregasi menggunakan Asia/Jakarta.

Status diperbolehkan:

```mermaid
stateDiagram-v2
    [*] --> Menunggu
    Menunggu --> Dikonfirmasi: konfirmasi dan kurangi stok
    Menunggu --> Dibatalkan: batalkan tanpa perubahan stok
    Dikonfirmasi --> Selesai: barang diserahkan
    Dikonfirmasi --> Dibatalkan: kembalikan stok dan void transaksi
    Selesai --> [*]
    Dibatalkan --> [*]
```

## Penambahan notifikasi dan pengajuan bukti

```mermaid
erDiagram
    USERS ||--o{ NOTIFICATIONS : menerima
    USERS ||--o{ PAYMENT_SUBMISSIONS : mengunggah
    ORDERS ||--o| PAYMENT_SUBMISSIONS : memiliki
    NOTIFICATIONS {
        int id PK
        int user_id FK
        string event_key "unik bersama user_id"
        string kind
        string title
        string message
        string link
        datetime created_at
        datetime read_at "nullable"
    }
    PAYMENT_SUBMISSIONS {
        int id PK
        int order_id FK,UK
        int member_id FK
        mediumblob proof "deferred, JPEG tervalidasi"
        datetime created_at
    }
```

Indeks inbox: user_id/read_at/id. Notifikasi disimpan per penerima dan dibuat atomik
bersama transaksi bisnis. Pengajuan bukti anggota terpisah dari bukti Sale yang sudah
terverifikasi; unggah anggota tidak mengubah status lunas atau empat status pesanan.

## Snapshot HPP

PRODUCTS.hpp dan ORDER_LINES.hpp berupa BIGINT nullable. PRODUCTS.hpp adalah HPP per unit
yang diisi admin; ORDER_LINES.hpp disalin dari produk saat konfirmasi pertama di dalam lock
produk/transaksi yang sama. Nilai null berbeda dari nol. Snapshot harga jual saat pesan tetap.
Tidak ada perubahan tabel Sale untuk perhitungan ini; agregasi memakai baris pesanan yang
terhubung dengan Sale.valid. Migrasi: migrate-hpp, additive dan tanpa backfill.

## Markup kategori

CATEGORIES.markup_percent: NUMERIC(5,2), default kategori kustom 15, validasi 0–100.
Harga produk dihitung dari HPP positif dan persentase dengan pembulatan ke atas Rp100;
OrderLine.harga tetap snapshot saat pesan dan OrderLine.hpp snapshot saat konfirmasi.
Migrasi migrate-pricing hanya menambah/set default kolom baru, tidak mereset nilai admin
atau mengubah harga, stok dan snapshot lama. Penyimpanan kategori/produk memakai urutan
lock Category lalu Product untuk repricing yang konsisten.
