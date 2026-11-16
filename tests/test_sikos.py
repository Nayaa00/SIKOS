import os
os.environ.setdefault('DATABASE_URL','sqlite:////tmp/sikos_import_only.db')
os.environ.setdefault('SESSION_SECRET','test-secret-with-more-than-thirty-two-characters')
from io import BytesIO
from datetime import datetime
import re
from uuid import uuid4
import pandas as pd
import pytest
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.db import Base,get_db
from app.main import app
from app.models import User,Category,Product,Order,Sale,StockMovement
from app.security import hash_password,verify_password
from app.services import create_order,transition,movement,RuleError,period,integer
from app.analytics import analyze
from app.importer import load_rows,save_rows

@pytest.fixture
def store(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'test.db'),connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    factory=sessionmaker(engine,expire_on_commit=False)
    with factory() as db:
        admin=User(nomor='ADM1',nama='Admin',email='admin@example.com',password_hash=hash_password('password-admin'),role='admin',telepon='0800',alamat='Bandung')
        member=User(nomor='AG1',nama='Naila',email='naila@example.com',password_hash=hash_password('password-member'),role='anggota',telepon='0811',alamat='Bandung')
        other=User(nomor='AG2',nama='Anggota Dua',email='dua@example.com',password_hash=hash_password('password-other'),role='anggota',telepon='0822',alamat='Bandung')
        cat=Category(nama='Beras');db.add_all([admin,member,other,cat]);db.flush()
        product=Product(kode='B01',nama='Beras 5kg',category_id=cat.id,harga=70000,stok=10,satuan='pak',deskripsi='',gambar='')
        second=Product(kode='B02',nama='Beras 10kg',category_id=cat.id,harga=140000,stok=1,satuan='pak',deskripsi='',gambar='')
        db.add_all([product,second]);db.commit()
        yield db,admin,member,other,product,second,factory
    engine.dispose()

@pytest.fixture
def web(store):
    factory=store[-1]
    def override():
        with factory() as db:
            try: yield db
            except Exception: db.rollback();raise
    app.dependency_overrides[get_db]=override
    with TestClient(app) as client:yield client
    app.dependency_overrides.clear()

def token(response):
    return re.search(r'name="csrf" value="([^"]+)"',response.text).group(1)

def signin(client,admin=False):
    csrf=token(client.get('/login'))
    response=client.post('/login',data={'csrf':csrf,'email':'admin@example.com' if admin else 'naila@example.com','password':'password-admin' if admin else 'password-member'},follow_redirects=False)
    assert response.status_code==303
    return token(client.get('/' if admin else '/katalog'))

def test_password_hash():
    encoded=hash_password('password-demo')
    assert encoded!='password-demo'
    assert verify_password('password-demo',encoded)
    assert not verify_password('wrong',encoded)

def test_waiting_confirmation_cancellation_once(store):
    db,admin,member,other,p,second,_=store
    o=create_order(db,member.id,{str(p.id):2},'a'*32);db.commit()
    assert p.stok==10
    transition(db,o.id,'Dikonfirmasi',admin.id);db.commit()
    assert p.stok==8
    transition(db,o.id,'Dikonfirmasi',admin.id);db.commit()
    assert p.stok==8 and db.scalar(select(func.count()).select_from(Sale))==1
    transition(db,o.id,'Dibatalkan',admin.id);db.commit()
    assert p.stok==10
    transition(db,o.id,'Dibatalkan',admin.id);db.commit()
    assert p.stok==10
    assert not db.scalar(select(Sale)).valid
    assert db.scalar(select(func.count()).select_from(StockMovement))==2

def test_cancel_pending_no_stock_return(store):
    db,a,m,_,p,_,_=store
    order=create_order(db,m.id,{str(p.id):2},'b'*32)
    transition(db,order.id,'Dibatalkan',a.id);db.commit()
    assert p.stok==10
    assert db.scalar(select(func.count()).select_from(StockMovement))==0

def test_insufficient_stock_rolls_back_whole_confirmation(store):
    db,a,m,_,p,s,_=store
    order=create_order(db,m.id,{str(p.id):2,str(s.id):1},'c'*32);db.commit()
    s.stok=0;db.commit()
    with pytest.raises(RuleError):transition(db,order.id,'Dikonfirmasi',a.id)
    db.rollback();db.expire_all()
    assert db.get(Product,p.id).stok==10
    assert db.get(Order,order.id).status=='Menunggu konfirmasi'
    assert db.scalar(select(func.count()).select_from(Sale))==0

def test_completed_order_cannot_cancel(store):
    db,a,m,_,p,_,_=store
    order=create_order(db,m.id,{str(p.id):1},'d'*32)
    transition(db,order.id,'Dikonfirmasi',a.id);transition(db,order.id,'Selesai',a.id);db.commit()
    with pytest.raises(RuleError):transition(db,order.id,'Dibatalkan',a.id)
    db.rollback()

