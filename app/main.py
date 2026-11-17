from pathlib import Path
from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo
from uuid import uuid4
import os
import secrets
import re
import pandas as pd
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, OperationalError
from .db import get_db
from .models import User, Category, Product, Order, Sale, StockMovement
from .security import hash_password, verify_password, csrf_token, check_csrf
from .services import RuleError, integer, text, code, movement, create_order, transition
from .product_images import product_image, default_product_image, valid_product_image
from .product_codes import next_product_code, choose_prefix
from .analytics import analyze
from .taxonomy import CATEGORIES, category_name

ROOT=Path(__file__).resolve().parent
app=FastAPI(title='SIKOS — Koperasi Sejahtera',version='1.0.0')
secret=os.getenv('SESSION_SECRET')
if not secret or len(secret)<32:
    raise RuntimeError('Isi SESSION_SECRET minimal 32 karakter di .env sebelum menjalankan aplikasi.')
app.add_middleware(SessionMiddleware,secret_key=secret,same_site='lax',https_only=os.getenv('COOKIE_SECURE','0')=='1',max_age=8*3600)
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
templates=Jinja2Templates(directory=ROOT/'templates')
templates.env.filters['rupiah']=lambda n: 'Rp'+format(int(n or 0),',').replace(',','.')
def wib(value):
    from datetime import timezone
    return value.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Asia/Jakarta')).strftime('%d %b %Y %H:%M') if value else '—'
templates.env.filters['wib']=wib
templates.env.filters['product_image']=product_image
templates.env.filters['default_product_image']=default_product_image

def page(request,name,**context):
    context.update(csrf=csrf_token(request),notice=request.session.pop('notice',None),category_choices=CATEGORIES)
    return templates.TemplateResponse(request=request,name=name,context=context)

def go(url,request=None,message=None):
    if request is not None and message:
        request.session['notice']=message
    return RedirectResponse(url,status_code=303)

def current(request:Request,db:Session=Depends(get_db)):
    user=db.get(User,request.session.get('uid',0))
    if user is None or not user.active:
        raise HTTPException(303,headers={'Location':'/login'})
    return user

def admin(user:User=Depends(current)):
    if user.role!='admin': raise HTTPException(403,'Halaman ini khusus admin koperasi.')
    return user


def buyer(user:User=Depends(current)):
    if user.role != 'anggota':
        raise HTTPException(403, 'Halaman ini khusus pembeli koperasi.')
    return user


@app.exception_handler(HTTPException)
async def http_error(request,exc):
    if exc.status_code==303:return go(exc.headers.get('Location','/login'))
    response=page(request,'error.html',user=None,error=exc.detail)
    response.status_code=exc.status_code
    return response

@app.exception_handler(RuleError)
async def rule_error(request,exc):
    response=page(request,'error.html',user=None,error=str(exc));response.status_code=400;return response

@app.exception_handler(ValueError)
async def value_error(request,exc):
    response=page(request,'error.html',user=None,error='Nilai formulir tidak valid. Periksa kembali input.');response.status_code=400;return response

@app.exception_handler(IntegrityError)
async def duplicate_error(request,exc):
    response=page(request,'error.html',user=None,error='Nomor anggota, email, kode produk, atau nama kategori sudah digunakan. Periksa duplikasi. Tidak ada perubahan parsial yang disimpan.');response.status_code=409;return response

@app.exception_handler(OperationalError)
async def database_error(request,exc):
    response=page(request,'error.html',user=None,error='Database belum siap atau sedang sibuk. Periksa MySQL dan .env. Untuk transaksi yang gagal, muat ulang lalu coba lagi.');response.status_code=503;return response

@app.get('/login', response_class=HTMLResponse)
def login_page(request: Request):
    return page(request, 'login.html', user=None) 

@app.post('/logout')
async def logout(request: Request):
    form = await request.form()
    check_csrf(request, form)

    request.session.clear()

    return go('/login')


@app.post('/login')
async def login_submit(request:Request,db:Session=Depends(get_db)):
    form=await request.form()
    check_csrf(request,form)

    user=db.scalar(
        select(User).where(
            User.email==str(form.get('email','')).strip().lower()
        )
    )

    if user is None or not user.active or not verify_password(
        str(form.get('password','')),user.password_hash
    ):
        return page(
            request,
            'login.html',
            user=None,
            error='Email atau password salah, atau akun nonaktif.'
        )

    request.session.clear()
    request.session['uid']=user.id

    if user.role=='admin':
        return go('/')

    return go('/anggota/dashboard')


