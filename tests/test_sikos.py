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
from app.services import create_order,transition,movement,RuleError,period,integer,record_payment
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
    return re.search(r'name="csrf"\s+value="([^"]+)"', response.text).group(1)

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
    row={'kode':'N01','nama':'Minyak','kategori':'Minyak','hpp':15000,'harga':18000,'stok':5,'satuan':'botol'}
    raw=excel([row,row,{**row,'kode':'N02','hpp':-1},{**row,'kode':'B01'}])
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

def test_cart_update_and_remove(web, store):
    _, _, member, _, product, _, _ = store
    csrf = signin(web)

    # Tambahkan 2 barang ke keranjang
    response = web.post('/keranjang/tambah', data={
        'csrf': csrf,
        'product_id': product.id,
        'qty': 2
    })
    assert response.status_code == 200
    assert 'Rp140.000' in response.text

    # Ubah jumlah menjadi 3
    response = web.post('/keranjang/ubah', data={
        'csrf': csrf,
        f'qty_{product.id}': 3
    })
    assert response.status_code == 200
    assert 'Rp210.000' in response.text

    # Hapus barang dengan jumlah 0
    response = web.post('/keranjang/ubah', data={
        'csrf': csrf,
        f'qty_{product.id}': 0
    })
    assert response.status_code == 200
    assert 'Keranjang masih kosong' in response.text


def test_cart_rejects_quantity_above_stock(web, store):
    _, _, _, _, _, second, _ = store
    csrf = signin(web)

    # Stok produk kedua hanya 1, tetapi diminta 2
    response = web.post('/keranjang/tambah', data={
        'csrf': csrf,
        'product_id': second.id,
        'qty': 2
    })

    assert response.status_code == 400



def test_member_orders_private(web,store):
    db,a,m,other,p,s,_=store
    order=create_order(db,other.id,{str(p.id):1},'2'*32);db.commit()
    csrf=signin(web)
    assert order.kode not in web.get('/pesanan').text
    assert web.post(f'/pesanan/{order.id}/status',data={'csrf':csrf,'status':'Dikonfirmasi'}).status_code==403


def test_order_details_displayed_to_member(web, store):
    db, admin, member, _, product, _, _ = store

    order = create_order(
        db, member.id, {str(product.id): 2}, '9' * 32
    )
    db.commit()

    signin(web)
    response = web.get('/pesanan')

    assert response.status_code == 200
    assert order.kode in response.text
    assert 'Beras 5kg' in response.text
    assert 'Rp70.000' in response.text
    assert 'Rp140.000' in response.text
    assert 'Konfirmasi:' not in response.text
    assert 'Selesai:' not in response.text


def test_empty_order_history(web):
    signin(web)

    response = web.get('/pesanan')

    assert response.status_code == 200
    assert 'Belum ada pesanan.' in response.text


def test_admin_order_status_visible_to_member(web, store):
    db, admin, member, _, product, _, _ = store

    order = create_order(
        db, member.id, {str(product.id): 1}, 'a' * 32
    )
    db.commit()

    # Admin mengonfirmasi pesanan
    csrf = signin(web, True)
    response = web.post(
        f'/pesanan/{order.id}/status',
        data={'csrf': csrf, 'status': 'Dikonfirmasi'}
    )
    assert response.status_code == 200

    # Pembeli masuk dan melihat status terbaru
    signin(web)
    response = web.get('/pesanan')

    assert response.status_code == 200
    assert order.kode in response.text
    assert 'Dikonfirmasi' in response.text


def test_admin_crud_http(web,store):
    csrf=signin(web,True)
    response=web.post('/anggota/simpan',data={'csrf':csrf,'nomor':'AG003','nama':'Baru','email':'baru@example.com','telepon':'0812','alamat':'Bandung','password':'password-baru','active':'on'})
    assert response.status_code==200 and 'AG003' in response.text
    db=store[0];store[4].label='Gula';category=Category(nama='Bahan pokok');db.add(category);db.commit()
    response=web.post('/kategori/simpan',data={'csrf':csrf,'id':category.id,'active':'on'})
    assert response.status_code==200
    response=web.post('/produk/simpan',data={'csrf':csrf,'kode':'G001','nama':'Gula 1kg','label':'Gula','category_id':category.id,'hpp':14000,'harga':16000,'stok':7,'satuan':'pak','active':'on'})
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
    assert 'Berhasil diimpor</span><strong>1</strong>' in response.text
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
    row={'kode':'SAB01','nama':'Sabun mandi','label':'Sabun','kategori':'Perawatan','hpp':4000,'harga':5000,'stok':8,'satuan':'batang'}
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
    form={'csrf':csrf,'nama':'Teh botol','label':'Teh','category_id':category.id,'hpp':4000,'harga':5000,'stok':4,'satuan':'botol','active':'on','kode':'HACK999'}
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
    row={'kode':'EX001','nama':'Air mineral','label':'Air','kategori':'Minuman','hpp':2500,'harga':3000,'stok':2,'satuan':'botol'}
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
    assert 'Ringkasan Anggota' not in dashboard.text and 'href="/produk"' not in dashboard.text
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

def test_profile_own_account_and_permissions(web,store):
    assert web.get('/profil',follow_redirects=False).status_code==303
    csrf=signin(web)
    assert 'Profil Saya' in web.get('/profil').text
    assert web.post('/profil',data={'nama':'A','email':'a@example.com'}).status_code==403
    result=web.post('/profil',data={'csrf':csrf,'nama':'Nama baru','email':'BARU@example.com','id':3,'role':'admin','nomor':'BAD','active':'off'})
    assert 'Profil berhasil diperbarui' in result.text
    db=store[0];db.expire_all();member=db.get(User,2)
    assert (member.nama,member.email,member.nomor,member.role,member.active)==('Nama baru','baru@example.com','AG1','anggota',True)
    assert db.get(User,3).nama=='Anggota Dua'
    csrf=signin(web,True)
    assert web.get('/profil').status_code==403
    assert web.post('/profil',data={'csrf':csrf,'nama':'A','email':'a@example.com'}).status_code==403

