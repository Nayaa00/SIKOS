from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
from uuid import uuid4
import re
from sqlalchemy import select
from .models import Product, Order, OrderLine, Sale, StockMovement, utcnow

class RuleError(ValueError):
    pass

def integer(value, label, zero=False):
    try:
        num = Decimal(str(value).strip())
        if not num.is_finite() or num != num.to_integral_value():
            raise ValueError()
        num = int(num)
    except (ValueError, TypeError, InvalidOperation):
        raise RuleError(f'{label} harus angka bulat.')
    if num < (0 if zero else 1) or num > 1_000_000_000:
        raise RuleError(f'{label} harus antara {0 if zero else 1} dan 1.000.000.000.')
    return num

def text(value, label, maxlen=150):
    value = str(value or '').strip()
    if not value or len(value) > maxlen:
        raise RuleError(f'{label} wajib diisi, maksimal {maxlen} karakter.')
    return value

def code(value):
    value = text(value,'Kode produk',40).upper()
    if not re.fullmatch(r'[A-Z0-9_-]+',value):
        raise RuleError('Kode hanya huruf, angka, - atau _.')
    return value

def movement(db, product, delta, actor, reason, order_id=None):
    if product.stok + delta < 0 or product.stok + delta > 1_000_000_000:
        raise RuleError(f'Stok {product.nama} tidak cukup atau melebihi batas.')
    product.stok += delta
    db.add(StockMovement(product_id=product.id,actor_id=actor,delta=delta,after=product.stok,alasan=reason,order_id=order_id))

def create_order(db, member, cart, token):
    if not re.fullmatch('[a-f0-9]{32}',token):
        raise RuleError('Form pesanan tidak valid.')
    prior = db.scalar(select(Order).where(Order.member_id==member,Order.token==token))
    if prior:
        return prior
    if not cart or len(cart)>100:
        raise RuleError('Keranjang kosong atau terlalu banyak jenis barang.')
    order = Order(kode='PSN-'+uuid4().hex[:16].upper(),member_id=member,token=token,total=0,status='Menunggu konfirmasi')
    for product_id, value in sorted(cart.items(),key=lambda pair:int(pair[0])):
        qty=integer(value,'Jumlah')
        product=db.scalar(select(Product).where(Product.id==int(product_id)).with_for_update().execution_options(populate_existing=True))
        if product is None or not product.active or not product.category.active:
            raise RuleError('Salah satu produk tidak tersedia.')
        if qty > product.stok:
            raise RuleError(f'Stok {product.nama} tidak cukup. Perbarui keranjang.')
        if qty > 1_000_000:
            raise RuleError('Jumlah per barang maksimal 1.000.000 unit.')
        subtotal=product.harga*qty
        order.lines.append(OrderLine(product_id=product.id,kode=product.kode,nama=product.nama,harga=product.harga,qty=qty,subtotal=subtotal))
        order.total+=subtotal
    db.add(order)
    db.flush()
    return order


