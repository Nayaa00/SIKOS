from sqlalchemy import inspect, text
from .taxonomy import CATEGORIES, LEGACY

def migrate_product_labels(engine):
    # Additive, idempotent migration. Never recreates tables or rewrites inventory.
    columns = {column['name'] for column in inspect(engine).get_columns('products')}
    if 'label' not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE products ADD COLUMN label VARCHAR(100) NOT NULL DEFAULT ''"))
    with engine.begin() as conn:
        for name in CATEGORIES:
            if conn.scalar(text('SELECT id FROM categories WHERE nama=:name'), {'name':name}) is None:
                conn.execute(text('INSERT INTO categories (nama,active) VALUES (:name,1)'), {'name':name})
        for old, target in LEGACY.items():
            old_id = conn.scalar(text('SELECT id FROM categories WHERE nama=:name AND active=1'), {'name':old})
            if old_id is None: continue
            target_id = conn.scalar(text('SELECT id FROM categories WHERE nama=:name'), {'name':target})
            conn.execute(text("UPDATE products SET label=CASE WHEN label='' THEN :label ELSE label END, category_id=:target WHERE category_id=:old"), {'label':old,'target':target_id,'old':old_id})
            conn.execute(text('UPDATE categories SET active=0 WHERE id=:old'), {'old':old_id})
        # Existing Minuman is already a broad category; preserve it and supply a label.
        conn.execute(text("UPDATE products SET label='Minuman' WHERE label='' AND category_id IN (SELECT id FROM categories WHERE nama='Minuman')"))


def migrate_sale_payments(engine):
    # Migrasi tambahan dan aman dijalankan berulang kali.
    columns = {
        column['name']
        for column in inspect(engine).get_columns('sales')
    }

    new_columns = {
        'metode_pembayaran': "VARCHAR(20) NOT NULL DEFAULT 'Tunai'",
        'status_pembayaran': "VARCHAR(20) NOT NULL DEFAULT 'Belum dibayar'",
        'jumlah_bayar': "BIGINT NOT NULL DEFAULT 0",
        'kembalian': "BIGINT NOT NULL DEFAULT 0",
        'paid_at': "DATETIME NULL",
    }

    with engine.begin() as conn:
        for name, definition in new_columns.items():
            if name not in columns:
                conn.execute(
                    text(f'ALTER TABLE sales ADD COLUMN {name} {definition}')
                )
