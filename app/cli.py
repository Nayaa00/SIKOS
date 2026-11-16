import argparse
from getpass import getpass
from sqlalchemy import select
from .db import Base,engine,SessionLocal
from .models import User,Category,Product
from .security import hash_password
from .services import movement

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['init-db','create-admin','seed-demo'])
    args=parser.parse_args()
    if args.command=='init-db':
        Base.metadata.create_all(engine)
        print('Tabel SIKOS siap.')
        return
    with SessionLocal() as db:
        if args.command=='create-admin':
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
            for kode,nama,kategori,harga,stok,satuan in [('BRG001','Beras 5 kg','Beras',70000,20,'karung'),('BRG002','Minyak goreng 1 liter','Minyak',18000,30,'botol'),('BRG003','Gula pasir 1 kg','Gula',16000,25,'pak'),('BRG004','Telur 1 kg','Telur',30000,15,'kg'),('BRG005','Mi instan','Mi instan',3500,100,'bungkus'),('BRG006','Tepung terigu 1 kg','Tepung',12000,0,'pak')]:
                if db.scalar(select(Product).where(Product.kode==kode)): continue
                category=db.scalar(select(Category).where(Category.nama==kategori))
                if category is None:
                    category=Category(nama=kategori);db.add(category);db.flush()
                product=Product(kode=kode,nama=nama,category_id=category.id,harga=harga,stok=0,satuan=satuan,deskripsi='',gambar='')
                db.add(product);db.flush()
                movement(db,product,stok,admin.id,'Stok awal data simulasi')
            db.commit();print('Enam produk contoh tersedia. Tidak membuat pesanan atau penjualan palsu.')
if __name__=='__main__':main()