def test_profile_invalid_email_and_password_atomic(web,store):
    csrf=signin(web)
    for email in ('bad@', 'bad @example.com', 'a'*180+'@example.com', 'dua@example.com'):
        result=web.post('/profil',data={'csrf':csrf,'nama':'Changed','email':email})
        assert 'profile-error' in result.text
    for old,new,confirm in (('wrong','password-new','password-new'),('password-member','short','short'),('password-member','password-new','different'),('password-member','a'*129,'a'*129)):
        result=web.post('/profil',data={'csrf':csrf,'nama':'Changed','email':'new@example.com','password_lama':old,'password_baru':new,'konfirmasi_password':confirm})
        assert 'profile-error' in result.text
    db=store[0];db.expire_all();member=db.get(User,2)
    assert member.nama=='Naila' and member.email=='naila@example.com'
    assert verify_password('password-member',member.password_hash)
    result=web.post('/profil',data={'csrf':csrf,'nama':'Naila','email':member.email,'password_lama':'password-member','password_baru':'password-new','konfirmasi_password':'password-new'})
    assert 'Profil berhasil diperbarui' in result.text
    db.expire_all();assert verify_password('password-new',db.get(User,2).password_hash)

def test_completion_auto_payment_once_and_no_manual_endpoint(web,store):
    db,admin,member,_,product,_,_=store
    order=create_order(db,member.id,{str(product.id):2},uuid4().hex)
    transition(db,order.id,'Dikonfirmasi',admin.id);db.commit()
    sale=db.scalar(select(Sale).where(Sale.order_id==order.id))
    assert sale.status_pembayaran=='Belum dibayar'
    csrf=signin(web,True)
    assert web.post(f'/transaksi/{sale.id}/bayar',data={'csrf':csrf,'jumlah_bayar':1}).status_code==410
    response=web.post(f'/pesanan/{order.id}/status',data={'csrf':csrf,'status':'Selesai','metode':'Cash','jumlah_bayar':140000})
    assert response.status_code==200
    db.expire_all();sale=db.get(Sale,sale.id);order=db.get(Order,order.id)
    assert sale.status_pembayaran=='Lunas' and sale.jumlah_bayar==140000 and sale.kembalian==0
    assert sale.paid_at is not None and db.get(Product,product.id).stok==8
    paid_at=sale.paid_at
    web.post(f'/pesanan/{order.id}/status',data={'csrf':csrf,'status':'Selesai','metode':'Cash','jumlah_bayar':140000})
    db.expire_all();assert db.get(Sale,sale.id).paid_at==paid_at
    assert 'name="jumlah_bayar"' not in web.get('/transaksi').text

def test_completion_preserves_old_payment_and_sync_only_completed(store):
    from app.services import sync_completed_payments
    db,admin,member,_,product,_,_=store
    paid=create_order(db,member.id,{str(product.id):1},uuid4().hex)
    transition(db,paid.id,'Dikonfirmasi',admin.id);db.commit()
    sale=db.scalar(select(Sale).where(Sale.order_id==paid.id))
    record_payment(db,sale.id,80000);db.commit();old=sale.paid_at
    transition(db,paid.id,'Selesai',admin.id);db.commit()
    assert sale.jumlah_bayar==80000 and sale.kembalian==10000 and sale.paid_at==old
    legacy=create_order(db,member.id,{str(product.id):1},uuid4().hex)
    transition(db,legacy.id,'Dikonfirmasi',admin.id);db.commit()
    legacy.status='Selesai';legacy.completed_at=datetime(2026,11,18,1);db.commit()
    before=product.stok
    assert sync_completed_payments(db)==1;db.commit()
    assert sync_completed_payments(db)==0 and product.stok==before
    legacy_sale=db.scalar(select(Sale).where(Sale.order_id==legacy.id))
    assert legacy_sale.jumlah_bayar==70000 and legacy_sale.paid_at==legacy.completed_at

def test_member_cannot_record_payment(web, store):
    db, admin, member, _, product, _, _ = store

    order = create_order(
        db, member.id, {str(product.id): 1}, 'd' * 32
    )
    transition(db, order.id, 'Dikonfirmasi', admin.id)
    db.commit()

    sale = db.scalar(
        select(Sale).where(Sale.order_id == order.id)
    )

    csrf = signin(web)

    response = web.post(
        f'/transaksi/{sale.id}/bayar',
        data={
            'csrf': csrf,
            'jumlah_bayar': 70000
        }
    )

    assert response.status_code == 403

    db.refresh(sale)
    assert sale.status_pembayaran == 'Belum dibayar'

def test_paid_order_cancellation_restores_once_and_voids(store):
    db, admin, member, _, product, _, _ = store
    order=create_order(db,member.id,{str(product.id):2},'9'*32)
    transition(db,order.id,'Dikonfirmasi',admin.id);db.commit()
    sale=db.scalar(select(Sale).where(Sale.order_id==order.id))
    record_payment(db,sale.id,sale.total+10000);db.commit()
    paid_at=sale.paid_at
    transition(db,order.id,'Dibatalkan',admin.id);db.commit()
    transition(db,order.id,'Dibatalkan',admin.id);db.commit()
    assert order.status=='Dibatalkan' and product.stok==10 and not sale.valid
    assert sale.status_pembayaran=='Lunas' and sale.jumlah_bayar==150000
    assert sale.kembalian==10000 and sale.paid_at==paid_at
    assert db.scalar(select(func.count()).select_from(StockMovement))==2
    result=analyze(db,'harian',datetime.now().date().isoformat())
    assert result['transactions']==0 and result['total']==0
    with pytest.raises(RuleError):record_payment(db,sale.id,sale.total)

def test_payment_schema_migration_preserves_existing_sales(tmp_path):
    from sqlalchemy import text as sql_text,inspect
    from app.migrations import migrate_sale_payments
    engine=create_engine('sqlite:///'+str(tmp_path/'old.db'))
    with engine.begin() as connection:
        connection.execute(sql_text('CREATE TABLE sales (id INTEGER PRIMARY KEY, total BIGINT, valid BOOLEAN)'))
        connection.execute(sql_text('INSERT INTO sales VALUES (1,70000,1)'))
    migrate_sale_payments(engine);migrate_sale_payments(engine)
    assert 'paid_at' in {c['name'] for c in inspect(engine).get_columns('sales')}
    with engine.connect() as connection:
        row=connection.execute(sql_text('SELECT total,valid,status_pembayaran,jumlah_bayar,kembalian FROM sales')).one()
        assert tuple(row)==(70000,1,'Belum dibayar',0,0)
    engine.dispose()

