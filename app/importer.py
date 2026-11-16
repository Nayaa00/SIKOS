from io import BytesIO
import pandas as pd
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .models import Product,Category
from .services import RuleError,integer,text,code,movement

REQUIRED=['kode','nama','kategori','harga','stok','satuan']
def load_rows(raw):
    try:
        book=load_workbook(BytesIO(raw),read_only=True,data_only=False)
        sheet=book.active
        if sheet.max_row>5001 or sheet.max_column>30:raise RuleError('Maksimal 5.000 baris dan 30 kolom.')
        iterator=sheet.iter_rows(values_only=True)
        header=[str(v or '').strip().lower() for v in next(iterator)]
        if any(header.count(h)!=1 for h in REQUIRED):raise RuleError('Kolom wajib: kode, nama, kategori, harga, stok, satuan. Unduh template.')
        records=[]
        for index,row in enumerate(iterator,2):
            if all(v is None for v in row):continue
            record={name:row[pos] for pos,name in enumerate(header) if name}
            record['_baris']=index
            record['_formula']=any(isinstance(v,str) and v.startswith('=') for v in row)
            records.append(record)
        book.close()
        if not records:raise RuleError('Tidak ada data produk dalam Excel.')
        # Pandas normalizes empty values while keeping Excel row numbers for feedback.
        return pd.DataFrame(records).fillna('')
    except RuleError:raise
    except Exception:raise RuleError('Workbook .xlsx tidak terbaca. Simpan ulang melalui Excel dan gunakan template.')

def save_rows(db,frame,actor):
    result={'success':0,'failed':0,'errors':[]};seen=set()
    for row in frame.to_dict('records'):
        try:
            if row['_formula']:raise RuleError('Ubah formula menjadi nilai sebelum impor.')
            sku=code(row.get('kode'))
            if sku in seen:raise RuleError('Kode produk duplikat di file.')
            seen.add(sku)
            name=text(row.get('nama'),'Nama');category_name=text(row.get('kategori'),'Kategori',100)
            price=integer(row.get('harga'),'Harga');stock=integer(row.get('stok'),'Stok',True);unit=text(row.get('satuan'),'Satuan',30)
            if db.scalar(select(Product.id).where(Product.kode==sku)):raise RuleError('Kode sudah ada di database. Gunakan edit produk atau stok masuk.')
            with db.begin_nested():
                category=db.scalar(select(Category).where(Category.nama==category_name))
                if category and not category.active:raise RuleError('Kategori tersebut nonaktif.')
                if category is None:category=Category(nama=category_name);db.add(category);db.flush()
                product=Product(kode=sku,nama=name,category_id=category.id,harga=price,stok=0,satuan=unit,deskripsi=str(row.get('deskripsi',''))[:5000],gambar='')
                db.add(product);db.flush();movement(db,product,stock,actor,'Stok awal impor Excel')
            result['success']+=1
        except (RuleError,IntegrityError) as exc:
            result['failed']+=1
            reason=str(exc) if isinstance(exc,RuleError) else 'Kode/kategori duplikat saat penyimpanan.'
            result['errors'].append({'baris':int(row['_baris']),'error':reason})
    return result
