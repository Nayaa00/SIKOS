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
    assert db.scalar(select(Product).where(Product.source_code=='N01')).stok==5

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
    for url in ['/','/anggota','/anggota/tambah','/kategori','/produk','/produk/tambah','/produk/1/edit','/stok','/impor','/pesanan','/transaksi','/laporan']:
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
    db=store[0];store[4].label='Gula';category=Category(nama='Bahan pokok');db.add(category);db.commit()
    response=web.post('/kategori/simpan',data={'csrf':csrf,'id':category.id,'active':'on'})
    assert response.status_code==200
    response=web.post('/produk/simpan',data={'csrf':csrf,'kode':'G001','nama':'Gula 1kg','label':'Gula','category_id':category.id,'harga':16000,'stok':7,'satuan':'pak','active':'on'})
    assert response.status_code==200 and 'BPK001' in response.text
    product=db.scalar(select(Product).where(Product.nama=='Gula 1kg'))
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
    response=web.post('/daftar',data={'csrf':csrf,'nama':'Test','email':'test@example.com','telepon':'0812','alamat':'Bandung','password':'password-test','password_confirm':'password-test','role':'admin'})
    assert response.status_code==200
    csrf=token(web.get('/login'))
    response=web.post('/login',data={'csrf':csrf,'email':'test@example.com','password':'password-test'})
    assert '/anggota/dashboard' in str(response.url)
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


def test_catalog_search_name_or_label_only(web,store):
    db,_,_,_,product,second,_ = store
    product.label='Sembako khusus'; second.label='Lainnya'; db.commit()
    signin(web)
    assert 'Beras 5kg' in web.get('/katalog?q=sembako').text
    assert 'Beras 10kg' not in web.get('/katalog?q=sembako').text
    assert 'Beras 5kg' in web.get('/katalog?q=Beras+5kg').text
    assert 'Beras 5kg' not in web.get('/katalog?q=B01').text
    assert 'Cari nama atau label' in web.get('/katalog').text

def test_import_label_and_broad_category(store):
    db,admin,*_=store
    row={'kode':'SAB01','nama':'Sabun mandi','label':'Sabun','kategori':'Perawatan','harga':5000,'stok':8,'satuan':'batang'}
    result=save_rows(db,load_rows(excel([row,{**row,'kode':'BAD01','kategori':'Tidak dikenal'}])),admin.id)
    db.commit()
    assert result['success']==1 and result['failed']==1
    product=db.scalar(select(Product).where(Product.source_code=='SAB01'))
    assert product.label=='Sabun' and product.category.nama=='Perawatan'

def test_migrate_labels_preserves_inventory_and_history(store):
    from app.migrations import migrate_product_labels
    db,admin,member,_,product,_,factory=store
    order=create_order(db,member.id,{str(product.id):2},'7'*32)
    transition(db,order.id,'Dikonfirmasi',admin.id);db.commit()
    stock=product.stok;total=order.total
    migrate_product_labels(db.get_bind());migrate_product_labels(db.get_bind())
    db.expire_all()
    assert product.stok==stock and order.total==total
    assert product.label=='Beras' and product.category.nama=='Bahan pokok'
    assert db.scalar(select(func.count()).select_from(Sale))==1
    assert db.scalar(select(func.count()).select_from(StockMovement))==1


def test_product_cards_and_local_photos(web,store):
    from app.product_images import default_product_image
    db,_,_,_,product,_,_=store
    signin(web,True)
    response=web.get('/produk')
    assert response.status_code==200
    assert '<article class="inventory-card' in response.text
    assert '<table' not in response.text
    assert 'Stok tersedia' in response.text and 'Hapus / arsip' in response.text
    assert f'/produk/{product.id}/edit' in response.text
    photo=default_product_image(product)
    assert photo in response.text
    image=web.get(photo)
    assert image.status_code==200 and image.headers['content-type'].startswith('image/')
    signin(web)
    assert photo in web.get('/katalog').text
    assert web.get('/static/products/credits.html').status_code==200