def test_member_cancel_waiting_ownership_csrf_and_processed_order(web,store):
    db,admin,member,other,p,_,_=store
    own=create_order(db,member.id,{str(p.id):2},'6'*32)
    foreign=create_order(db,other.id,{str(p.id):1},'7'*32)
    processed=create_order(db,member.id,{str(p.id):1},'8'*32)
    transition(db,processed.id,'Dikonfirmasi',admin.id);db.commit()
    before=p.stok
    csrf=signin(web)
    assert web.post(f'/pesanan/{own.id}/batal',data={}).status_code==403
    assert web.post(f'/pesanan/{foreign.id}/batal',data={'csrf':csrf}).status_code==404
    result=web.post(f'/pesanan/{processed.id}/batal',data={'csrf':csrf})
    assert 'sudah diproses admin' in result.text
    db.expire_all();assert db.get(Order,processed.id).status=='Dikonfirmasi'
    for _ in range(2):
        assert web.post(f'/pesanan/{own.id}/batal',data={'csrf':csrf}).status_code==200
    db.expire_all()
    assert db.get(Order,own.id).status=='Dibatalkan'
    assert db.get(Product,p.id).stok==before
    assert db.scalar(select(func.count()).select_from(Sale))==1
    assert db.get(Order,foreign.id).status=='Menunggu konfirmasi'
    csrf=signin(web,True)
    assert web.post(f'/pesanan/{foreign.id}/batal',data={'csrf':csrf}).status_code==403

def test_member_sales_private_snapshot_payment_and_void(web,store):
    db,admin,member,other,p,_,_=store
    own=create_order(db,member.id,{str(p.id):2},'3'*32)
    foreign=create_order(db,other.id,{str(p.id):1},'4'*32)
    pending=create_order(db,member.id,{str(p.id):1},'5'*32)
    transition(db,own.id,'Dikonfirmasi',admin.id)
    transition(db,foreign.id,'Dikonfirmasi',admin.id);db.commit()
    sale=db.scalar(select(Sale).where(Sale.order_id==own.id))
    record_payment(db,sale.id,150000);db.commit()
    p.nama='Nama berubah';p.harga=90000;db.commit()
    csrf=signin(web)
    result=web.get('/transaksi-saya')
    assert result.status_code==200 and own.kode in result.text
    assert foreign.kode not in result.text
    # Own pending order may appear in the private bell, but never in transaction rows.
    assert pending.kode not in result.text.split('<main',1)[1]
    assert 'Beras 5kg' in result.text and 'Rp70.000' in result.text
    assert 'Lunas' in result.text and 'Rp10.000' in result.text
    assert 'Nama berubah' not in result.text and '/bayar' not in result.text
    assert web.post(f'/transaksi/{sale.id}/bayar',data={'csrf':csrf,'jumlah_bayar':150000}).status_code==403
    transition(db,own.id,'Dibatalkan',admin.id);db.commit()
    result=web.get('/transaksi-saya')
    assert 'tidak dihitung dalam penjualan' in result.text and 'pengembalian uang' in result.text
    signin(web,True);assert web.get('/transaksi-saya').status_code==403

def test_member_history_pagination_filters_and_empty_sales(web,store):
    db,_,member,_,p,_,_=store
    for _ in range(22):create_order(db,member.id,{str(p.id):1},uuid4().hex)
    db.commit();signin(web)
    result=web.get('/pesanan')
    assert result.text.count('<article class="card order-card">')==20
    assert 'Halaman 1 dari 2' in result.text
    result=web.get('/pesanan?halaman=2&status=Menunggu+konfirmasi')
    assert result.text.count('<article class="card order-card">')==2
    assert 'Halaman 2 dari 2' in result.text
    assert 'Tidak ada pesanan dengan status ini.' in web.get('/pesanan?status=Selesai').text
    assert 'Belum ada transaksi' in web.get('/transaksi-saya').text
    assert web.get('/pesanan?halaman=bad').status_code==200

def test_signup_inline_errors_preserve_only_non_secret_fields(web,store):
    csrf=token(web.get('/daftar'))
    form={'csrf':csrf,'nama':'Nama baru','email':'naila@example.com','telepon':'081234','alamat':'Alamat lengkap','password':'private-example-password','password_confirm':'private-example-password'}
    response=web.post('/daftar',data=form)
    assert response.status_code==409 and 'Email sudah terdaftar.' in response.text
    assert 'value="Nama baru"' in response.text and '>Alamat lengkap</textarea>' in response.text
    assert 'private-example-password' not in response.text
    response=web.post('/daftar',data={**form,'email':'new@example.com','password_confirm':'different'})
    assert response.status_code==400 and 'value="new@example.com"' in response.text
    response=web.post('/daftar',data={**form,'nama':'<script>alert(1)</script>','email':'invalid'})
    assert '<script>alert(1)</script>' not in response.text
    assert '&lt;script&gt;' in response.text
    assert store[0].scalar(select(func.count()).select_from(User))==3

def test_profile_contact_validation_retains_input_and_protects_identity(web,store):
    csrf=signin(web)
    data={'csrf':csrf,'nama':'Nama kontak','email':'new@example.com','telepon':'089999','alamat':'Alamat baru','role':'admin','nomor':'AG-FAKE','id':3}
    response=web.post('/profil',data={**data,'telepon':'1'*31,'password_baru':'secret-dummy-value'})
    assert response.status_code==400 and 'value="Nama kontak"' in response.text
    assert 'secret-dummy-value' not in response.text
    db=store[0];db.expire_all();assert db.get(User,2).nama=='Naila'
    response=web.post('/profil',data=data)
    assert response.status_code==200 and 'Profil berhasil diperbarui' in response.text
    db.expire_all();member=db.get(User,2)
    assert (member.telepon,member.alamat,member.nomor,member.role)==('089999','Alamat baru','AG1','anggota')
    assert '<input id="nomor" type="text" value="AG1" disabled>' in response.text
    assert 'Role Akun' not in response.text and 'id="role"' not in response.text
    assert db.get(User,3).nama=='Anggota Dua'