@app.get('/daftar')
def register_page(request:Request):
    return page(request,'member_form.html',user=None,member=None,register=True)

@app.post('/daftar')
async def register_submit(request:Request,db:Session=Depends(get_db)):
    form=await request.form()
    check_csrf(request,form)

    if str(form.get('password','')) != str(form.get('password_confirm','')):
        raise RuleError('Konfirmasi password tidak sama.')

    member=User(
        nomor='AG-'+uuid4().hex[:12].upper(),
        role='anggota',
        active=True
    )

    apply_member(member,form,new=True)
    db.add(member)
    db.commit()

    return go('/login',request,'Pendaftaran berhasil. Silakan login menggunakan email.')

@app.get('/')
def dashboard(request:Request,user:User=Depends(current),db:Session=Depends(get_db)):
    if user.role!='admin':return go('/katalog')
    kind=request.query_params.get('periode','bulanan')
    day=request.query_params.get('tanggal',datetime.now(ZoneInfo('Asia/Jakarta')).date().isoformat())
    analysis=analyze(db,kind,day)
    stock=db.scalars(select(Product).join(Category).where(Product.active.is_(True),Category.active.is_(True)).order_by(Product.stok.desc(),Product.kode).limit(5)).all()
    return page(request,'dashboard.html',user=user,analysis=analysis,stock=stock,
                member_count=db.scalar(select(func.count()).select_from(User).where(User.role=='anggota',User.active.is_(True))),
                product_count=db.scalar(select(func.count()).select_from(Product).where(Product.active.is_(True))),
                pending=db.scalar(select(func.count()).select_from(Order).where(Order.status=='Menunggu konfirmasi')))



def apply_member(member, form, new=False):
    member.nama = text(form.get('nama'), 'Nama')
    member.email = text(form.get('email'), 'Email', 190).lower()

    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', member.email):
        raise RuleError('Format email tidak valid.')

    member.telepon = text(form.get('telepon'), 'Telepon', 30)
    member.alamat = text(form.get('alamat'), 'Alamat', 2000)

    password = str(form.get('password', ''))

    if new or password:
        if len(password) < 8 or len(password) > 128:
            raise RuleError('Password harus 8–128 karakter.')

        member.password_hash = hash_password(password)


@app.get('/anggota')
def members(request:Request,user:User=Depends(admin),db:Session=Depends(get_db)):
    return page(request,'members.html',user=user,members=db.scalars(select(User).where(User.role=='anggota').order_by(User.nama)).all())

@app.get('/anggota/tambah')
def member_add_page(request:Request,user:User=Depends(admin)):
    return page(request,'member_form.html',user=user,member=None,register=False)

@app.get('/anggota/{member_id}/edit')
def member_edit_page(member_id:int,request:Request,user:User=Depends(admin),db:Session=Depends(get_db)):
    member=db.get(User,member_id)
    if member is None or member.role!='anggota':raise HTTPException(404,'Anggota tidak ditemukan.')
    return page(request,'member_form.html',user=user,member=member,register=False)

@app.post('/anggota/simpan')
async def member_save(request:Request,user:User=Depends(admin),db:Session=Depends(get_db)):
    form=await request.form();check_csrf(request,form)
    member_id=form.get('id')
    member=db.get(User,integer(member_id,'ID')) if member_id else User(role='anggota')
    if member is None or member.role!='anggota':raise HTTPException(404,'Anggota tidak ditemukan.')
    member.nomor=text(form.get('nomor'),'Nomor anggota',40).upper()
    apply_member(member,form,new=not bool(member_id))
    member.active=form.get('active')=='on'
    db.add(member);db.commit();return go('/anggota',request,'Data anggota disimpan.')

@app.post('/anggota/{member_id}/hapus')
async def member_delete(member_id:int,request:Request,user:User=Depends(admin),db:Session=Depends(get_db)):
    form=await request.form();check_csrf(request,form)
    member=db.get(User,member_id)
    if member is None or member.role!='anggota':raise HTTPException(404,'Anggota tidak ditemukan.')
    member.active=False;db.commit();return go('/anggota',request,'Anggota dinonaktifkan. Riwayat transaksi tetap tersimpan.')

