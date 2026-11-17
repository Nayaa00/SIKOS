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
