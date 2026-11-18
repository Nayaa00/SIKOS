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
                if 'markup_percent' in {c['name'] for c in inspect(engine).get_columns('categories')}:
                    from .pricing import DEFAULT_MARKUPS
                    conn.execute(text('INSERT INTO categories (nama,active,markup_percent) VALUES (:name,1,:markup)'),{'name':name,'markup':DEFAULT_MARKUPS.get(name,15)})
                else:
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
        'payment_proof': "MEDIUMBLOB NULL" if engine.dialect.name=='mysql' else "BLOB NULL",
        'payment_verified_by': "INTEGER NULL",
    }

    with engine.begin() as conn:
        for name, definition in new_columns.items():
            if name not in columns:
                conn.execute(
                    text(f'ALTER TABLE sales ADD COLUMN {name} {definition}')
                )


def migrate_notifications(engine):
    from .models import Notification, PaymentSubmission
    # Add only the two feature tables; never modify inventory or existing transactions.
    Notification.__table__.create(engine,checkfirst=True)
    PaymentSubmission.__table__.create(engine,checkfirst=True)


def migrate_hpp(engine):
    # Nullable means unknown; never backfill historical costs from today's product cost.
    for table in ('products','order_lines'):
        columns={column['name'] for column in inspect(engine).get_columns(table)}
        if 'hpp' not in columns:
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN hpp BIGINT NULL'))


def migrate_pricing(engine):
    columns={column['name'] for column in inspect(engine).get_columns('categories')}
    if 'markup_percent' not in columns:
        from .pricing import DEFAULT_MARKUPS
        with engine.begin() as conn:
            conn.execute(text('ALTER TABLE categories ADD COLUMN markup_percent NUMERIC(5,2) NOT NULL DEFAULT 15'))
            for name,value in DEFAULT_MARKUPS.items():
                conn.execute(text('UPDATE categories SET markup_percent=:value WHERE nama=:name'),{'name':name,'value':value})
    # Price, HPP and historical order snapshots are deliberately not rewritten.
