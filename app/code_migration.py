"""Additive migration; keep IDs, stocks, order snapshots and import aliases intact."""
from sqlalchemy import inspect, text
import re
from .product_codes import choose_prefix

def migrate_product_codes(engine):
    for table, fields in {
        'categories':{'code_prefix':"VARCHAR(3) NULL",'code_counter':"INTEGER NOT NULL DEFAULT 0"},
        'products':{'source_code':"VARCHAR(40) NULL"},
    }.items():
        columns={c['name'] for c in inspect(engine).get_columns(table)}
        for name,definition in fields.items():
            if name not in columns:
                with engine.begin() as conn:conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {definition}'))
    for table,column,index in [('categories','code_prefix','ux_categories_code_prefix'),('products','source_code','ux_products_source_code')]:
        unique=inspect(engine).get_unique_constraints(table)+inspect(engine).get_indexes(table)
        if not any(item.get('column_names')==[column] and item.get('unique',True) for item in unique):
            with engine.begin() as conn:conn.execute(text(f'CREATE UNIQUE INDEX {index} ON {table} ({column})'))
    with engine.begin() as conn:
        lock=' FOR UPDATE' if engine.dialect.name=='mysql' else ''
        categories=conn.execute(text('SELECT id,nama,code_prefix,code_counter FROM categories ORDER BY id'+lock)).mappings().all()
        used={row['code_prefix'] for row in categories if row['code_prefix']}
        all_codes=set(conn.scalars(text('SELECT kode FROM products')))
        all_aliases=set(conn.scalars(text('SELECT source_code FROM products WHERE source_code IS NOT NULL')))
        for category in categories:
            prefix=category['code_prefix']
            if not prefix:
                prefix=choose_prefix(category['nama'],used)
                used.add(prefix)
            products=conn.execute(text('SELECT id,kode,source_code FROM products WHERE category_id=:id ORDER BY id'+lock),{'id':category['id']}).mappings().all()
            counter=int(category['code_counter'] or 0)
            for code in all_codes|all_aliases:
                if re.fullmatch(re.escape(prefix)+r'[0-9]+',code):counter=max(counter,int(code[3:]))
            for product in products:
                if re.fullmatch(re.escape(prefix)+r'[0-9]+',product['kode']) and int(product['kode'][3:])>0:continue
                old=product['kode']
                while True:
                    counter+=1;new=f'{prefix}{counter:03d}'
                    if new not in all_codes and new not in all_aliases:break
                conn.execute(text('UPDATE products SET kode=:new,source_code=COALESCE(source_code,:old) WHERE id=:id'),{'new':new,'old':old,'id':product['id']})
                all_codes.add(new);all_aliases.add(product['source_code'] or old)
            conn.execute(text('UPDATE categories SET code_prefix=:prefix,code_counter=:counter WHERE id=:id'),{'prefix':prefix,'counter':counter,'id':category['id']})
