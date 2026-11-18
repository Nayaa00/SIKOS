from datetime import datetime, timezone
from sqlalchemy import String, Integer, BigInteger, ForeignKey, Boolean, DateTime, Text, CheckConstraint, UniqueConstraint, LargeBinary, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base
from sqlalchemy.dialects.mysql import MEDIUMBLOB

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    nomor: Mapped[str] = mapped_column(String(40), unique=True)
    nama: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(190), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    telepon: Mapped[str] = mapped_column(String(30), default='')
    alamat: Mapped[str] = mapped_column(Text, default='')
    role: Mapped[str] = mapped_column(String(15), default='anggota')
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class Category(Base):
    __tablename__ = 'categories'
    id: Mapped[int] = mapped_column(primary_key=True)
    nama: Mapped[str] = mapped_column(String(100), unique=True)
    code_prefix: Mapped[str | None] = mapped_column(String(3), unique=True, nullable=True)
    code_counter: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class Product(Base):
    __tablename__ = 'products'
    __table_args__ = (CheckConstraint('stok >= 0'), CheckConstraint('harga > 0'))
    id: Mapped[int] = mapped_column(primary_key=True)
    kode: Mapped[str] = mapped_column(String(40), unique=True)
    source_code: Mapped[str | None] = mapped_column(String(40), unique=True, nullable=True)
    nama: Mapped[str] = mapped_column(String(150))
    label: Mapped[str] = mapped_column(String(100), default='', server_default='')
    category_id: Mapped[int] = mapped_column(ForeignKey('categories.id'))
    category: Mapped[Category] = relationship()
    harga: Mapped[int] = mapped_column(BigInteger)
    stok: Mapped[int] = mapped_column(Integer, default=0)
    satuan: Mapped[str] = mapped_column(String(30))
    deskripsi: Mapped[str] = mapped_column(Text, default='')
    gambar: Mapped[str] = mapped_column(String(500), default='')
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class Order(Base):
    __tablename__ = 'orders'
    __table_args__ = (
        UniqueConstraint('member_id','token'),
        CheckConstraint("status IN ('Menunggu konfirmasi', 'Dikonfirmasi', 'Selesai', 'Dibatalkan')", name='ck_order_status'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    kode: Mapped[str] = mapped_column(String(40), unique=True)
    member_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    member: Mapped[User] = relationship()
    token: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default='Menunggu konfirmasi')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total: Mapped[int] = mapped_column(BigInteger)
    lines: Mapped[list['OrderLine']] = relationship(back_populates='order', cascade='all, delete-orphan', order_by='OrderLine.id')

class OrderLine(Base):
    __tablename__ = 'order_lines'
    __table_args__ = (CheckConstraint('qty > 0'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'))
    order: Mapped[Order] = relationship(back_populates='lines')
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    kode: Mapped[str] = mapped_column(String(40))
    nama: Mapped[str] = mapped_column(String(150))
    harga: Mapped[int] = mapped_column(BigInteger)
    qty: Mapped[int] = mapped_column(Integer)
    subtotal: Mapped[int] = mapped_column(BigInteger)

class Sale(Base):
    __tablename__ = 'sales'

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    valid: Mapped[bool] = mapped_column(Boolean, default=True)
    total: Mapped[int] = mapped_column(BigInteger)

    metode_pembayaran: Mapped[str] = mapped_column(
        String(20), default='Tunai', server_default='Tunai'
    )
    status_pembayaran: Mapped[str] = mapped_column(
        String(20), default='Belum dibayar', server_default='Belum dibayar'
    )
    jumlah_bayar: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0')
    kembalian: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0')
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    payment_proof: Mapped[bytes | None] = mapped_column(LargeBinary().with_variant(MEDIUMBLOB(), 'mysql'),nullable=True,deferred=True)
    payment_verified_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'),nullable=True)


class StockMovement(Base):
    __tablename__ = 'stock_movements'
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    product: Mapped[Product] = relationship()
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    actor: Mapped[User] = relationship()
    order_id: Mapped[int | None] = mapped_column(ForeignKey('orders.id'), nullable=True)
    delta: Mapped[int] = mapped_column(Integer)
    after: Mapped[int] = mapped_column(Integer)
    alasan: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Notification(Base):
    __tablename__ = 'notifications'
    __table_args__ = (UniqueConstraint('user_id','event_key',name='uq_notification_event'),Index('ix_notification_inbox','user_id','read_at','id'))
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    event_key: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(150))
    message: Mapped[str] = mapped_column(String(500))
    link: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime,default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime,nullable=True)

class PaymentSubmission(Base):
    __tablename__ = 'payment_submissions'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'),unique=True)
    member_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    proof: Mapped[bytes] = mapped_column(LargeBinary().with_variant(MEDIUMBLOB(),'mysql'),deferred=True)
    created_at: Mapped[datetime] = mapped_column(DateTime,default=utcnow)

# Explicit transactional engine for every newly created MySQL table.
for _table in Base.metadata.tables.values():
    _table.dialect_options['mysql']['engine'] = 'InnoDB'