@app.get('/kategori')
def categories(request:Request,user:User=Depends(admin),db:Session=Depends(get_db)):
    return page(request,'categories.html',user=user,categories=db.scalars(select(Category).order_by(Category.nama)).all())

@app.post('/kategori/simpan')
async def category_save(request:Request,user:User=Depends(admin),db:Session=Depends(get_db)):
    form=await request.form();check_csrf(request,form)
    if not form.get('id'):
        name=category_name(form.get('nama'))
        if db.scalar(select(Category).where(func.lower(Category.nama)==name.lower())):
            return go('/kategori',request,'Nama kategori sudah tersedia. Tidak ada kategori duplikat yang ditambahkan.')
        used=set(db.scalars(select(Category.code_prefix).where(Category.code_prefix.is_not(None))))
        prefix=choose_prefix(name,used,form.get('code_prefix',''))
        category=Category(nama=name,code_prefix=prefix,code_counter=0,active=form.get('active')=='on')
        db.add(category)
        try:db.commit()
        except IntegrityError:
            db.rollback()
            return go('/kategori',request,'Nama kategori atau awalan kode sudah digunakan. Periksa kembali.')
        return go('/kategori',request,'Kategori baru berhasil ditambahkan.')
    category=db.get(Category,integer(form['id'],'ID'))
    if category is None:raise HTTPException(404,'Kategori tidak ditemukan.')
    category.active=form.get('active')=='on'
    db.commit();return go('/kategori',request,'Status kategori disimpan.')

@app.post('/kategori/{category_id}/hapus')
async def category_delete(category_id:int,request:Request,user:User=Depends(admin),db:Session=Depends(get_db)):
    form=await request.form();check_csrf(request,form)
    category=db.get(Category,category_id)
    if category is None:raise HTTPException(404,'Kategori tidak ditemukan.')
    category.active=False;db.commit();return go('/kategori',request,'Kategori dinonaktifkan dan disembunyikan dari katalog.')

@app.get('/produk')
def products(request:Request,user:User=Depends(admin),db:Session=Depends(get_db)):
    query=request.query_params.get('q','').strip()[:100]
    category=request.query_params.get('kategori','')
    statement=select(Product)
    if query:
        escaped=query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        statement=statement.where(or_(Product.nama.ilike('%'+escaped+'%',escape='\\'),Product.kode.ilike('%'+escaped+'%',escape='\\'),Product.label.ilike('%'+escaped+'%',escape='\\')))
    if category:
        category_id=integer(category,'Kategori')
        if db.get(Category,category_id) is None:raise RuleError('Kategori tidak ditemukan.')
        statement=statement.where(Product.category_id==category_id)
        category=str(category_id)
    return page(request,'products.html',user=user,products=db.scalars(statement.order_by(Product.nama)).all(),
                categories=db.scalars(select(Category).order_by(Category.nama)).all(),query=query,category=category,
                total_count=db.scalar(select(func.count()).select_from(Product)))

def product_labels(db):
    # Include archived products so historical labels remain selectable during maintenance.
    values=db.scalars(select(Product.label).where(Product.label!='').distinct()).all()
    labels={}
    for value in sorted(values):
        value=value.strip()
        if value:labels.setdefault(value.casefold(),value)
    return sorted(labels.values(),key=str.casefold)

@app.get('/produk/tambah')
def product_add_page(request:Request,user:User=Depends(admin),db:Session=Depends(get_db)):
    return page(request,'product_form.html',user=user,product=None,categories=db.scalars(select(Category).where(Category.active.is_(True))).all(),labels=product_labels(db))

@app.get('/produk/{product_id}/edit')
def product_edit_page(product_id:int,request:Request,user:User=Depends(admin),db:Session=Depends(get_db)):
    product=db.get(Product,product_id)
    if product is None:raise HTTPException(404,'Produk tidak ditemukan.')
    return page(request,'product_form.html',user=user,product=product,categories=db.scalars(select(Category)).all(),labels=product_labels(db))

@app.get('/produk/kode-berikutnya')
def product_code_preview(category_id:int,product_id:int|None=None,user:User=Depends(admin),db:Session=Depends(get_db)):
    if product_id is not None:
        product=db.get(Product,product_id)
        if product is None:raise HTTPException(404,'Produk tidak ditemukan.')
        if product.category_id==category_id:return {'kode':product.kode,'tetap':True}
    return {'kode':next_product_code(db,category_id,reserve=False),'tetap':False}