def test_member_dashboard_counts_only_own_orders(web,store):
    db,admin,member,other,p,_,_=store
    own=create_order(db,member.id,{str(p.id):1},uuid4().hex)
    foreign=create_order(db,other.id,{str(p.id):1},uuid4().hex)
    transition(db,foreign.id,'Dikonfirmasi',admin.id);db.commit()
    signin(web)
    page=web.get('/anggota/dashboard')
    assert page.status_code==200
    assert 'Ringkasan pesanan saya' in page.text
    assert '<strong class="stat-value">1</strong>' in page.text
    assert own.kode in page.text and foreign.kode not in page.text
    assert '<article' not in re.search(r'<title>(.*?)</title>',page.text,re.S).group(1)
    section=re.search(r'<section aria-label="Ringkasan pesanan saya"(.*?)</section>',page.text,re.S).group(1)
    counts=dict(re.findall(r'<span class="small-note">([^<]+)</span><strong class="stat-value">(\d+)</strong>',section))
    assert counts=={'Menunggu konfirmasi':'1','Dikonfirmasi':'0','Selesai':'0','Dibatalkan':'0'}


def test_stock_original_initial_quantity_and_sold_only_on_confirmation(web,store):
    db,admin,member,_,product,_,_=store
    product.stok=0;movement(db,product,20,admin.id,'Stok awal produk manual');db.commit()
    order=create_order(db,member.id,{str(product.id):2},uuid4().hex)
    transition(db,order.id,'Dikonfirmasi',admin.id);db.commit()
    movement(db,product,5,admin.id,'Pembelian pemasok');db.commit()
    movement(db,product,-1,admin.id,'Barang rusak');db.commit()
    transition(db,order.id,'Dibatalkan',admin.id);db.commit()
    signin(web,True);response=web.get('/stok')
    assert response.status_code==200
    assert '<th>Produk</th><th>Stok Awal</th><th>Terjual</th><th>Stok sesudah</th>' in response.text
    rows=re.findall(r'<tr>(.*?)</tr>',response.text,re.S)
    for row in rows:
        if 'Beras 5kg' not in row:continue
        assert '<td>20</td>' in row
        if 'Konfirmasi pesanan' in row:assert '<td>20</td><td>2</td><td>18</td>' in row
        if 'Pembelian pemasok' in row:assert '<td>20</td><td>0</td><td>23</td>' in row
        if 'Barang rusak' in row:assert '<td>20</td><td>0</td><td>22</td>' in row
        if 'Pembatalan pesanan' in row:assert '<td>20</td><td>0</td><td>24</td>' in row
    assert db.get(Product,product.id).stok==24


def test_import_card_only_upload_and_reports_stay_in_reports_menu(web):
    signin(web,True)
    response=web.get('/impor')
    assert 'Unduh template Excel' not in response.text
    assert 'Kolom wajib:' not in response.text and 'Pindahkan data lama' not in response.text
    assert 'action="/laporan"' not in response.text and 'Unduh laporan penjualan Excel' not in response.text
    assert 'enctype="multipart/form-data"' in response.text and 'Validasi &amp; impor' in response.text
    assert 'name="file"' in response.text
    for kind in ('harian','mingguan','bulanan','tahunan'):
        response=web.get('/laporan',params={'export':'xlsx','periode':kind,'tanggal':'2026-11-18'})
        assert response.status_code==200
        book=pd.ExcelFile(BytesIO(response.content))
        assert 'Ringkasan' in book.sheet_names and 'Rincian' in book.sheet_names
        assert pd.read_excel(book,sheet_name='Ringkasan').iloc[0]['periode']==kind


def test_cash_completion_form_and_validation(web,store):
    db,admin,member,_,p,_,_=store
    order=create_order(db,member.id,{str(p.id):1},uuid4().hex)
    transition(db,order.id,'Dikonfirmasi',admin.id);db.commit()
    csrf=signin(web,True)
    assert 'Uang Pembayaran' in web.get(f'/pesanan/{order.id}/selesaikan').text
    for data in ({},{'metode':'Cashless','jumlah_bayar':100000},{'metode':'Cash','jumlah_bayar':50000},{'metode':'Cash','jumlah_bayar':'1.5'}):
        result=web.post(f'/pesanan/{order.id}/status',data={'csrf':csrf,'status':'Selesai',**data})
        assert result.status_code==400
        db.expire_all();assert db.get(Order,order.id).status=='Dikonfirmasi'
    result=web.post(f'/pesanan/{order.id}/status',data={'csrf':csrf,'status':'Selesai','metode':'Cash','jumlah_bayar':100000,'kembalian':999999})
    assert result.status_code==200
    db.expire_all();sale=db.scalar(select(Sale).where(Sale.order_id==order.id))
    assert sale.jumlah_bayar==100000 and sale.kembalian==30000 and sale.status_pembayaran=='Lunas'
    assert db.get(Product,p.id).stok==9
    signin(web);assert web.get(f'/pesanan/{order.id}/selesaikan').status_code==403


def test_cashless_proof_upload_verification_privacy_and_idempotency(web,store):
    from PIL import Image
    db,admin,member,_,p,_,_=store
    order=create_order(db,member.id,{str(p.id):1},uuid4().hex)
    transition(db,order.id,'Dikonfirmasi',admin.id);db.commit()
    csrf=signin(web,True)
    payload={'csrf':csrf,'status':'Selesai','metode':'Cashless'}
    url=f'/pesanan/{order.id}/status'
    assert web.post(url,data=payload).status_code==400
    assert web.post(url,data=payload,files={'payment_proof':('fake.jpg',b'not an image','image/jpeg')}).status_code==400
    image=BytesIO();Image.new('RGB',(50,50),'white').save(image,'PNG');raw=image.getvalue()
    db.expire_all();assert db.get(Order,order.id).status=='Dikonfirmasi'
    result=web.post(url,data=payload,files={'payment_proof':('proof.png',raw,'image/png')})
    assert result.status_code==200
    db.expire_all();sale=db.scalar(select(Sale).where(Sale.order_id==order.id))
    assert sale.metode_pembayaran=='Cashless' and sale.jumlah_bayar==70000 and sale.kembalian==0
    assert sale.payment_verified_by==admin.id and sale.payment_proof.startswith(b'\xff\xd8')
    assert db.get(Order,order.id).status=='Selesai' and db.get(Product,p.id).stok==9
    proof=sale.payment_proof;paid=sale.paid_at
    assert web.post(url,data=payload,files={'payment_proof':('proof.png',raw,'image/png')}).status_code==200
    db.expire_all();assert db.get(Sale,sale.id).payment_proof==proof and db.get(Sale,sale.id).paid_at==paid
    response=web.get(f'/transaksi/{sale.id}/bukti')
    assert response.status_code==200 and response.headers['content-type']=='image/jpeg'
    assert response.headers['cache-control']=='no-store'
    assert 'Lihat bukti' in web.get('/transaksi').text
    signin(web);assert web.get(f'/transaksi/{sale.id}/bukti').status_code==403


