import argparse
from getpass import getpass
from sqlalchemy import select
from .db import Base,engine,SessionLocal
from .models import User,Category,Product
from .security import hash_password
from .services import movement, sync_completed_payments
from .migrations import migrate_product_labels, migrate_sale_payments, migrate_notifications, migrate_hpp, migrate_pricing, migrate_expenses
from .code_migration import migrate_product_codes
from .product_codes import next_product_code
from sqlalchemy import or_

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['init-db','migrate-expenses','init-product-hpp','init-history-hpp','migrate-pricing','migrate-hpp','migrate-notifications','migrate-labels','migrate-codes','migrate-payments','sync-completed-payments','create-admin','seed-demo'])
    args=parser.parse_args()
    if args.command=='init-db':
        Base.metadata.create_all(engine)
        migrate_product_labels(engine)
        migrate_product_codes(engine)
        migrate_sale_payments(engine)
        migrate_hpp(engine)
        migrate_pricing(engine)
        migrate_expenses(engine)
        print('Tabel SIKOS siap.')
        return
    if args.command=='migrate-expenses':
        migrate_expenses(engine)
        print('Biaya operasional dan penanda HPP estimasi siap.')
        return
    if args.command=='init-history-hpp':
        from .expenses import initialize_history_costs
        with SessionLocal() as db:
            count=initialize_history_costs(db);db.commit()
        print(f'{count} baris snapshot HPP kosong diisi estimasi historis, harga/jumlah/status tetap.')
        return
    if args.command=='init-product-hpp':
        from .expenses import initialize_product_costs
        with SessionLocal() as db:
            count=initialize_product_costs(db);db.commit()
        print(f'{count} HPP produk kosong diisi estimasi. Harga jual, stok, dan snapshot lama tetap.')
        return
    if args.command=='migrate-pricing':
        migrate_pricing(engine)
        print('Markup kategori siap; harga produk lama dan snapshot tetap.')
        return
    if args.command=='migrate-hpp':
        migrate_hpp(engine)
        print('Kolom HPP siap; nilai lama tetap belum tersedia.')
        return
    if args.command=='migrate-notifications':
        migrate_notifications(engine)
        print('Tabel notifikasi dan unggahan bukti siap; data lama tetap.')
        return
    if args.command=='migrate-labels':
        migrate_product_labels(engine)
        print('Migrasi label dan kategori selesai; stok dan transaksi tetap.')
        return
    if args.command=='migrate-codes':
        migrate_product_codes(engine)
        print('Kode produk sesuai kategori; stok dan snapshot pesanan tetap.')
        return
    if args.command=='migrate-payments':
        migrate_sale_payments(engine)
        print('Migrasi pembayaran selesai.')
        return
    with SessionLocal() as db:
        if args.command=='sync-completed-payments':
            count=sync_completed_payments(db)
            db.commit();print(f'{count} pembayaran pesanan selesai disinkronkan; stok tetap.')
        elif args.command=='create-admin':
            email=input('Email admin: ').strip().lower()
            if '@' not in email or len(email)>190: raise SystemExit('Email tidak valid.')
            if db.scalar(select(User).where(User.email==email)): raise SystemExit('Email sudah terdaftar.')
            password=getpass('Password admin (min 8 karakter): ')
            if password!=getpass('Ulangi password: '): raise SystemExit('Password berbeda.')
            db.add(User(nomor='ADMIN-'+__import__('uuid').uuid4().hex[:12],nama='Admin Koperasi',email=email,password_hash=hash_password(password),role='admin',telepon='',alamat=''))
            db.commit();print('Admin berhasil dibuat.')
        elif args.command=='seed-demo':
            admin=db.scalar(select(User).where(User.role=='admin'))
            if admin is None: raise SystemExit('Buat admin terlebih dahulu.')
            for kode,nama,label,harga,stok,satuan in [('BRG001','Beras 5 kg','Beras',70000,20,'karung'),('BRG002','Minyak goreng 1 liter','Minyak',18000,30,'botol'),('BRG003','Gula pasir 1 kg','Gula',16000,25,'pak'),('BRG004','Telur 1 kg','Telur',30000,15,'kg'),('BRG005','Mi instan','Mi instan',3500,100,'bungkus'),('BRG006','Tepung terigu 1 kg','Tepung',12000,0,'pak')]:
                if db.scalar(select(Product).where(or_(Product.kode==kode,Product.source_code==kode))): continue
                kategori='Bahan pokok'
                category=db.scalar(select(Category).where(Category.nama==kategori))
                if category is None:
                    category=Category(nama=kategori);db.add(category);db.flush()
                product=Product(kode=next_product_code(db,category.id),source_code=kode,nama=nama,label=label,category_id=category.id,harga=harga,stok=0,satuan=satuan,deskripsi='',gambar='')
                db.add(product);db.flush()
                movement(db,product,stok,admin.id,'Stok awal data simulasi')
            db.commit();print('Enam produk contoh tersedia. Tidak membuat pesanan atau penjualan palsu.')
if __name__=='__main__':main()