@app.post('/produk/simpan')
async def product_save(request:Request,user:User=Depends(admin),db:Session=Depends(get_db)):
    form=await request.form();check_csrf(request,form)
    product_id=form.get('id')
    product=db.scalar(select(Product).where(Product.id==integer(product_id,'ID')).with_for_update()) if product_id else Product(stok=0)
    if product is None:raise HTTPException(404,'Produk tidak ditemukan.')
    category=db.get(Category,integer(form.get('category_id'),'Kategori'))
    if category is None or not category.active:raise RuleError('Pilih kategori yang aktif.')
    if not product_id or product.category_id!=category.id:
        product.kode=next_product_code(db,category.id)
    product.nama=text(form.get('nama'),'Nama produk')
    chosen_label=text(form.get('label'),'Label',100)
    if chosen_label not in product_labels(db):raise RuleError('Pilih label yang tersedia pada dropdown.')
    product.label=chosen_label
    product.category_id=category.id;product.harga=integer(form.get('harga'),'Harga')
    product.satuan=text(form.get('satuan'),'Satuan',30)
    product.deskripsi=str(form.get('deskripsi','')).strip()[:5000]
    image=str(form.get('gambar','')).strip()
    if image and not valid_product_image(image):raise RuleError('Gunakan URL gambar HTTPS atau foto lokal produk yang tersedia, maksimal 500 karakter.')
    product.gambar=image;product.active=form.get('active')=='on'
    db.add(product);db.flush()
    if not product_id:movement(db,product,integer(form.get('stok'),'Stok awal',True),user.id,'Stok awal produk manual')
    db.commit();return go('/produk',request,'Produk disimpan.')

@app.post('/produk/{product_id}/hapus')
async def product_delete(product_id:int,request:Request,user:User=Depends(admin),db:Session=Depends(get_db)):
    form=await request.form();check_csrf(request,form)
    product=db.scalar(select(Product).where(Product.id==product_id).with_for_update())
    if product is None:raise HTTPException(404,'Produk tidak ditemukan.')
    product.active=False;db.commit();return go('/produk',request,'Produk diarsipkan. Riwayat pesanan dan stok tetap dapat ditelusuri.')

@app.get('/stok')
def stock_page(request:Request,user:User=Depends(admin),db:Session=Depends(get_db)):
    return page(request,'stock.html',user=user,products=db.scalars(select(Product).order_by(Product.nama)).all(),movements=db.scalars(select(StockMovement).order_by(StockMovement.id.desc()).limit(300)).all())

@app.post('/stok')
async def stock_save(request:Request,user:User=Depends(admin),db:Session=Depends(get_db)):
    form=await request.form();check_csrf(request,form)
    product=db.scalar(select(Product).where(Product.id==integer(form.get('product_id'),'Produk')).with_for_update())
    if product is None:raise HTTPException(404,'Produk tidak ditemukan.')
    qty=integer(form.get('qty'),'Jumlah');direction=form.get('direction')
    if direction not in ['masuk','keluar']:raise RuleError('Pilih barang masuk atau keluar.')
    movement(db,product,qty if direction=='masuk' else -qty,user.id,text(form.get('alasan'),'Alasan',200))
    db.commit();return go('/stok',request,'Perubahan stok dicatat.')

# ROUTE DASHBOARD ANGGOTA
@app.get('/anggota/dashboard')
def member_dashboard(
    request: Request,
    user: User = Depends(buyer),
    db: Session = Depends(get_db)
):
    product_count = db.scalar(
        select(func.count())
        .select_from(Product)
        .join(Category)
        .where(
            Product.active.is_(True),
            Category.active.is_(True)
        )
    ) or 0

    category_count = db.scalar(
        select(func.count())
        .select_from(Category)
        .where(Category.active.is_(True))
    ) or 0

    featured_products = db.scalars(
        select(Product)
        .join(Category)
        .where(
            Product.active.is_(True),
            Category.active.is_(True)
        )
        .order_by(Product.stok.desc(), Product.nama)
        .limit(4)
    ).all()

    return page(
        request,
        'member_dashboard.html',
        user=user,
        product_count=product_count,
        category_count=category_count,
        featured_products=featured_products
    )