def test_payment_proof_size_and_image_validation():
    from app.payment_proofs import validate_payment_proof,MAX_PROOF_SIZE
    for raw in (b'',b'x'*(MAX_PROOF_SIZE+1),b'<svg></svg>'):
        with pytest.raises(RuleError):validate_payment_proof(raw)


def test_notifications_events_atomic_private_and_idempotent(store):
    from app.models import Notification
    from app.services import complete_cash_order
    db,a,m,other,p,second,_=store
    order=create_order(db,m.id,{str(p.id):1},uuid4().hex);db.commit()
    assert db.scalar(select(func.count()).select_from(Notification))==2
    assert not db.scalar(select(Notification).where(Notification.user_id==other.id))
    create_order(db,m.id,{str(p.id):1},order.token);db.commit()
    assert db.scalar(select(func.count()).select_from(Notification))==2
    transition(db,order.id,'Dikonfirmasi',a.id);db.commit()
    count=db.scalar(select(func.count()).select_from(Notification))
    transition(db,order.id,'Dikonfirmasi',a.id);db.commit()
    assert db.scalar(select(func.count()).select_from(Notification))==count
    complete_cash_order(db,order.id,a.id,'Cash',70000);db.commit()
    complete_cash_order(db,order.id,a.id,'Cash',70000);db.commit()
    assert db.scalar(select(func.count()).select_from(Notification).where(Notification.kind=='payment'))==2
    assert db.scalar(select(func.count()).select_from(Notification).where(Notification.title=='Pesanan selesai'))==1
    broken=create_order(db,m.id,{str(p.id):1,str(second.id):1},uuid4().hex);db.commit()
    second.stok=0;db.commit();count=db.scalar(select(func.count()).select_from(Notification))
    with pytest.raises(RuleError):transition(db,broken.id,'Dikonfirmasi',a.id)
    db.rollback()
    assert db.scalar(select(func.count()).select_from(Notification))==count


def test_notifications_api_read_scope_csrf_and_snapshot_all(web,store):
    from app.models import Notification
    from app.notifications import send
    db,a,m,other,p,_,_=store
    order=create_order(db,m.id,{str(p.id):1},uuid4().hex);db.commit()
    csrf=signin(web)
    response=web.get('/api/notifikasi');assert response.headers['cache-control']=='no-store'
    data=response.json();assert data['user_id']==m.id and data['unread']==1
    own=data['items'][0]['id'];foreign=db.scalar(select(Notification.id).where(Notification.user_id==a.id))
    assert web.post(f'/notifikasi/{foreign}/baca',data={'csrf':csrf}).status_code==404
    assert web.post(f'/notifikasi/{own}/baca',data={'csrf':'wrong'}).status_code==403
    assert web.post(f'/notifikasi/{own}/baca',data={'csrf':csrf}).status_code==200
    db.expire_all();read_at=db.get(Notification,own).read_at
    assert web.post(f'/notifikasi/{own}/baca',data={'csrf':csrf}).status_code==200
    db.expire_all();assert db.get(Notification,own).read_at==read_at
    send(db,m.id,'old','order','Old','Old','/pesanan');db.commit()
    through=web.get('/api/notifikasi').json()['latest_id']
    send(db,m.id,'new','order','New','New','/pesanan');db.commit()
    assert web.post('/notifikasi/baca-semua',data={'csrf':csrf,'through':through}).status_code==200
    assert web.get('/api/notifikasi').json()['unread']==1
    db.expire_all();assert db.get(Notification,foreign).read_at is None
    assert 'Notifikasi Anda' in web.get('/anggota/dashboard').text
    assert 'New' in web.get('/notifikasi').text
    signin(web,True);assert web.get('/api/notifikasi').json()['unread']==1


def test_notification_stock_thresholds_and_rollback(store):
    from app.models import Notification
    db,a,_,_,p,_,_=store
    movement(db,p,-5,a.id,'Tes');db.commit()
    assert db.scalar(select(func.count()).select_from(Notification))==1
    movement(db,p,-1,a.id,'Tes');db.commit()
    assert db.scalar(select(func.count()).select_from(Notification))==1
    movement(db,p,-4,a.id,'Tes');db.commit()
    assert db.scalar(select(func.count()).select_from(Notification).where(Notification.title=='Stok habis'))==1
    movement(db,p,10,a.id,'Restok');db.commit()
    movement(db,p,-5,a.id,'Tes');db.rollback()
    assert db.scalar(select(func.count()).select_from(Notification))==2


def test_member_payment_submission_private_notifies_without_settling(web,store):
    from app.models import Notification,PaymentSubmission
    from PIL import Image
    db,a,m,other,p,_,_=store
    own=create_order(db,m.id,{str(p.id):1},uuid4().hex)
    foreign=create_order(db,other.id,{str(p.id):1},uuid4().hex)
    transition(db,own.id,'Dikonfirmasi',a.id);transition(db,foreign.id,'Dikonfirmasi',a.id);db.commit()
    csrf=signin(web);url=f'/pesanan/{own.id}/bukti'
    raw=BytesIO();Image.new('RGB',(20,20),'white').save(raw,format='PNG');raw=raw.getvalue()
    assert web.get(f'/pesanan/{foreign.id}/bukti').status_code==404
    assert web.post(url,data={'csrf':csrf},files={'payment_proof':('bad.jpg',b'invalid','image/jpeg')}).status_code==400
    result=web.post(url,data={'csrf':csrf},files={'payment_proof':('proof.png',raw,'image/png')});assert result.status_code==200
    result=web.post(url,data={'csrf':csrf},files={'payment_proof':('proof.png',raw,'image/png')});assert result.status_code==200
    db.expire_all();sale=db.scalar(select(Sale).where(Sale.order_id==own.id))
    assert sale.status_pembayaran=='Belum dibayar' and db.get(Order,own.id).status=='Dikonfirmasi'
    assert db.scalar(select(func.count()).select_from(PaymentSubmission))==1
    assert db.scalar(select(func.count()).select_from(Notification).where(Notification.kind=='proof'))==1
    assert web.get(f'/pesanan/{foreign.id}/bukti/gambar').status_code==404
    assert web.get(url+'/gambar').headers['cache-control']=='no-store'
    csrf=signin(web,True)
    assert 'Lihat bukti anggota' in web.get(f'/pesanan/{own.id}/selesaikan').text
    result=web.post(f'/pesanan/{own.id}/status',data={'csrf':csrf,'status':'Selesai','metode':'Cashless'})
    assert result.status_code==200
    db.expire_all();sale=db.get(Sale,sale.id)
    assert sale.status_pembayaran=='Lunas' and sale.payment_proof and sale.payment_verified_by==a.id
    assert db.scalar(select(func.count()).select_from(Notification).where(Notification.kind=='payment'))==2


