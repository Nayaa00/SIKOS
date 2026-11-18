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
from sqlalchemy import select, func, or_, update
from sqlalchemy.orm import Session, selectinload, joinedload, object_session
from sqlalchemy.exc import IntegrityError, OperationalError
from .db import get_db
from .models import User, Category, Product, Order, Sale, StockMovement, Notification, PaymentSubmission, utcnow
from .security import hash_password, verify_password, csrf_token, check_csrf
from .services import RuleError, integer, text, code, movement, create_order, transition, record_payment, cancel_member_order, complete_cash_order, complete_cashless_order
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
    user=context.get('user')
    if user is not None and object_session(user) is not None:
        from .notifications import inbox, unread
        db=object_session(user)
        with db.no_autoflush:
            context.update(notification_unread=unread(db,user.id),notification_recent=inbox(db,user.id))

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


# ==========================================
# EDIT PROFIL ANGGOTA
# ==========================================

PROFILE_FIELDS = ('nama','email','telepon','alamat')

def profile_result(request,user,values=None,error=None,status=200):
    response=page(request,'profile.html',user=user,values=values or {k:getattr(user,k) for k in PROFILE_FIELDS},error=error)
    response.status_code=status
    return response

@app.get('/profil', response_class=HTMLResponse)
def profile_page(request:Request,user:User=Depends(buyer)):
    return profile_result(request,user)