def test_order_idempotency(store):
    db,_,m,_,p,_,_=store
    first=create_order(db,m.id,{str(p.id):1},'e'*32);db.commit()
    again=create_order(db,m.id,{str(p.id):1},'e'*32)
    assert first.id==again.id
    assert db.scalar(select(func.count()).select_from(Order))==1

def test_stock_no_negative(store):
    db,a,_,_,p,_,_=store
    with pytest.raises(RuleError):movement(db,p,-11,a.id,'keluar')
    assert p.stok==10

def test_periods():
    start,end=period('mingguan','2026-11-18')
    assert start==datetime(2026,11,15,17)
    assert end==datetime(2026,11,22,17)
    assert period('bulanan','2026-12-31')[1]==datetime(2026,12,31,17)
    assert period('tahunan','2024-02-29')[1]==datetime(2024,12,31,17)
    for value in ['-1','1.5','nan','inf']:
        with pytest.raises(RuleError):integer(value,'Jumlah')

def test_analytics_counts_units_excludes_cancelled(store):
    db,a,m,_,p,s,_=store
    first=create_order(db,m.id,{str(p.id):3},'f'*32);transition(db,first.id,'Dikonfirmasi',a.id)
    cancelled=create_order(db,m.id,{str(s.id):1},'0'*32);transition(db,cancelled.id,'Dikonfirmasi',a.id);transition(db,cancelled.id,'Dibatalkan',a.id)
    pending=create_order(db,m.id,{str(p.id):1},'1'*32)
    db.commit()
    for sale in db.scalars(select(Sale)):
        sale.created_at=datetime(2026,11,16,2)
    db.commit()
    result=analyze(db,'harian','2026-11-16')
    assert result['units']==3 and result['transactions']==1 and result['total']==210000
    assert result['best'][0]['kode']=='B01'
    assert result['trend'][0]['hari']=='2026-11-16'
    for kind in ['mingguan','bulanan','tahunan']:
        assert analyze(db,kind,'2026-11-16')['total']==210000

def excel(rows):
    out=BytesIO();pd.DataFrame(rows).to_excel(out,index=False,engine='openpyxl');return out.getvalue()

def test_import_partial_valid_duplicate_invalid(store):
    db,a,*_=store
    row={'kode':'N01','nama':'Minyak','kategori':'Minyak','harga':18000,'stok':5,'satuan':'botol'}
    raw=excel([row,row,{**row,'kode':'N02','harga':-1},{**row,'kode':'B01'}])
    result=save_rows(db,load_rows(raw),a.id);db.commit()
    assert result['success']==1 and result['failed']==3
    assert len(result['errors'])==3
    assert db.scalar(select(Product).where(Product.kode=='N01')).stok==5

def test_bad_excel_header():
    with pytest.raises(RuleError):load_rows(excel([{'foo':'bar'}]))

def test_login_csrf_role_boundaries(web):
    assert web.get('/produk',follow_redirects=False).status_code==303
    assert web.post('/login',data={'email':'admin@example.com','password':'password-admin'}).status_code==403
    csrf=token(web.get('/login'))
    assert 'Email atau password salah' in web.post('/login',data={'csrf':csrf,'email':'admin@example.com','password':'bad'}).text
    signin(web)
    for url in ['/anggota','/kategori','/produk','/stok','/impor','/transaksi','/laporan']:
        assert web.get(url).status_code==403

def test_all_admin_pages(web):
    signin(web,True)
    for url in ['/','/anggota','/anggota/tambah','/kategori','/produk','/produk/tambah','/produk/1/edit','/stok','/impor','/katalog','/keranjang','/pesanan','/transaksi','/laporan']:
        result=web.get(url)
        assert result.status_code==200,(url,result.text)

def test_cart_and_order_browser_flow(web,store):
    csrf=signin(web)
    response=web.post('/keranjang/tambah',data={'csrf':csrf,'product_id':1,'qty':2})
    assert response.status_code==200
    assert 'Rp140.000' in response.text
    csrf=token(response)
    checkout_token=re.search(r'name="token" value="([^"]+)"',response.text).group(1)
    response=web.post('/pesanan/buat',data={'csrf':csrf,'token':checkout_token})
    assert 'Menunggu konfirmasi' in response.text
    response=web.post('/pesanan/buat',data={'csrf':csrf,'token':checkout_token})
    assert response.status_code==200
    db=store[0];db.expire_all()
    assert db.scalar(select(func.count()).select_from(Order))==1
    assert db.get(Product,1).stok==10

