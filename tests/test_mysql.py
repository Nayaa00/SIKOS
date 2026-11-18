"""Opt-in real database tests. Never fall back to SQLite or production URL."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Category, Order, OrderLine, Product, Sale, StockMovement, User, Notification, PaymentSubmission
from app.services import RuleError, create_order, movement, transition
from app.security import hash_password


@pytest.fixture
def mysql_store():
    load_dotenv()
    raw = os.getenv('SIKOS_TEST_DATABASE_URL')
    if not raw:
        pytest.skip('SIKOS_TEST_DATABASE_URL belum tersedia; MySQL belum diuji.')
    url = make_url(raw)
    if url.get_backend_name() != 'mysql' or not (url.database or '').endswith('_test'):
        pytest.fail('Tes hanya menerima URL MySQL menuju database berakhiran _test.')
    engine = create_engine(url, pool_pre_ping=True)
    tag = 'T' + uuid4().hex[:16].upper()
    factory = sessionmaker(engine, expire_on_commit=False)
    with engine.connect() as connection:
        version = connection.scalar(text('SELECT VERSION()'))
        print('Database nyata:', version)
        is_mariadb = 'mariadb' in version.lower()
        if is_mariadb and os.getenv('SIKOS_ALLOW_MARIADB') != '1':
            pytest.skip('Server MariaDB, bukan MySQL. Gunakan SIKOS_ALLOW_MARIADB=1 untuk tes MariaDB terpisah.')
        if not is_mariadb and int(version.split('.')[0]) < 8:
            pytest.fail('Diperlukan MySQL 8 atau lebih baru.')
    Base.metadata.create_all(engine)
    from app.migrations import migrate_product_labels
    migrate_product_labels(engine)
    from app.code_migration import migrate_product_codes
    migrate_product_codes(engine)
    from app.migrations import migrate_sale_payments
    migrate_sale_payments(engine)
    with engine.connect() as connection:
        engines = connection.execute(text(
            'SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES '
            'WHERE TABLE_SCHEMA = DATABASE()'
        )).all()
        assert all(kind == 'InnoDB' for name, kind in engines if name in Base.metadata.tables)
    with factory() as db:
        admin = User(nomor=tag+'A', nama='Admin tes', email=tag+'a@example.invalid',
                     password_hash=hash_password(uuid4().hex), role='admin')
        member = User(nomor=tag+'M', nama='Anggota tes', email=tag+'m@example.invalid',
                      password_hash=hash_password(uuid4().hex), role='anggota')
        cat = Category(nama=tag)
        db.add_all([admin, member, cat]); db.flush()
        p = Product(kode=tag+'1', nama='Stok terakhir', category_id=cat.id,
                    harga=10000, stok=1, satuan='pak')
        q = Product(kode=tag+'2', nama='Produk kedua', category_id=cat.id,
                    harga=20000, stok=10, satuan='pak')
        db.add_all([p, q]); db.commit()
        ids = admin.id, member.id, p.id, q.id
        category_id = cat.id
    try:
        yield factory, ids
    finally:
        with factory() as db:
            orders = select(Order.id).where(Order.member_id == ids[1])
            db.execute(delete(Notification).where(Notification.user_id.in_(ids[:2])))
            db.execute(delete(PaymentSubmission).where(PaymentSubmission.member_id.in_(ids[:2])))
            db.execute(delete(StockMovement).where(StockMovement.product_id.in_(ids[2:])))
            db.execute(delete(Sale).where(Sale.order_id.in_(orders)))
            db.execute(delete(OrderLine).where(OrderLine.order_id.in_(orders)))
            db.execute(delete(Order).where(Order.member_id == ids[1]))
            db.execute(delete(Product).where(Product.id.in_(ids[2:])))
            db.execute(delete(Category).where(Category.id == category_id))
            db.execute(delete(User).where(User.id.in_(ids[:2])))
            db.commit()
        engine.dispose()


def parallel_transitions(factory, order_ids, target, actor):
    barrier = Barrier(2)
    def worker(order_id):
        with factory() as db:
            # Exercise the identity-map case as well as two independent connections.
            preloaded = db.get(Order, order_id)
            assert preloaded is not None
            db.commit()
            barrier.wait(timeout=10)
            try:
                transition(db, order_id, target, actor)
                db.commit()
                return 'ok'
            except RuleError:
                db.rollback()
                return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as executor:
        return list(executor.map(worker, order_ids))


def test_mysql_last_unit_concurrent_confirmation_and_cancellation(mysql_store):
    factory, (admin, member, product, _) = mysql_store
    with factory() as db:
        first = create_order(db, member, {str(product): 1}, uuid4().hex)
        second = create_order(db, member, {str(product): 1}, uuid4().hex)
        db.commit()
        order_ids = first.id, second.id
        assert db.get(Product, product).stok == 1
    assert sorted(parallel_transitions(factory, order_ids, 'Dikonfirmasi', admin)) == ['ok', 'rejected']
    with factory() as db:
        winner = db.scalar(select(Order).where(Order.id.in_(order_ids), Order.status == 'Dikonfirmasi'))
        assert winner is not None
        winner_id = winner.id
        assert db.get(Product, product).stok == 0
        assert db.scalar(select(func.count()).select_from(Sale).where(Sale.order_id.in_(order_ids))) == 1
        assert db.scalar(select(func.count()).select_from(StockMovement).where(StockMovement.product_id == product)) == 1
    assert parallel_transitions(factory, (winner_id, winner_id), 'Dikonfirmasi', admin) == ['ok', 'ok']
    assert parallel_transitions(factory, (winner_id, winner_id), 'Dibatalkan', admin) == ['ok', 'ok']
    with factory() as db:
        assert db.get(Product, product).stok == 1
        assert not db.scalar(select(Sale).where(Sale.order_id == winner_id)).valid
        assert db.scalar(select(func.count()).select_from(StockMovement).where(StockMovement.product_id == product)) == 2


def test_mysql_atomic_confirmation_snapshot_and_void(mysql_store):
    from app.analytics import analyze
    from app.models import utcnow
    from zoneinfo import ZoneInfo
    from datetime import timezone
    factory, (admin, member, p, q) = mysql_store
    with factory() as db:
        order = create_order(db, member, {str(p): 1, str(q): 2}, uuid4().hex)
        db.commit()
        oid = order.id
        movement(db, db.get(Product, q), -10, admin, 'Habiskan stok untuk tes rollback')
        db.commit()
        with pytest.raises(RuleError):
            transition(db, oid, 'Dikonfirmasi', admin)
        db.rollback()
        assert db.get(Product, p).stok == 1
        assert db.get(Order, oid).status == 'Menunggu konfirmasi'
        assert db.scalar(select(Sale).where(Sale.order_id == oid)) is None
        movement(db, db.get(Product, q), 10, admin, 'Pulihkan fixture')
        db.get(Product, p).harga = 90000
        db.commit()
        transition(db, oid, 'Dikonfirmasi', admin)
        db.commit()
        assert db.get(Order, oid).total == 50000
        assert db.scalar(select(Sale).where(Sale.order_id == oid)).total == 50000
        day = utcnow().replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Asia/Jakarta')).date().isoformat()
        for kind in ('harian', 'mingguan', 'bulanan', 'tahunan'):
            assert any(row['pesanan'] == order.kode for row in analyze(db, kind, day)['rows'])
        transition(db, oid, 'Dibatalkan', admin)
        db.commit()
        assert db.get(Product, p).stok == 1
        assert db.get(Product, q).stok == 10
        for kind in ('harian', 'mingguan', 'bulanan', 'tahunan'):
            assert not any(row['pesanan'] == order.kode for row in analyze(db, kind, day)['rows'])


def test_mysql_parallel_product_code_allocation(mysql_store):
    from app.product_codes import next_product_code,choose_prefix
    factory,(_,_,pid,_)=mysql_store
    with factory() as db:
        category=db.get(Product,pid).category
        category.code_prefix=choose_prefix(category.nama,set(db.scalars(select(Category.code_prefix).where(Category.code_prefix.is_not(None)))))
        db.commit();cid=category.id
    barrier=Barrier(2)
    def worker(_):
        with factory() as db:
            barrier.wait(timeout=10)
            value=next_product_code(db,cid)
            product=Product(kode=value,nama='Produk paralel',category_id=cid,harga=1000,stok=0,satuan='pak')
            db.add(product);db.commit()
            return product.id,value
    with ThreadPoolExecutor(max_workers=2) as pool:
        created=list(pool.map(worker,range(2)))
    try:
        assert len({value for _,value in created})==2
        assert sorted(int(value[3:]) for _,value in created)==[1,2]
    finally:
        with factory() as db:
            db.execute(delete(Product).where(Product.id.in_([pid for pid,_ in created])))
            db.commit()

def test_mysql_member_cancel_races_admin_confirmation(mysql_store):
    from app.services import cancel_member_order
    factory,ids=mysql_store
    admin,member,pid,_=ids
    with factory() as db:
        order=create_order(db,member,{str(pid):1},uuid4().hex);db.commit();oid=order.id
    barrier=Barrier(2)
    def worker(member_cancel):
        with factory() as db:
            db.get(Order,oid);db.commit();barrier.wait(timeout=10)
            try:
                if member_cancel:cancel_member_order(db,oid,member)
                else:transition(db,oid,'Dikonfirmasi',admin)
                db.commit();return 'ok'
            except RuleError:
                db.rollback();return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures=[executor.submit(worker,value) for value in (True,False)]
        results=[future.result(timeout=30) for future in futures]
    assert sorted(results)==['ok','rejected']
    with factory() as db:
        order=db.get(Order,oid);product=db.get(Product,pid)
        count=db.scalar(select(func.count()).select_from(Sale).where(Sale.order_id==oid))
        if order.status=='Dibatalkan':assert product.stok==1 and count==0
        else:assert order.status=='Dikonfirmasi' and product.stok==0 and count==1

def test_mysql_payment_races_cancellation(mysql_store):
    from app.services import record_payment
    factory,ids=mysql_store
    admin,member,pid,_=ids
    with factory() as db:
        order=create_order(db,member,{str(pid):1},uuid4().hex)
        transition(db,order.id,'Dikonfirmasi',admin);db.commit()
        oid=order.id;sid=db.scalar(select(Sale.id).where(Sale.order_id==oid))
    barrier=Barrier(2)
    def worker(payment):
        with factory() as db:
            db.get(Order,oid);db.commit();barrier.wait(timeout=10)
            try:
                if payment:record_payment(db,sid,10000)
                else:transition(db,oid,'Dibatalkan',admin)
                db.commit();return 'ok'
            except RuleError:
                db.rollback();return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures=[executor.submit(worker,value) for value in (True,False)]
        results=[future.result(timeout=30) for future in futures]
    assert results[1]=='ok'
    with factory() as db:
        assert db.get(Order,oid).status=='Dibatalkan'
        assert db.get(Product,pid).stok==1
        sale=db.get(Sale,sid);assert not sale.valid
        assert sale.jumlah_bayar==(10000 if results[0]=='ok' else 0)
        assert db.scalar(select(func.count()).select_from(StockMovement).where(StockMovement.order_id==oid))==2


def test_mysql_completion_auto_payment_parallel_once(mysql_store):
    factory,(admin,member,pid,_) = mysql_store
    with factory() as db:
        order=create_order(db,member,{str(pid):1},uuid4().hex)
        transition(db,order.id,'Dikonfirmasi',admin);db.commit();oid=order.id
    results=parallel_transitions(factory,[oid,oid],'Selesai',admin)
    with factory() as db:
        order=db.get(Order,oid);sale=db.scalar(select(Sale).where(Sale.order_id==oid))
        assert order.status=='Selesai' and sale.status_pembayaran=='Lunas'
        assert sale.jumlah_bayar==10000 and sale.kembalian==0
        assert sale.paid_at==order.completed_at and db.get(Product,pid).stok==0
        assert db.scalar(select(func.count()).select_from(Sale).where(Sale.order_id==oid))==1
        assert db.scalar(select(func.count()).select_from(StockMovement).where(StockMovement.order_id==oid))==1


def test_mysql_cash_completion_parallel_keeps_actual_change(mysql_store):
    from app.services import complete_cash_order
    factory,(admin,member,pid,_) = mysql_store
    with factory() as db:
        order=create_order(db,member,{str(pid):1},uuid4().hex)
        transition(db,order.id,'Dikonfirmasi',admin);db.commit();oid=order.id
    barrier=Barrier(2)
    def worker():
        with factory() as db:
            barrier.wait(timeout=10)
            result=complete_cash_order(db,oid,admin,'Cash',20000)
            db.commit();return result.id
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures=[executor.submit(worker) for _ in range(2)]
        assert [f.result(timeout=30) for f in futures]==[oid,oid]
    with factory() as db:
        sale=db.scalar(select(Sale).where(Sale.order_id==oid))
        assert sale.jumlah_bayar==20000 and sale.kembalian==10000
        assert db.get(Order,oid).status=='Selesai' and db.get(Product,pid).stok==0
        assert db.scalar(select(func.count()).select_from(Sale).where(Sale.order_id==oid))==1


def test_mysql_cashless_evidence_persisted_atomically(mysql_store):
    from io import BytesIO
    from PIL import Image
    from app.payment_proofs import validate_payment_proof
    from app.services import complete_cashless_order
    factory,(admin,member,pid,_) = mysql_store
    image=BytesIO();Image.new('RGB',(30,30),'white').save(image,'PNG')
    proof=validate_payment_proof(image.getvalue())
    with factory() as db:
        order=create_order(db,member,{str(pid):1},uuid4().hex)
        transition(db,order.id,'Dikonfirmasi',admin);db.commit();oid=order.id
        complete_cashless_order(db,oid,admin,proof,True);db.commit()
    with factory() as db:
        sale=db.scalar(select(Sale).where(Sale.order_id==oid))
        assert sale.payment_proof==proof and sale.payment_verified_by==admin
        assert sale.metode_pembayaran=='Cashless' and sale.jumlah_bayar==10000 and sale.kembalian==0
        assert db.get(Order,oid).status=='Selesai' and db.get(Product,pid).stok==0
        complete_cashless_order(db,oid,admin,proof,True);db.commit()
        assert db.scalar(select(func.count()).select_from(Sale).where(Sale.order_id==oid))==1


def test_mysql_notification_confirmation_once_and_transaction_rollback(mysql_store):
    factory,ids=mysql_store
    with factory() as db:
        order=create_order(db,ids[1],{str(ids[2]):1},uuid4().hex);db.commit();oid=order.id
    results=parallel_transitions(factory,[oid,oid],'Dikonfirmasi',ids[0])
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id==ids[1],Notification.event_key==f'order:{oid}:Dikonfirmasi'))==1
        assert db.scalar(select(func.count()).select_from(Notification).where(Notification.event_key==f'order:{oid}:created'))==2
        transition(db,oid,'Dibatalkan',ids[0]);db.rollback()
    with factory() as db:
        assert db.get(Order,oid).status=='Dikonfirmasi'
        assert db.scalar(select(func.count()).select_from(Notification).where(Notification.event_key==f'order:{oid}:Dibatalkan'))==0