def test_notification_migration_additive_idempotent(tmp_path):
    from app.migrations import migrate_notifications
    from sqlalchemy import inspect
    engine=create_engine('sqlite:///'+str(tmp_path/'migration.db'))
    User.__table__.create(engine);Order.__table__.create(engine)
    migrate_notifications(engine);migrate_notifications(engine)
    assert {'notifications','payment_submissions'}.issubset(inspect(engine).get_table_names())
    engine.dispose()


def test_hpp_snapshot_confirmation_edit_and_cancellation(store):
    db,a,m,_,p,_,_=store
    p.hpp=40000;db.commit()
    order=create_order(db,m.id,{str(p.id):2},uuid4().hex);db.commit()
    assert order.lines[0].hpp is None
    p.hpp=45000;db.commit()
    transition(db,order.id,'Dikonfirmasi',a.id);db.commit()
    assert order.lines[0].hpp==45000
    p.hpp=60000;p.harga=90000;db.commit()
    transition(db,order.id,'Dikonfirmasi',a.id);db.commit()
    day=order.confirmed_at.replace(tzinfo=__import__('datetime').timezone.utc).astimezone(__import__('zoneinfo').ZoneInfo('Asia/Jakarta')).date().isoformat()
    result=analyze(db,'harian',day)
    assert result['total']==140000 and result['total_hpp']==90000 and result['gross_profit']==50000
    assert result['rows'][0]['hpp']==45000 and result['rows'][0]['laba_kotor']==50000
    assert result['cost_complete'] and result['missing_cost_units']==0
    transition(db,order.id,'Dibatalkan',a.id);db.commit()
    result=analyze(db,'harian',day)
    assert result['total']==0 and result['total_hpp']==0 and result['gross_profit']==0
    assert order.lines[0].hpp==45000


def test_hpp_unknown_zero_and_loss_are_distinguished(store):
    from app.models import utcnow
    db,a,m,_,p,second,_=store
    p.hpp=80000;second.hpp=None;db.commit()
    order=create_order(db,m.id,{str(p.id):1,str(second.id):1},uuid4().hex)
    transition(db,order.id,'Dikonfirmasi',a.id);db.commit()
    result=analyze(db,'tahunan',utcnow().date().isoformat())
    assert not result['cost_complete'] and result['missing_cost_units']==1
    assert result['total']==210000 and result['total_hpp'] is None and result['gross_profit'] is None
    assert result['known_cost']==80000 and result['known_profit']==-10000
    second.hpp=0;db.commit()
    # Filling a product cost today cannot repair an old unknown snapshot.
    assert not analyze(db,'tahunan',utcnow().date().isoformat())['cost_complete']
    transition(db,order.id,'Dibatalkan',a.id);db.commit()
    zero=create_order(db,m.id,{str(second.id):1},uuid4().hex)
    transition(db,zero.id,'Dikonfirmasi',a.id);db.commit()
    result=analyze(db,'tahunan',utcnow().date().isoformat())
    assert result['cost_complete'] and result['total_hpp']==0 and result['gross_profit']==140000


def test_hpp_admin_edit_validation_privacy_and_export(web,store):
    db,a,m,_,p,_,_=store
    p.label='Beras';p.hpp=43210;db.commit()
    signin(web);assert web.get(f'/produk/{p.id}/edit').status_code==403
    assert 'HPP per unit' not in web.get('/katalog').text
    assert web.get('/laporan').status_code==403
    csrf=signin(web,True)
    payload={'csrf':csrf,'id':p.id,'category_id':p.category_id,'nama':p.nama,'label':'Beras','harga':70000,'satuan':'pak','active':'on'}
    assert web.post('/produk/simpan',data={**payload,'hpp':'-1'}).status_code==400
    db.expire_all();assert db.get(Product,p.id).hpp==43210
    assert web.post('/produk/simpan',data={**payload,'hpp':'0'}).status_code==400
    assert web.post('/produk/simpan',data={**payload,'hpp':'60000'}).status_code==200
    db.expire_all();assert db.get(Product,p.id).hpp==60000
    assert web.post('/produk/simpan',data=payload).status_code==200
    db.expire_all();assert db.get(Product,p.id).hpp==60000
    order=create_order(db,m.id,{str(p.id):1},uuid4().hex);transition(db,order.id,'Dikonfirmasi',a.id);db.commit()
    # Actual test clock may vary; choose the real order year for the snapshot export.
    response=web.get('/laporan',params={'periode':'tahunan','tanggal':order.confirmed_at.date().isoformat(),'export':'xlsx'})
    from openpyxl import load_workbook
    workbook=load_workbook(BytesIO(response.content),data_only=True)
    summary=list(workbook['Ringkasan'].values);data=dict(zip(summary[0],summary[1]))
    assert data['total_hpp']==60000 and data['laba_kotor']==9000 and data['status_hpp']=='Lengkap'
    assert 'hpp' in next(workbook['Rincian'].values)
    assert 'Laba bersih tercatat' in web.get('/laporan').text


def test_hpp_migration_preserves_unknown_history(tmp_path):
    from sqlalchemy import text as sql_text
    from app.migrations import migrate_hpp
    engine=create_engine('sqlite:///'+str(tmp_path/'hpp.db'))
    with engine.begin() as conn:
        conn.execute(sql_text('CREATE TABLE products (id INTEGER PRIMARY KEY, harga BIGINT, stok INTEGER)'))
        conn.execute(sql_text('CREATE TABLE order_lines (id INTEGER PRIMARY KEY, subtotal BIGINT)'))
        conn.execute(sql_text('INSERT INTO products VALUES (1,70000,8)'))
        conn.execute(sql_text('INSERT INTO order_lines VALUES (1,140000)'))
    migrate_hpp(engine);migrate_hpp(engine)
    with engine.connect() as conn:
        assert tuple(conn.execute(sql_text('SELECT harga,stok,hpp FROM products')).one())==(70000,8,None)
        assert tuple(conn.execute(sql_text('SELECT subtotal,hpp FROM order_lines')).one())==(140000,None)
    engine.dispose()