@app.get('/katalog')
def catalog(
    request: Request,
    user: User = Depends(buyer),
    db: Session = Depends(get_db)
):
    query = request.query_params.get('q', '').strip()[:100]
    category = request.query_params.get('kategori', '')

    statement = (
        select(Product)
        .join(Category)
        .where(
            Product.active.is_(True),
            Category.active.is_(True)
        )
    )

    if query:
        escaped = (
            query.replace('\\', '\\\\')
            .replace('%', '\\%')
            .replace('_', '\\_')
        )

        statement = statement.where(
            or_(
                Product.nama.ilike(
                    '%' + escaped + '%',
                    escape='\\'
                ),
                Product.label.ilike(
                    '%' + escaped + '%',
                    escape='\\'
                )
            )
        )

    if category:
        statement = statement.where(
            Product.category_id == integer(category, 'Kategori')
        )

    products = db.scalars(
        statement.order_by(Product.nama)
    ).all()

    categories = db.scalars(
        select(Category).where(Category.active.is_(True))
    ).all()

    return page(
        request,
        'catalog.html',
        user=user,
        products=products,
        categories=categories,
        query=query,
        category=category
    )

def cart_rows(request,db):
    rows=[];total=0
    for key,qty in request.session.get('cart',{}).items():
        product=db.get(Product,int(key))
        if product:
            subtotal=product.harga*qty;total+=subtotal
            rows.append(dict(product=product,qty=qty,subtotal=subtotal,available=product.active and product.category.active and qty<=product.stok))
    return rows,total

@app.post('/keranjang/tambah')
async def cart_add(request:Request,user:User=Depends(buyer),db:Session=Depends(get_db)):
    form=await request.form();check_csrf(request,form)
    product=db.get(Product,integer(form.get('product_id'),'Produk'));qty=integer(form.get('qty'),'Jumlah')
    if product is None or not product.active or not product.category.active:raise RuleError('Produk tidak tersedia.')
    cart=dict(request.session.get('cart',{}));key=str(product.id)
    qty+=cart.get(key,0)
    if qty>product.stok:raise RuleError('Jumlah melebihi stok tersedia.')
    if key not in cart and len(cart)>=100:raise RuleError('Maksimal 100 jenis barang.')
    cart[key]=qty;request.session['cart']=cart
    request.session['checkout_token']=uuid4().hex
    return go('/keranjang',request,'Barang ditambahkan ke keranjang.')

@app.get('/keranjang')
def cart_page(request:Request,user:User=Depends(buyer),db:Session=Depends(get_db)):
    rows,total=cart_rows(request,db)
    token=request.session.setdefault('checkout_token',uuid4().hex)
    return page(request,'cart.html',user=user,rows=rows,total=total,token=token,can_checkout=bool(rows) and all(row['available'] for row in rows))

def submitted_cart(request,form,db):
    cart={}
    for key in request.session.get('cart',{}):
        qty=integer(form.get('qty_'+key,request.session['cart'][key]),'Jumlah',True)
        if qty:
            product=db.get(Product,int(key))
            if product is None or not product.active or not product.category.active or qty>product.stok:
                raise RuleError('Barang tidak aktif atau stok tidak cukup. Sesuaikan jumlah atau hapus barang.')
            cart[key]=qty
    return cart

def cart_problem(request,user,db,error):
    request.session.setdefault('checkout_token',uuid4().hex)
    # Render with the same account and saved cart; failed updates never save partially.
    rows,total=cart_rows(request,db)
    response=page(request,'cart.html',user=user,rows=rows,total=total,
                  token=request.session['checkout_token'],can_checkout=bool(rows) and all(row['available'] for row in rows),error=str(error))
    response.status_code=400
    return response

@app.post('/keranjang/ubah')
async def cart_update(request:Request,user:User=Depends(buyer),db:Session=Depends(get_db)):
    form=await request.form();check_csrf(request,form)
    try:
        cart=submitted_cart(request,form,db)
    except RuleError as exc:
        return cart_problem(request,user,db,exc)
    request.session['cart']=cart;request.session['checkout_token']=uuid4().hex
    return go('/keranjang',request,'Keranjang diperbarui.')

@app.post('/keranjang/hapus')
async def cart_remove(request:Request,user:User=Depends(buyer)):
    form=await request.form();check_csrf(request,form)
    key=str(integer(form.get('product_id'),'Produk'))
    cart=dict(request.session.get('cart',{}));cart.pop(key,None)
    request.session['cart']=cart;request.session['checkout_token']=uuid4().hex
    return go('/keranjang',request,'Barang dihapus dari keranjang.')