def test_product_image_custom_url_and_path_safety():
    from app.product_images import product_image,valid_product_image
    from types import SimpleNamespace
    custom=SimpleNamespace(nama='Beras',gambar='https://example.com/rice.jpg')
    assert product_image(custom)==custom.gambar
    assert valid_product_image('/static/products/rice.jpg')
    for value in ('javascript:alert(1)','/static/products/../../.env','http://example.com/a.jpg','/static/products/missing.jpg'):
        assert not valid_product_image(value)


def test_admin_cannot_access_buyer_pages_or_create_orders(web,store):
    from app.models import Order
    csrf=signin(web,True)
    response=web.get('/produk')
    assert 'href="/katalog"' not in response.text
    assert 'href="/keranjang"' not in response.text
    assert 'href="/pesanan"' in response.text
    for url in ('/katalog','/keranjang'):
        assert web.get(url).status_code==403
    for url,data in (
        ('/keranjang/tambah',{'product_id':1,'qty':1}),
        ('/keranjang/ubah',{'qty_1':1}),
        ('/pesanan/buat',{'token':'a'*32}),
    ):
        assert web.post(url,data={'csrf':csrf,**data}).status_code==403
    db=store[0];db.expire_all()
    assert db.scalar(select(func.count()).select_from(Order))==0
    assert db.get(Product,1).stok==10
    signin(web)
    member_page=web.get('/katalog')
    assert member_page.status_code==200
    assert 'href="/katalog"' in member_page.text
    assert 'href="/keranjang"' in member_page.text
    assert 'href="/produk"' not in member_page.text
    assert web.get('/keranjang').status_code==200


def test_categories_fixed_names_status_and_stale_add_form(web,store):
    db,_,_,_,product,_,_=store
    category=product.category
    original_name=category.nama
    count=db.scalar(select(func.count()).select_from(Category))
    csrf=signin(web,True)
    response=web.get('/kategori')
    assert '<select' not in response.text and 'Tambah kategori' in response.text
    response=web.post('/kategori/simpan',data={'csrf':csrf,'nama':original_name,'active':'on'})
    assert response.status_code==200
    assert '/kategori'==response.url.path
    assert 'Nama kategori sudah tersedia' in response.text
    assert 'Admin Koperasi' not in response.text or 'href="/produk"' in response.text
    assert web.get('/produk').status_code==200
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Category))==count
    response=web.post('/kategori/simpan',data={'csrf':csrf,'id':category.id,'nama':'Nama palsu'})
    assert response.status_code==200
    db.expire_all()
    assert category.nama==original_name and not category.active
    response=web.post('/kategori/simpan',data={'csrf':csrf,'id':category.id,'active':'on'})
    assert response.status_code==200
    db.expire_all()
    assert category.nama==original_name and category.active
    assert db.get(Product,product.id).stok==10


def test_category_creation_custom_prefix_and_duplicates(web,store):
    db=store[0]
    csrf=signin(web,True)
    assert web.post('/kategori/simpan',data={'csrf':csrf,'nama':'Alat tulis','code_prefix':'ALT','active':'on'}).status_code==200
    category=db.scalar(select(Category).where(Category.nama=='Alat tulis'))
    assert category.code_prefix=='ALT' and category.active
    count=db.scalar(select(func.count()).select_from(Category))
    response=web.post('/kategori/simpan',data={'csrf':csrf,'nama':'alat tulis','code_prefix':'XYZ','active':'on'})
    assert 'Nama kategori sudah tersedia' in response.text
    assert db.scalar(select(func.count()).select_from(Category))==count
    assert web.post('/kategori/simpan',data={'csrf':csrf,'nama':'Kategori lain','code_prefix':'ALT','active':'on'}).status_code==400