@app.post('/profil', response_class=HTMLResponse)
async def profile_update(request:Request,user:User=Depends(buyer),db:Session=Depends(get_db)):
    form=await request.form();check_csrf(request,form)
    values={k:str(form.get(k,getattr(user,k))).strip() for k in PROFILE_FIELDS}
    values['email']=values['email'].lower()
    try:
        values['nama']=text(values['nama'],'Nama',150)
        values['email']=text(values['email'],'Email',190)
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',values['email']):
            raise RuleError('Alamat email tidak valid.')
        values['telepon']=text(values['telepon'],'Telepon',30)
        values['alamat']=text(values['alamat'],'Alamat',2000)
        if db.scalar(select(User.id).where(User.email==values['email'],User.id!=user.id)):
            return profile_result(request,user,values,'Email sudah digunakan oleh akun lain.',409)
        old=str(form.get('password_lama',''))
        new=str(form.get('password_baru',''))
        confirm=str(form.get('konfirmasi_password',''))
        if old or new or confirm:
            if not 8<=len(new)<=128:raise RuleError('Password baru harus 8 sampai 128 karakter.')
            if not verify_password(old,user.password_hash):raise RuleError('Password lama tidak sesuai.')
            if new!=confirm:raise RuleError('Konfirmasi password baru tidak cocok.')
        # Validate the complete form before changing any persisted attributes.
        password_hash=hash_password(new) if new else None
        for key,value in values.items():setattr(user,key,value)
        if password_hash:user.password_hash=password_hash
        db.commit()
    except RuleError as exc:
        return profile_result(request,user,values,str(exc),400)
    except IntegrityError:
        db.rollback()
        return profile_result(request,user,values,'Email sudah digunakan oleh akun lain.',409)
    return go('/profil',request,'Profil berhasil diperbarui!')


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
            values={'email':str(form.get('email','')).strip()},
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
    form=await request.form();check_csrf(request,form)
    # Password values are never rendered back into the form or saved in the session.
    values={k:str(form.get(k,'')).strip() for k in PROFILE_FIELDS}
    def invalid(message,status=400):
        response=page(request,'member_form.html',user=None,member=None,register=True,values=values,error=message)
        response.status_code=status
        return response
    try:
        if str(form.get('password',''))!=str(form.get('password_confirm','')):
            raise RuleError('Konfirmasi password tidak sama.')
        member=User(nomor='AG-'+uuid4().hex[:12].upper(),role='anggota',active=True)
        apply_member(member,form,new=True)
        if db.scalar(select(User.id).where(User.email==member.email)):
            return invalid('Email sudah terdaftar. Gunakan email lain atau masuk ke akun Anda.',409)
        db.add(member);db.commit()
    except RuleError as exc:
        return invalid(str(exc))
    except IntegrityError:
        db.rollback()
        return invalid('Email sudah terdaftar. Gunakan email lain atau masuk ke akun Anda.',409)
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
    apply_member(member, form, new=not bool(member_id))
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
    return page(request,'products.html',user=user,products=db.scalars(statement.options(joinedload(Product.category)).order_by(Product.nama)).all(),
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
    movements=db.scalars(select(StockMovement).options(joinedload(StockMovement.product),joinedload(StockMovement.actor)).order_by(StockMovement.id.desc()).limit(300)).all()
    ids={m.product_id for m in movements}
    first_ids=select(func.min(StockMovement.id)).where(StockMovement.product_id.in_(ids)).group_by(StockMovement.product_id)
    first_movements=db.scalars(select(StockMovement).where(StockMovement.id.in_(first_ids))).all() if ids else []
    initial_stocks={m.product_id:(m.after if m.delta>=0 and not m.order_id else m.after-m.delta) for m in first_movements}
    return page(request,'stock.html',user=user,products=db.scalars(select(Product).order_by(Product.nama)).all(),movements=movements,initial_stocks=initial_stocks)

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
    featured_products = db.scalars(
        select(Product)
        .join(Category)
        .where(
            Product.active.is_(True),
            Category.active.is_(True)
        )
        .options(joinedload(Product.category))
        .order_by(Product.stok.desc(), Product.nama)
        .limit(4)
    ).all()

    return page(
        request,
        'member_dashboard.html',
        user=user,
        order_counts=dict(db.execute(select(Order.status,func.count()).where(Order.member_id==user.id).group_by(Order.status)).all()),
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
        statement.options(joinedload(Product.category)).order_by(Product.nama)
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
    cart=request.session.get('cart',{})
    products={str(p.id):p for p in db.scalars(select(Product).options(joinedload(Product.category))
              .where(Product.id.in_([int(key) for key in cart])))} if cart else {}
    rows=[];total=0
    for key,qty in cart.items():
        product=products.get(key)
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

ORDER_STATUSES=('Menunggu konfirmasi','Dikonfirmasi','Selesai','Dibatalkan')

def history_window(request,db,statement):
    try:number=max(1,min(100000,int(request.query_params.get('halaman','1'))))
    except ValueError:number=1
    total=db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    pages=max(1,(total+19)//20);number=min(number,pages)
    return statement.limit(20).offset((number-1)*20),dict(number=number,pages=pages,total=total)

@app.get('/pesanan')
def order_list(request:Request,user:User=Depends(current),db:Session=Depends(get_db)):
    statement=select(Order).order_by(Order.id.desc())
    if user.role!='admin':statement=statement.where(Order.member_id==user.id)
    status=request.query_params.get('status','')
    if status not in ORDER_STATUSES:status=''
    if status:statement=statement.where(Order.status==status)
    statement,window=history_window(request,db,statement)
    orders=db.scalars(statement.options(selectinload(Order.lines),joinedload(Order.member))).all()
    return page(request,'orders.html',user=user,orders=orders,window=window,status=status,statuses=ORDER_STATUSES)

@app.post('/pesanan/{order_id}/batal')
async def order_cancel(order_id:int,request:Request,user:User=Depends(buyer),db:Session=Depends(get_db)):
    form=await request.form();check_csrf(request,form)
    try:
        cancel_member_order(db,order_id,user.id);db.commit()
    except RuleError as exc:
        db.rollback()
        return go('/pesanan',request,str(exc))
    return go('/pesanan',request,'Pesanan dibatalkan. Stok tidak berubah.')

@app.get('/transaksi-saya')
def member_sales(request:Request,user:User=Depends(buyer),db:Session=Depends(get_db)):
    statement=select(Sale,Order).join(Order,Sale.order_id==Order.id).where(Order.member_id==user.id).order_by(Sale.id.desc())
    statement,window=history_window(request,db,statement)
    rows=db.execute(statement.options(selectinload(Order.lines))).all()
    return page(request,'member_sales.html',user=user,rows=rows,window=window)

def notification_json(db,user,offset=0):
    from .notifications import inbox, unread
    rows=inbox(db,user.id,20,offset)
    return dict(user_id=user.id,unread=unread(db,user.id),latest_id=db.scalar(select(func.max(Notification.id)).where(Notification.user_id==user.id)) or 0,
                items=[dict(id=n.id,title=n.title,message=n.message,link=n.link,kind=n.kind,created_at=wib(n.created_at),read=n.read_at is not None) for n in rows])

@app.get('/api/notifikasi')
def notification_feed(user:User=Depends(current),db:Session=Depends(get_db)):
    from fastapi.responses import JSONResponse
    return JSONResponse(notification_json(db,user),headers={'Cache-Control':'no-store'})

@app.get('/notifikasi')
def notification_history(request:Request,user:User=Depends(current),db:Session=Depends(get_db)):
    statement=select(Notification).where(Notification.user_id==user.id).order_by(Notification.id.desc())
    statement,window=history_window(request,db,statement)
    return page(request,'notifications.html',user=user,notifications=db.scalars(statement).all(),window=window)

@app.post('/notifikasi/{notification_id}/baca')
async def notification_read(notification_id:int,request:Request,user:User=Depends(current),db:Session=Depends(get_db)):
    form=await request.form();check_csrf(request,form)
    notification=db.scalar(select(Notification).where(Notification.id==notification_id,Notification.user_id==user.id).with_for_update())
    if notification is None:raise HTTPException(404,'Notifikasi tidak ditemukan.')
    if notification.read_at is None:notification.read_at=utcnow()
    db.commit()
    return {'ok':True}

@app.post('/notifikasi/baca-semua')
async def notifications_read_all(request:Request,user:User=Depends(current),db:Session=Depends(get_db)):
    form=await request.form();check_csrf(request,form)
    through=integer(form.get('through'),'Batas notifikasi',True)
    db.execute(update(Notification).where(Notification.user_id==user.id,Notification.id<=through,Notification.read_at.is_(None)).values(read_at=utcnow()))
    db.commit();return {'ok':True}

@app.get('/pesanan/{order_id}/bukti')
def member_proof_form(order_id:int,request:Request,user:User=Depends(buyer),db:Session=Depends(get_db)):
    order=db.scalar(select(Order).where(Order.id==order_id,Order.member_id==user.id))
    if order is None:raise HTTPException(404,'Pesanan tidak ditemukan.')
    if order.status!='Dikonfirmasi':raise HTTPException(409,'Bukti hanya dapat diunggah untuk pesanan Dikonfirmasi.')
    submission=db.scalar(select(PaymentSubmission).where(PaymentSubmission.order_id==order.id))
    return page(request,'member_proof.html',user=user,order=order,submission=submission)

@app.post('/pesanan/{order_id}/bukti')
async def member_proof_upload(order_id:int,request:Request,user:User=Depends(buyer),db:Session=Depends(get_db)):
    from .payment_proofs import validate_payment_proof,MAX_PROOF_SIZE
    from .notifications import admins
    form=await request.form();check_csrf(request,form)
    upload=form.get('payment_proof')
    if not upload or not hasattr(upload,'read'):raise RuleError('Pilih bukti pembayaran terlebih dahulu.')
    proof=validate_payment_proof(await upload.read(MAX_PROOF_SIZE+1))
    order=db.scalar(select(Order).where(Order.id==order_id,Order.member_id==user.id).with_for_update().execution_options(populate_existing=True))
    if order is None:raise HTTPException(404,'Pesanan tidak ditemukan.')
    sale=db.scalar(select(Sale).where(Sale.order_id==order.id))
    if order.status!='Dikonfirmasi' or sale is None or not sale.valid or sale.status_pembayaran=='Lunas':
        raise HTTPException(409,'Pesanan ini tidak menerima bukti pembayaran.')
    if db.scalar(select(PaymentSubmission.id).where(PaymentSubmission.order_id==order.id)):
        return go(f'/pesanan/{order.id}/bukti',request,'Bukti sudah dikirim dan menunggu pemeriksaan admin.')
    db.add(PaymentSubmission(order_id=order.id,member_id=user.id,proof=proof))
    admins(db,f'order:{order.id}:proof','proof','Bukti pembayaran baru',f'{order.kode}: anggota mengunggah bukti pembayaran.',f'/pesanan/{order.id}/selesaikan')
    db.commit()
    return go(f'/pesanan/{order.id}/bukti',request,'Bukti berhasil dikirim. Pembayaran menunggu pemeriksaan admin.')

@app.get('/pesanan/{order_id}/bukti/gambar')
def submitted_proof_image(order_id:int,user:User=Depends(current),db:Session=Depends(get_db)):
    statement=select(PaymentSubmission.proof).join(Order,Order.id==PaymentSubmission.order_id).where(Order.id==order_id)
    if user.role!='admin':statement=statement.where(Order.member_id==user.id)
    proof=db.scalar(statement)
    if not proof:raise HTTPException(404,'Bukti pembayaran tidak ditemukan.')
    return Response(proof,media_type='image/jpeg',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

@app.get('/pesanan/{order_id}/selesaikan')
def completion_page(order_id:int,request:Request,user:User=Depends(admin),db:Session=Depends(get_db)):
    order=db.get(Order,order_id)
    if order is None:raise HTTPException(404,'Pesanan tidak ditemukan.')
    if order.status!='Dikonfirmasi':return go('/pesanan',request,'Pesanan ini tidak menunggu penyelesaian.')
    sale=db.scalar(select(Sale).where(Sale.order_id==order.id))
    return page(request,'complete_order.html',user=user,order=order,amount=sale.jumlah_bayar if sale and sale.status_pembayaran=='Lunas' else '',method='Cash',submission=db.scalar(select(PaymentSubmission).where(PaymentSubmission.order_id==order.id)))

@app.post('/pesanan/{order_id}/status')
async def order_status(order_id:int,request:Request,user:User=Depends(admin),db:Session=Depends(get_db)):
    form=await request.form();check_csrf(request,form)
    target=str(form.get('status',''))
    if target=='Selesai':
        try:
            if form.get('metode')=='Cashless':
                from .payment_proofs import validate_payment_proof, MAX_PROOF_SIZE
                upload=form.get('payment_proof')
                if upload and hasattr(upload,'read') and upload.filename:
                    proof=validate_payment_proof(await upload.read(MAX_PROOF_SIZE+1))
                else:
                    proof=db.scalar(select(PaymentSubmission.proof).where(PaymentSubmission.order_id==order_id))
                    if not proof:raise RuleError('Unggah bukti pembayaran terlebih dahulu.')
                complete_cashless_order(db,order_id,user.id,proof,True)
            else:complete_cash_order(db,order_id,user.id,str(form.get('metode','')),form.get('jumlah_bayar'))
        except RuleError as exc:
            db.rollback()
            order=db.get(Order,order_id)
            if order is None:raise HTTPException(404,'Pesanan tidak ditemukan.')
            response=page(request,'complete_order.html',user=user,order=order,amount=str(form.get('jumlah_bayar','')),method=str(form.get('metode','Cash')),error=str(exc),submission=db.scalar(select(PaymentSubmission).where(PaymentSubmission.order_id==order_id)))
            response.status_code=400
            return response
    else:transition(db,order_id,target,user.id)
    db.commit()
    return go('/pesanan',request,'Status pesanan diperbarui.')

@app.get('/transaksi/{sale_id}/bukti')
def payment_proof_page(sale_id:int,user:User=Depends(admin),db:Session=Depends(get_db)):
    proof=db.scalar(select(Sale.payment_proof).where(Sale.id==sale_id))
    if not proof:raise HTTPException(404,'Bukti pembayaran tidak ditemukan.')
    return Response(proof,media_type='image/jpeg',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Disposition':'inline; filename="bukti-pembayaran.jpg"'})

@app.get('/transaksi')
def sales_page(request:Request,user:User=Depends(admin),db:Session=Depends(get_db)):
    rows=db.execute(select(Sale,Order).join(Order,Sale.order_id==Order.id).order_by(Sale.id.desc())).all()
    proof_ids=set(db.scalars(select(Sale.id).where(Sale.payment_proof.is_not(None))))
    return page(request,'sales.html',user=user,rows=rows,proof_ids=proof_ids)


@app.post('/transaksi/{sale_id}/bayar')
async def sale_payment(
    sale_id: int,
    request: Request,
    user: User = Depends(admin),
    db: Session = Depends(get_db)
):
    form = await request.form()
    check_csrf(request, form)

    raise HTTPException(410,'Pembayaran dicatat otomatis saat pesanan diselesaikan melalui menu Pesanan.')

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