def test_member_orders_private(web,store):
    db,a,m,other,p,s,_=store
    order=create_order(db,other.id,{str(p.id):1},'2'*32);db.commit()
    csrf=signin(web)
    assert order.kode not in web.get('/pesanan').text
    assert web.post(f'/pesanan/{order.id}/status',data={'csrf':csrf,'status':'Dikonfirmasi'}).status_code==403

def test_admin_crud_http(web,store):
    csrf=signin(web,True)
    response=web.post('/anggota/simpan',data={'csrf':csrf,'nomor':'AG003','nama':'Baru','email':'baru@example.com','telepon':'0812','alamat':'Bandung','password':'password-baru','active':'on'})
    assert response.status_code==200 and 'AG003' in response.text
    response=web.post('/kategori/simpan',data={'csrf':csrf,'nama':'Gula','active':'on'})
    assert response.status_code==200
    db=store[0];category=db.scalar(select(Category).where(Category.nama=='Gula'))
    response=web.post('/produk/simpan',data={'csrf':csrf,'kode':'G001','nama':'Gula 1kg','category_id':category.id,'harga':16000,'stok':7,'satuan':'pak','active':'on'})
    assert response.status_code==200 and 'G001' in response.text
    product=db.scalar(select(Product).where(Product.kode=='G001'))
    response=web.post('/stok',data={'csrf':csrf,'product_id':product.id,'qty':2,'direction':'keluar','alasan':'rusak'})
    assert response.status_code==200
    db.expire_all();assert db.get(Product,product.id).stok==5
    assert web.post(f'/produk/{product.id}/hapus',data={'csrf':csrf}).status_code==200
    db.expire_all();assert not db.get(Product,product.id).active

def test_template_import_and_report_export(web):
    csrf=signin(web,True)
    response=web.get('/impor/template');assert response.status_code==200
    response=web.post('/impor',data={'csrf':csrf},files={'file':('produk.xlsx',response.content,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert 'Berhasil 1 baris' in response.text
    response=web.get('/laporan?export=xlsx')
    assert response.status_code==200
    book=pd.read_excel(BytesIO(response.content),sheet_name='Ringkasan')
    assert book.iloc[0]['transaksi']==0

def test_registration_does_not_grant_admin(web):
    csrf=token(web.get('/daftar'))
    response=web.post('/daftar',data={'csrf':csrf,'nama':'Test','email':'test@example.com','telepon':'0812','alamat':'Bandung','password':'password-test','role':'admin'})
    assert response.status_code==200
    csrf=token(web.get('/login'))
    response=web.post('/login',data={'csrf':csrf,'email':'test@example.com','password':'password-test'})
    assert '/katalog' in str(response.url)
    assert web.get('/produk').status_code==403


def test_price_snapshot_survives_product_edit(store):
    db, admin, member, _, product, _, _ = store
    order = create_order(db, member.id, {str(product.id): 2}, '3'*32)
    db.commit()
    product.harga = 90000
    product.nama = 'Nama baru'
    db.commit()
    transition(db, order.id, 'Dikonfirmasi', admin.id)
    db.commit()
    assert order.lines[0].harga == 70000
    assert order.lines[0].nama == 'Beras 5kg'
    assert order.total == 140000
    assert db.scalar(select(Sale)).total == 140000


def test_confirmation_refreshes_preloaded_product(store):
    db, admin, member, _, product, _, factory = store
    order = create_order(db, member.id, {str(product.id): 2}, '4'*32)
    db.commit()
    with factory() as concurrent:
        current = concurrent.get(Product, product.id)
        movement(concurrent, current, -9, admin.id, 'Perubahan sesi lain')
        concurrent.commit()
    with pytest.raises(RuleError):
        transition(db, order.id, 'Dikonfirmasi', admin.id)
    db.rollback()
    assert db.get(Product, product.id).stok == 1
    assert db.get(Order, order.id).status == 'Menunggu konfirmasi'


def test_transition_refreshes_preloaded_order(store):
    db, admin, member, _, product, _, factory = store
    order = create_order(db, member.id, {str(product.id): 2}, '5'*32)
    db.commit()
    with factory() as concurrent:
        transition(concurrent, order.id, 'Dikonfirmasi', admin.id)
        concurrent.commit()
    transition(db, order.id, 'Dikonfirmasi', admin.id)
    db.commit()
    db.expire_all()
    assert db.get(Product, product.id).stok == 8
    assert db.scalar(select(func.count()).select_from(Sale)) == 1


def test_order_status_constraint(store):
    from sqlalchemy.exc import IntegrityError
    db, _, member, _, product, _, _ = store
    order = create_order(db, member.id, {str(product.id): 1}, '6'*32)
    db.commit()
    order.status = 'Status tidak dikenal'
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