def test_import_required_hpp_missing_and_invalid_cost(store):
    db,a,_,_,_,_,_=store
    frame=pd.DataFrame([
        dict(kode='HPP01',nama='Produk HPP',label='Beras',kategori='Bahan pokok',harga=10000,hpp=6000,stok=5,satuan='pak',_baris=2,_formula=False),
        dict(kode='HPP02',nama='Produk lama',label='Beras',kategori='Bahan pokok',harga=10000,hpp='',stok=5,satuan='pak',_baris=3,_formula=False),
        dict(kode='HPP03',nama='Produk gagal',label='Beras',kategori='Bahan pokok',harga=10000,hpp=-1,stok=5,satuan='pak',_baris=4,_formula=False)])
    result=save_rows(db,frame,a.id);db.commit()
    assert result['success']==1 and result['failed']==2
    assert db.scalar(select(Product).where(Product.source_code=='HPP01')).hpp==6000
    assert db.scalar(select(Product).where(Product.source_code=='HPP02')) is None


@pytest.mark.parametrize('cost,percentage,expected',[(3000,25,3800),(3000,20,3600),(3000,15,3500),(1,0,100),(100,0,100),(3333,'12.5',3800)])
def test_automatic_price_rounds_up_to_100(cost,percentage,expected):
    from app.pricing import selling_price
    assert selling_price(cost,percentage)==expected


def test_pricing_rejects_invalid_inputs():
    from app.pricing import selling_price,markup
    for cost in (None,'',0,-1,'1.2'):
        with pytest.raises(RuleError):selling_price(cost,10)
    for value in ('NaN','Infinity',-1,101,'1.001'):
        with pytest.raises(RuleError):markup(value)
    with pytest.raises(RuleError):selling_price(1000000000,100)


def test_category_markup_reprices_products_but_not_order_prices(web,store):
    db,a,m,_,p,second,_=store
    p.hpp=3000;p.label='Beras';db.commit()
    order=create_order(db,m.id,{str(p.id):1},uuid4().hex);db.commit()
    csrf=signin(web,True)
    response=web.post('/kategori/simpan',data={'csrf':csrf,'id':p.category_id,'active':'on','markup_percent':'25'})
    assert response.status_code==200
    db.expire_all();assert db.get(Product,p.id).harga==3800 and db.get(Product,second.id).harga==140000
    assert db.get(Order,order.id).total==70000 and order.lines[0].harga==70000
    transition(db,order.id,'Dikonfirmasi',a.id);db.commit()
    assert order.lines[0].hpp==3000
    # A forged selling price from a browser is ignored.
    response=web.post('/produk/simpan',data={'csrf':csrf,'id':p.id,'category_id':p.category_id,'nama':p.nama,'label':'Beras','satuan':'pak','hpp':'4000','harga':'1','active':'on'})
    assert response.status_code==200
    db.expire_all();assert db.get(Product,p.id).harga==5000 and order.total==70000
    assert web.post('/produk/simpan',data={'csrf':csrf,'id':p.id,'category_id':p.category_id,'nama':p.nama,'label':'Beras','satuan':'pak','hpp':''}).status_code==400
    assert web.post('/kategori/simpan',data={'csrf':csrf,'id':p.category_id,'markup_percent':'101'}).status_code==400


def test_pricing_migration_keeps_prices_and_custom_percentage(tmp_path):
    from sqlalchemy import text as sql_text
    from app.migrations import migrate_pricing
    engine=create_engine('sqlite:///'+str(tmp_path/'pricing.db'))
    with engine.begin() as conn:
        conn.execute(sql_text('CREATE TABLE categories (id INTEGER PRIMARY KEY,nama VARCHAR(100))'))
        conn.execute(sql_text("INSERT INTO categories VALUES (1,'Bahan pokok'),(2,'Perawatan'),(3,'Makanan ringan'),(4,'Minuman'),(5,'Kesehatan')"))
        conn.execute(sql_text('CREATE TABLE products (id INTEGER PRIMARY KEY,harga BIGINT)'))
        conn.execute(sql_text('INSERT INTO products VALUES (1,75000)'))
    migrate_pricing(engine)
    with engine.begin() as conn:
        assert [int(n) for n in conn.scalars(sql_text('SELECT markup_percent FROM categories ORDER BY id'))]==[10,20,25,15,10]
        conn.execute(sql_text('UPDATE categories SET markup_percent=12 WHERE id=1'))
    migrate_pricing(engine)
    with engine.connect() as conn:
        assert conn.scalar(sql_text('SELECT markup_percent FROM categories WHERE id=1'))==12
        assert conn.scalar(sql_text('SELECT harga FROM products'))==75000
    engine.dispose()


def test_operating_cost_periods_void_and_incomplete_hpp(store):
    from app.expenses import create_expense,void_expense
    from app.models import OperatingExpense
    db,a,m,_,p,_,_=store
    p.hpp=40000;db.commit()
    order=create_order(db,m.id,{str(p.id):1},uuid4().hex);transition(db,order.id,'Dikonfirmasi',a.id);db.commit()
    sale=db.scalar(select(Sale).where(Sale.order_id==order.id));sale.created_at=datetime(2026,11,16,0);db.commit()
    expense=create_expense(db,a.id,uuid4().hex,'2026-11-16','Listrik dan air','Listrik toko',10000)
    create_expense(db,a.id,uuid4().hex,'2026-11-15','Transportasi','Ongkos',2000)
    create_expense(db,a.id,uuid4().hex,'2026-12-01','Sewa','Sewa',5000);db.commit()
    for kind,expected in [('harian',20000),('mingguan',20000),('bulanan',18000),('tahunan',13000)]:
        assert analyze(db,kind,'2026-11-16')['net_profit']==expected
    void_expense(db,expense.id,a.id);db.commit();old=expense.voided_at
    void_expense(db,expense.id,a.id);db.commit();assert expense.voided_at==old
    assert analyze(db,'harian','2026-11-16')['net_profit']==30000
    order.lines[0].hpp=None;db.commit()
    result=analyze(db,'bulanan','2026-11-16');assert result['net_profit'] is None and result['expense_total']==2000
    # A period without sales can legitimately have a negative recorded net profit.
    assert analyze(db,'harian','2026-12-01')['net_profit']==-5000