def transition(db, order_id, target, actor):
    order = db.scalar(
        select(Order)
        .where(Order.id == order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )

    if order is None:
        raise RuleError('Pesanan tidak ditemukan.')

    if target == order.status:
        return order

    valid = {
        'Menunggu konfirmasi': {'Dikonfirmasi', 'Dibatalkan'},
        'Dikonfirmasi': {'Selesai', 'Dibatalkan'},
        'Selesai': set(),
        'Dibatalkan': set()
    }

    if target not in valid.get(order.status, set()):
        raise RuleError('Perubahan status tersebut tidak diperbolehkan.')

    # Lock order before sale, shared with cash payment, to serialize cancellation.
    sale = None
    if target == 'Dibatalkan':
        sale = db.scalar(select(Sale).where(Sale.order_id == order.id)
                         .with_for_update().execution_options(populate_existing=True))

    # Proses perubahan stok
    if target == 'Dikonfirmasi' or (
        target == 'Dibatalkan' and order.status == 'Dikonfirmasi'
    ):
        for line in sorted(order.lines, key=lambda line: line.product_id):
            product = db.scalar(
                select(Product)
                .where(Product.id == line.product_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )

            if target == 'Dikonfirmasi':
                if not product.active or not product.category.active:
                    raise RuleError(f'{product.nama} sudah dinonaktifkan.')

                movement(
                    db, product, -line.qty, actor,
                    'Konfirmasi pesanan', order.id
                )
            else:
                movement(
                    db, product, line.qty, actor,
                    'Pembatalan pesanan', order.id
                )

    if target == 'Dikonfirmasi':
        order.confirmed_at = utcnow()
        db.add(
            Sale(
                order_id=order.id,
                total=order.total,
                created_at=order.confirmed_at,
                valid=True
            )
        )

    elif target == 'Dibatalkan':
        if sale:
            sale.valid = False

    elif target == 'Selesai':
        order.completed_at = utcnow()
        settle_completed_order(db,order)

    order.status = target
    db.flush()
    return order


def period(kind, selected):
    try:
        day=date.fromisoformat(selected)
        if day.year<1900 or day.year>9998:
            raise ValueError()
    except (ValueError,TypeError):
        raise RuleError('Tanggal laporan tidak valid.')
    if kind=='harian': start,end=day,day+timedelta(days=1)
    elif kind=='mingguan':
        start=day-timedelta(days=day.weekday());end=start+timedelta(days=7)
    elif kind=='bulanan':
        start=day.replace(day=1);end=date(day.year+1,1,1) if day.month==12 else date(day.year,day.month+1,1)
    elif kind=='tahunan': start,end=date(day.year,1,1),date(day.year+1,1,1)
    else: raise RuleError('Jenis periode tidak valid.')
    zone=ZoneInfo('Asia/Jakarta')
    return tuple(datetime.combine(d,time.min,zone).astimezone(timezone.utc).replace(tzinfo=None) for d in (start,end))


def record_payment(db, sale_id, amount):
    amount = integer(amount, 'Jumlah uang diterima')
    order_id = db.scalar(select(Sale.order_id).where(Sale.id == sale_id))
    if order_id is None:
        raise RuleError('Transaksi tidak ditemukan.')
    order = db.scalar(select(Order).where(Order.id == order_id)
                      .with_for_update().execution_options(populate_existing=True))
    if order is None or order.status not in ('Dikonfirmasi', 'Selesai'):
        raise RuleError('Pesanan tidak dapat dibayar.')
    sale = db.scalar(
        select(Sale)
        .where(Sale.id == sale_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )

    if sale is None:
        raise RuleError('Transaksi tidak ditemukan.')

    if not sale.valid:
        raise RuleError('Transaksi sudah tidak valid.')

    if sale.status_pembayaran == 'Lunas':
        raise RuleError('Pembayaran sudah lunas.')

    if amount < sale.total:
        raise RuleError('Uang yang diterima kurang dari total pembayaran.')

    sale.metode_pembayaran = 'Tunai'
    sale.status_pembayaran = 'Lunas'
    sale.jumlah_bayar = amount
    sale.kembalian = amount - sale.total
    sale.paid_at = utcnow()

    db.flush()
    return sale


def cancel_member_order(db, order_id, member_id):
    # Ownership and status are checked under the same lock used by admin confirmation.
    order=db.scalar(select(Order).where(Order.id==order_id,Order.member_id==member_id)
                    .with_for_update().execution_options(populate_existing=True))
    if order is None:
        from fastapi import HTTPException
        raise HTTPException(404,'Pesanan tidak ditemukan.')
    if order.status=='Dibatalkan':return order
    if order.status!='Menunggu konfirmasi':
        raise RuleError('Pesanan sudah diproses admin. Hanya pesanan Menunggu konfirmasi yang dapat Anda batalkan.')
    return transition(db,order_id,'Dibatalkan',member_id)


def settle_completed_order(db,order):
    sale=db.scalar(select(Sale).where(Sale.order_id==order.id)
                   .with_for_update().execution_options(populate_existing=True))
    if sale is None or not sale.valid:
        raise RuleError('Transaksi valid untuk pesanan ini tidak ditemukan.')
    if sale.status_pembayaran=='Lunas':return sale
    if sale.jumlah_bayar or sale.kembalian or sale.paid_at:
        raise RuleError('Catatan pembayaran lama perlu diperiksa sebelum menyelesaikan pesanan.')
    sale.metode_pembayaran='Tunai'
    sale.status_pembayaran='Lunas'
    sale.jumlah_bayar=sale.total
    sale.kembalian=0
    sale.paid_at=order.completed_at
    return sale

def sync_completed_payments(db):
    ids=db.scalars(select(Order.id).join(Sale,Sale.order_id==Order.id).where(
        Order.status=='Selesai',Order.completed_at.is_not(None),Sale.valid.is_(True),
        Sale.status_pembayaran=='Belum dibayar',Sale.jumlah_bayar==0,
        Sale.kembalian==0,Sale.paid_at.is_(None)).order_by(Order.id)).all()
    count=0
    for oid in ids:
        order=db.scalar(select(Order).where(Order.id==oid).with_for_update().execution_options(populate_existing=True))
        if order.status=='Selesai':settle_completed_order(db,order);count+=1
    db.flush()
    return count