def test_product_code_preview_and_server_authority(web,store):
    db=store[0]
    store[4].label='Teh'
    category=Category(nama='Minuman',code_prefix='MNM');db.add(category);db.commit()
    csrf=signin(web,True)
    preview=web.get(f'/produk/kode-berikutnya?category_id={category.id}')
    assert preview.json()['kode']=='MNM001'
    assert web.get(f'/produk/kode-berikutnya?category_id={category.id}').json()['kode']=='MNM001'
    form={'csrf':csrf,'nama':'Teh botol','label':'Teh','category_id':category.id,'harga':5000,'stok':4,'satuan':'botol','active':'on','kode':'HACK999'}
    assert web.post('/produk/simpan',data=form).status_code==200
    product=db.scalar(select(Product).where(Product.nama=='Teh botol'))
    assert product.kode=='MNM001'
    assert 'readonly' in web.get('/produk/tambah').text
    assert web.get(f'/produk/kode-berikutnya?category_id={category.id}').json()['kode']=='MNM002'
    assert web.post('/produk/simpan',data={**form,'id':product.id,'nama':'Teh baru'}).status_code==200
    db.expire_all();assert product.kode=='MNM001' and product.stok==4
    other=Category(nama='Makanan ringan',code_prefix='MKR');db.add(other);db.commit()
    assert web.post('/produk/simpan',data={**form,'id':product.id,'category_id':other.id}).status_code==200
    db.expire_all();assert product.kode=='MKR001' and product.stok==4

def test_code_migration_preserves_snapshot_and_reimport_is_rejected(store):
    from app.code_migration import migrate_product_codes
    db,admin,member,_,product,second,_=store
    product.category.nama='Bahan pokok'
    product.kode='UJI001';second.kode='UJI002';db.commit()
    order=create_order(db,member.id,{str(product.id):2},'8'*32)
    transition(db,order.id,'Dikonfirmasi',admin.id);db.commit()
    stock=product.stok;price=product.harga;total=order.total
    migrate_product_codes(db.get_bind());migrate_product_codes(db.get_bind())
    db.expire_all()
    assert product.kode=='BPK001' and second.kode=='BPK002'
    assert product.source_code=='UJI001'
    assert product.stok==stock and product.harga==price and order.total==total
    assert order.lines[0].kode=='UJI001'
    assert db.scalar(select(func.count()).select_from(Sale))==1
    assert db.scalar(select(func.count()).select_from(StockMovement))==1
    row={'kode':'UJI001','nama':'Beras lama','label':'Beras','kategori':'Bahan pokok','harga':5000,'stok':999,'satuan':'pak'}
    result=save_rows(db,load_rows(excel([row])),admin.id);db.commit()
    assert result['failed']==1 and result['success']==0
    assert db.get(Product,product.id).stok==stock

def test_automatic_import_codes_keep_excel_alias_and_rollback_counter(store):
    from app.product_codes import next_product_code
    db,admin,*_=store
    row={'kode':'EX001','nama':'Air mineral','label':'Air','kategori':'Minuman','harga':3000,'stok':2,'satuan':'botol'}
    result=save_rows(db,load_rows(excel([row])),admin.id);db.commit()
    product=db.scalar(select(Product).where(Product.source_code=='EX001'))
    assert result['success']==1 and product.kode=='MNM001'
    category=product.category
    assert next_product_code(db,category.id)=='MNM002'
    db.rollback()
    assert next_product_code(db,category.id)=='MNM002'
    db.rollback()
    result=save_rows(db,load_rows(excel([row])),admin.id);db.commit()
    assert result['failed']==1