def test_expense_http_admin_csrf_idempotent_and_export(web,store):
    from app.models import OperatingExpense
    signin(web)
    assert web.get('/biaya-operasional').status_code==403
    assert web.post('/biaya-operasional',data={}).status_code==403
    csrf=signin(web,True);page=web.get('/biaya-operasional')
    form_token=re.search(r'name="token" value="([a-f0-9]+)"',page.text).group(1)
    payload={'csrf':csrf,'token':form_token,'tanggal':'2026-11-18','category':'Transportasi','description':'Ongkos pemasok','amount':'12000'}
    assert web.post('/biaya-operasional',data={**payload,'csrf':'wrong'}).status_code==403
    for amount in ('-1','0','1.5'):
        assert web.post('/biaya-operasional',data={**payload,'amount':amount}).status_code==400
    assert web.post('/biaya-operasional',data=payload).status_code==200
    assert web.post('/biaya-operasional',data=payload).status_code==200
    db=store[0];assert db.scalar(select(func.count()).select_from(OperatingExpense))==1
    expense=db.scalar(select(OperatingExpense));assert expense.amount==12000
    response=web.get('/laporan?periode=harian&tanggal=2026-11-18&export=xlsx')
    from openpyxl import load_workbook
    book=load_workbook(BytesIO(response.content),data_only=True)
    summary=list(book['Ringkasan'].values);row=dict(zip(summary[0],summary[1]))
    assert row['biaya_operasional']==12000 and row['laba_bersih']==-12000
    assert 'Biaya operasional' in book.sheetnames
    assert web.post(f'/biaya-operasional/{expense.id}/batalkan',data={'csrf':csrf}).status_code==200
    db.expire_all();assert not db.get(OperatingExpense,expense.id).valid
    signin(web);assert web.post(f'/biaya-operasional/{expense.id}/batalkan',data={'csrf':csrf}).status_code==403


def test_estimated_hpp_initialization_preserves_actual_prices_stock_and_history(store):
    from app.expenses import initialize_product_costs
    db,a,m,_,p,second,_=store
    p.hpp=40000;db.commit()
    prior=create_order(db,m.id,{str(second.id):1},uuid4().hex);transition(db,prior.id,'Dikonfirmasi',a.id);db.commit()
    before=(p.harga,p.stok,second.harga,second.stok,prior.total)
    assert initialize_product_costs(db)==1;db.commit()
    assert p.hpp==40000 and not p.hpp_estimated
    assert second.hpp>0 and second.hpp_estimated
    assert (p.harga,p.stok,second.harga,second.stok,prior.total)==before
    assert prior.lines[0].hpp is None and not prior.lines[0].hpp_estimated
    assert initialize_product_costs(db)==0
    transition(db,prior.id,'Dibatalkan',a.id);db.commit()
    new=create_order(db,m.id,{str(second.id):1},uuid4().hex);transition(db,new.id,'Dikonfirmasi',a.id);db.commit()
    assert new.lines[0].hpp==second.hpp and new.lines[0].hpp_estimated
    result=analyze(db,'tahunan',new.confirmed_at.date().isoformat())
    assert result['estimated_cost_units']==1


def test_history_hpp_estimate_only_missing_and_preserves_known(store):
    from app.expenses import initialize_history_costs
    db,a,m,_,p,second,_=store
    p.hpp=40000;db.commit()
    known=create_order(db,m.id,{str(p.id):1},uuid4().hex);transition(db,known.id,'Dikonfirmasi',a.id)
    missing=create_order(db,m.id,{str(second.id):1},uuid4().hex);transition(db,missing.id,'Dikonfirmasi',a.id);db.commit()
    assert missing.lines[0].hpp is None
    second.hpp=100000;db.commit()
    before=(known.total,missing.total,p.stok,second.stok,missing.lines[0].harga,missing.lines[0].qty)
    assert initialize_history_costs(db)==1;db.commit()
    assert known.lines[0].hpp==40000 and not known.lines[0].hpp_estimated
    assert missing.lines[0].hpp==121739 and missing.lines[0].hpp_estimated
    assert (known.total,missing.total,p.stok,second.stok,missing.lines[0].harga,missing.lines[0].qty)==before
    assert initialize_history_costs(db)==0
    result=analyze(db,'tahunan',missing.confirmed_at.date().isoformat())
    assert result['cost_complete'] and result['total_hpp']==161739 and result['estimated_cost_units']==1


def test_monthly_plan_conservative_break_even_math():
    from app.expenses import plan_calculation
    result=plan_calculation(1500000,20000000,10)
    assert result['bep']==16500000 and result['projected_net']==318181 and result['covered']
    assert str(result['required_markup'])=='8.11'
    result=plan_calculation(1500000,10000000,10);assert not result['covered'] and result['projected_net']<0
    result=plan_calculation(1500000,1000000,0);assert result['bep'] is None and result['required_markup'] is None and not result['covered']


def test_monthly_plan_admin_only_not_actual_expense(web,store):
    from app.models import MonthlyPlan,OperatingExpense
    signin(web);assert web.post('/biaya-operasional/rencana',data={}).status_code==403
    csrf=signin(web,True)
    page=web.get('/biaya-operasional');assert 'SIMULASI BULANAN' not in page.text and 'Simpan rencana' not in page.text
    assert store[0].get(MonthlyPlan,1) is None
    assert web.post('/biaya-operasional/rencana',data={'csrf':csrf,'budget':1000000,'target_revenue':15000000}).status_code==200
    assert store[0].get(MonthlyPlan,1).budget==1000000
    assert store[0].scalar(select(func.count()).select_from(OperatingExpense))==0
    report=web.get('/laporan').text
    assert 'Omzet minimal impas' not in report and '<span class="stat-label">Laba kotor</span>' not in report


def test_stylesheet_version_changes_after_build(web,tmp_path,monkeypatch):
    import importlib
    module=importlib.import_module('app.main')
    css=tmp_path/'static'/'tailwind.css';css.parent.mkdir();css.write_text('/* CSS fixture */',encoding='utf-8')
    monkeypatch.setattr(module,'ROOT',tmp_path)
    first=web.get('/login').text
    version=re.search(r'/static/tailwind.css\?v=(\d+)',first).group(1)
    assert version==str(css.stat().st_mtime_ns)
    next_time=css.stat().st_mtime_ns+1000000000
    os.utime(css,ns=(next_time,next_time))
    second=web.get('/login').text
    assert re.search(r'/static/tailwind.css\?v=(\d+)',second).group(1)!=version