@app.post('/pesanan/buat')
async def order_create(request:Request,user:User=Depends(buyer),db:Session=Depends(get_db)):
    form=await request.form();check_csrf(request,form)
    token=str(form.get('token',''))
    prior=db.scalar(select(Order).where(Order.member_id==user.id,Order.token==token))
    if prior:return go('/pesanan')
    if not secrets.compare_digest(token,request.session.get('checkout_token','!')):raise RuleError('Keranjang berubah. Muat ulang halaman keranjang.')
    try:
        cart=submitted_cart(request,form,db)
        order=create_order(db,user.id,cart,token)
    except RuleError as exc:
        db.rollback()
        return cart_problem(request,user,db,exc)
    db.commit();request.session['cart']={};request.session.pop('checkout_token',None)
    return go('/pesanan',request,f'{order.kode} dibuat. Stok akan dikurangi saat admin mengonfirmasi.')

@app.get('/pesanan')
def order_list(request:Request,user:User=Depends(current),db:Session=Depends(get_db)):
    statement=select(Order).order_by(Order.id.desc())
    if user.role!='admin':statement=statement.where(Order.member_id==user.id)
    return page(request,'orders.html',user=user,orders=db.scalars(statement).all())

@app.post('/pesanan/{order_id}/status')
async def order_status(order_id:int,request:Request,user:User=Depends(admin),db:Session=Depends(get_db)):
    form=await request.form();check_csrf(request,form)
    transition(db,order_id,str(form.get('status','')),user.id);db.commit()
    return go('/pesanan',request,'Status pesanan diperbarui.')

@app.get('/transaksi')
def sales_page(request:Request,user:User=Depends(admin),db:Session=Depends(get_db)):
    rows=db.execute(select(Sale,Order).join(Order,Sale.order_id==Order.id).order_by(Sale.id.desc())).all()
    return page(request,'sales.html',user=user,rows=rows)

@app.get('/laporan')
def report_page(request:Request,user:User=Depends(admin),db:Session=Depends(get_db)):
    kind=request.query_params.get('periode','harian');day=request.query_params.get('tanggal',datetime.now(ZoneInfo('Asia/Jakarta')).date().isoformat())
    analysis=analyze(db,kind,day)
    if request.query_params.get('export')=='xlsx':
        buffer=BytesIO()
        frame=pd.DataFrame(analysis['rows'],columns=['pesanan','anggota','tanggal','kode','produk','jumlah','harga','subtotal'])
        with pd.ExcelWriter(buffer,engine='openpyxl') as writer:
            frame.to_excel(writer,index=False,sheet_name='Rincian')
            pd.DataFrame([{'periode':kind,'tanggal_acuan':day,'transaksi':analysis['transactions'],'unit':analysis['units'],'penjualan':analysis['total']}]).to_excel(writer,index=False,sheet_name='Ringkasan')
            for sheet in writer.book:
                for row in sheet:
                    for cell in row:
                        if isinstance(cell.value,str):cell.data_type='s'
                sheet.freeze_panes='A2'
        return Response(buffer.getvalue(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename="laporan_{kind}_{day}.xlsx"'})
    return page(request,'reports.html',user=user,analysis=analysis)

@app.get('/impor')
def import_page(request:Request,user:User=Depends(admin)):
    return page(request,'import.html',user=user,result=None)

@app.get('/impor/template')
def import_template(user:User=Depends(admin)):
    buffer=BytesIO()
    pd.DataFrame([{'kode':'IMP001','nama':'Beras premium 5 kg','label':'Beras','kategori':'Bahan pokok','harga':75000,'stok':10,'satuan':'karung','deskripsi':'Contoh data'}]).to_excel(buffer,index=False,engine='openpyxl')
    return Response(buffer.getvalue(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="template_produk_sikos.xlsx"'})

@app.post('/impor')
async def import_submit(request:Request,user:User=Depends(admin),db:Session=Depends(get_db)):
    form=await request.form();check_csrf(request,form)
    upload=form.get('file')
    if upload is None or not hasattr(upload,'read') or not upload.filename.lower().endswith('.xlsx'):raise RuleError('Pilih file .xlsx.')
    raw=await upload.read(10*1024*1024+1)
    if len(raw)>10*1024*1024:raise RuleError('Ukuran file maksimal 10 MB.')
    from .importer import load_rows, save_rows
    frame=load_rows(raw)
    result=save_rows(db,frame,user.id)
    db.commit()
    return page(request,'import.html',user=user,result=result)