def test_label_dropdown_matches_saved_data_and_rejects_unknown(web,store):
    db,_,_,_,product,second,_=store
    product.label='Beras';second.label='Minyak';db.commit()
    csrf=signin(web,True)
    add=web.get('/produk/tambah')
    assert '<select id="product-label" name="label" required>' in add.text
    assert '<input name="label"' not in add.text
    assert '<option value="Beras"' in add.text and '<option value="Minyak"' in add.text
    edit=web.get(f'/produk/{product.id}/edit')
    assert '<option value="Beras" selected>' in edit.text
    count=db.scalar(select(func.count()).select_from(Product))
    response=web.post('/produk/simpan',data={'csrf':csrf,'nama':'Baru','label':'Label palsu','category_id':product.category_id,'harga':1000,'stok':0,'satuan':'pak','active':'on'})
    assert response.status_code==400
    assert 'Pilih label yang tersedia' in response.text
    db.expire_all();assert db.scalar(select(func.count()).select_from(Product))==count
    assert product.stok==10

def test_admin_product_search_category_combination_and_empty_result(web,store):
    db,_,_,_,product,second,_=store
    category=Category(nama='Minuman',code_prefix='MNM');db.add(category);db.flush()
    product.label='Beras';second.nama='Teh tawar';second.label='Teh';second.category_id=category.id;db.commit()
    signin(web,True)
    assert 'Beras 5kg' in web.get('/produk?q=beras').text
    assert 'Teh tawar' not in web.get('/produk?q=beras').text
    assert 'Beras 5kg' in web.get('/produk?q=B01').text
    assert 'Teh tawar' in web.get('/produk?q=teh').text
    filtered=web.get(f'/produk?kategori={category.id}')
    assert 'Teh tawar' in filtered.text and 'Beras 5kg' not in filtered.text
    assert f'value="{category.id}" selected' in filtered.text
    combined=web.get(f'/produk?q=beras&kategori={category.id}')
    assert 'Tidak ada produk yang cocok' in combined.text
    assert 'href="/produk">Reset' in combined.text
    assert web.get('/produk?kategori=abc').status_code==400
    assert web.get('/produk?kategori=99999').status_code==400
    # SQL wildcards are searched literally, not expanded to match every product.
    assert 'Tidak ada produk yang cocok' in web.get('/produk?q=%25').text
    signin(web)
    assert web.get('/produk?q=teh').status_code==403


def test_cipa_signup_confirmation_and_duplicate_email(web,store):
    db=store[0]
    page=web.get('/daftar')
    assert page.status_code==200 and 'name="password_confirm"' in page.text
    csrf=token(page)
    form={'csrf':csrf,'nama':'Pembeli Baru','email':'signup@example.com','telepon':'081234','alamat':'Bandung','password':'password-new','password_confirm':'different-pass'}
    count=db.scalar(select(func.count()).select_from(User))
    result=web.post('/daftar',data=form)
    assert result.status_code==400 and 'Konfirmasi password tidak sama' in result.text
    assert db.scalar(select(func.count()).select_from(User))==count
    result=web.post('/daftar',data={**form,'password_confirm':'password-new','role':'admin'})
    assert result.status_code==200
    member=db.scalar(select(User).where(User.email=='signup@example.com'))
    assert member.role=='anggota' and member.nomor.startswith('AG-')
    assert member.password_hash!='password-new'
    result=web.post('/daftar',data={**form,'password_confirm':'password-new'})
    assert result.status_code==409
    assert db.scalar(select(func.count()).select_from(User))==count+1

def test_cipa_member_dashboard_role_and_active_catalog(web,store):
    db,_,_,_,product,second,_=store
    csrf=token(web.get('/login'))
    result=web.post('/login',data={'csrf':csrf,'email':'naila@example.com','password':'password-member'},follow_redirects=False)
    assert result.headers['location']=='/anggota/dashboard'
    dashboard=web.get('/anggota/dashboard')
    assert dashboard.status_code==200 and 'Selamat datang, Naila!' in dashboard.text
    assert 'AG1' in dashboard.text and 'href="/produk"' not in dashboard.text
    product.active=False;second.stok=0;db.commit()
    catalog=web.get('/katalog')
    assert 'Foto Beras 5kg' not in catalog.text
    assert 'Stok Habis' in catalog.text
    assert f'name="product_id" value="{second.id}"' not in catalog.text
    assert db.get(Product,second.id).stok==0
    signin(web,True)
    assert web.get('/anggota/dashboard').status_code==403

