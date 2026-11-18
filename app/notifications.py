"""Transactional inbox: notifications commit/rollback with their business event."""
from sqlalchemy import select, func
from .models import Notification, User, Order

def send(db,user_id,key,kind,title,message,link):
    if not db.scalar(select(Notification.id).where(Notification.user_id==user_id,Notification.event_key==key)):
        db.add(Notification(user_id=user_id,event_key=key,kind=kind,title=title,message=message[:500],link=link))

def admins(db,key,kind,title,message,link):
    for uid in db.scalars(select(User.id).where(User.role=='admin',User.active.is_(True)).order_by(User.id)):
        send(db,uid,key,kind,title,message,link)

def order_created(db,order):
    key=f'order:{order.id}:created'
    admins(db,key,'order','Pesanan baru',f'{order.kode} menunggu konfirmasi.','/pesanan?status=Menunggu+konfirmasi')
    send(db,order.member_id,key,'order','Pesanan berhasil dibuat',f'{order.kode} menunggu konfirmasi admin.','/pesanan')

def order_changed(db,order):
    key=f'order:{order.id}:{order.status}'
    titles={'Dikonfirmasi':'Pesanan dikonfirmasi','Selesai':'Pesanan selesai','Dibatalkan':'Pesanan dibatalkan'}
    send(db,order.member_id,key,'order',titles[order.status],f'{order.kode}: {order.status}.','/pesanan')
    if order.status=='Dibatalkan':admins(db,key,'canceled','Pesanan dibatalkan',f'{order.kode} telah dibatalkan.','/pesanan?status=Dibatalkan')

def payment_received(db,sale):
    order=db.get(Order,sale.order_id);key=f'order:{order.id}:paid'
    message=f'Pembayaran {order.kode} telah dicatat lunas.'
    admins(db,key,'payment','Pembayaran berhasil',message,'/transaksi')
    send(db,order.member_id,key,'payment','Pembayaran berhasil',message,'/transaksi-saya')

def stock_changed(db,product,before,movement):
    empty=before>0 and product.stok==0
    low=before>5 and 0<product.stok<=5
    initial=before==0 and 0<=product.stok<=5 and movement.alasan.startswith('Stok awal')
    if product.active and (empty or low or initial):
        title='Stok habis' if product.stok==0 else 'Stok menipis'
        admins(db,f'stock:{movement.id}','stock',title,f'{product.nama}: tersisa {product.stok} {product.satuan}.','/stok')

def inbox(db,user_id,limit=5,offset=0):
    return db.scalars(select(Notification).where(Notification.user_id==user_id).order_by(Notification.id.desc()).limit(limit).offset(offset)).all()

def unread(db,user_id):
    return db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id==user_id,Notification.read_at.is_(None))) or 0