def test_cart_update_remove_and_inline_validation(web,store):
    csrf=signin(web)
    web.post('/keranjang/tambah',data={'csrf':csrf,'product_id':1,'qty':2})
    web.post('/keranjang/tambah',data={'csrf':csrf,'product_id':2,'qty':1})
    response=web.post('/keranjang/ubah',data={'csrf':csrf,'qty_1':3,'qty_2':2})
    assert response.status_code==400 and 'stok tidak cukup' in response.text
    assert 'href="/keranjang"' in response.text
    assert 'value="2" required data-price="70000"' in response.text
    response=web.post('/keranjang/ubah',data={'csrf':csrf,'qty_1':3,'qty_2':1})
    assert response.status_code==200 and 'Rp350.000' in response.text
    assert web.post('/keranjang/hapus',data={'product_id':1}).status_code==403
    response=web.post('/keranjang/hapus',data={'csrf':csrf,'product_id':2})
    assert 'Rp210.000' in response.text and 'Beras 10kg' not in response.text
    response=web.post('/keranjang/hapus',data={'csrf':csrf,'product_id':1})
    assert 'Keranjang masih kosong' in response.text
    assert store[0].scalar(select(func.count()).select_from(Order))==0

def test_cart_checkout_latest_quantities_and_snapshot(web,store):
    csrf=signin(web)
    response=web.post('/keranjang/tambah',data={'csrf':csrf,'product_id':1,'qty':1})
    checkout=re.search(r'name="token" value="([^"]+)"',response.text).group(1)
    response=web.post('/pesanan/buat',data={'csrf':csrf,'token':checkout,'qty_1':3,'total':1,'harga':1})
    assert response.status_code==200 and 'Menunggu konfirmasi' in response.text
    db=store[0];db.expire_all();order=db.scalar(select(Order))
    assert order.total==210000 and order.lines[0].qty==3 and order.lines[0].harga==70000
    assert db.get(Product,1).stok==10
    web.post('/pesanan/buat',data={'csrf':csrf,'token':checkout,'qty_1':3})
    assert db.scalar(select(func.count()).select_from(Order))==1
    assert 'Keranjang masih kosong' in web.get('/keranjang').text

def test_cart_stock_change_and_inactive_product_preserve_cart(web,store):
    csrf=signin(web)
    response=web.post('/keranjang/tambah',data={'csrf':csrf,'product_id':1,'qty':3})
    checkout=re.search(r'name="token" value="([^"]+)"',response.text).group(1)
    db=store[0];db.get(Product,1).stok=1;db.commit()
    response=web.get('/keranjang')
    assert 'Stok berubah' in response.text and 'disabled>Buat pesanan' in response.text
    assert web.post('/pesanan/buat',data={'csrf':csrf,'token':checkout}).status_code==400
    db.get(Product,1).active=False;db.commit()
    assert 'Barang tidak tersedia' in web.get('/keranjang').text
    assert web.post('/pesanan/buat',data={'csrf':csrf,'token':checkout,'qty_1':1}).status_code==400
    assert db.scalar(select(func.count()).select_from(Order))==0
    assert 'Keranjang masih kosong' in web.post('/keranjang/hapus',data={'csrf':csrf,'product_id':1}).text

def test_cart_stale_token_and_admin_remove_denied(web,store):
    csrf=signin(web)
    response=web.post('/keranjang/tambah',data={'csrf':csrf,'product_id':1,'qty':1})
    checkout=re.search(r'name="token" value="([^"]+)"',response.text).group(1)
    web.post('/keranjang/ubah',data={'csrf':csrf,'qty_1':2})
    assert web.post('/pesanan/buat',data={'csrf':csrf,'token':checkout}).status_code==400
    csrf=signin(web,True)
    assert web.post('/keranjang/hapus',data={'csrf':csrf,'product_id':1}).status_code==403
