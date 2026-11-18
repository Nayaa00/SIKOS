import pandas as pd
from datetime import timedelta
from sqlalchemy import select,func
from .models import Order, OrderLine, Sale, OperatingExpense
from .services import period

def analyze(db, kind, selected):
    start,end=period(kind,selected)
    records=db.execute(select(Sale,Order,OrderLine).join(Order,Sale.order_id==Order.id).join(OrderLine,OrderLine.order_id==Order.id).where(Sale.valid.is_(True),Sale.created_at>=start,Sale.created_at<end).order_by(Sale.created_at,OrderLine.id)).all()
    rows=[dict(pesanan=o.kode,anggota=o.member.nama,tanggal=s.created_at,kode=line.kode,produk=line.nama,jumlah=line.qty,harga=line.harga,subtotal=line.subtotal,hpp=line.hpp,hpp_estimasi=line.hpp_estimated,total_hpp=line.hpp*line.qty if line.hpp is not None else None,laba_kotor=line.subtotal-line.hpp*line.qty if line.hpp is not None else None) for s,o,line in records]
    missing_cost_units=sum(row['jumlah'] for row in rows if row['hpp'] is None)
    known_cost=sum(row['total_hpp'] for row in rows if row['hpp'] is not None)
    known_profit=sum(row['laba_kotor'] for row in rows if row['hpp'] is not None)
    cost_complete=missing_cost_units==0
    estimated_units=sum(row['jumlah'] for row in rows if row['hpp'] is not None and row['hpp_estimasi'])
    expenses=db.scalars(select(OperatingExpense).where(OperatingExpense.valid.is_(True),OperatingExpense.tanggal>=(start+timedelta(hours=7)).date(),OperatingExpense.tanggal<(end+timedelta(hours=7)).date()).order_by(OperatingExpense.tanggal,OperatingExpense.id)).all()
    expense_rows=[dict(tanggal=e.tanggal.isoformat(),kategori=e.category,keterangan=e.description,nominal=e.amount) for e in expenses]
    expense_total=sum(e.amount for e in expenses)
    frame=pd.DataFrame(rows,columns=['pesanan','anggota','tanggal','kode','produk','jumlah','harga','subtotal'])
    best=[];trend=[]
    if not frame.empty:
        grouped=frame.groupby('kode',as_index=False).agg(produk=('produk','last'),jumlah=('jumlah','sum'),subtotal=('subtotal','sum'))
        best=grouped.sort_values(['jumlah','kode'],ascending=[False,True]).to_dict('records')
        frame['tanggal']=pd.to_datetime(frame['tanggal'],utc=True).dt.tz_convert('Asia/Jakarta')
        daily=frame.assign(hari=frame['tanggal'].dt.strftime('%Y-%m-%d')).groupby('hari',as_index=False)['subtotal'].sum()
        trend=daily.to_dict('records')
        for row in rows:
            row['tanggal']=pd.Timestamp(row['tanggal'],tz='UTC').tz_convert('Asia/Jakarta').strftime('%d-%m-%Y %H:%M')
    return dict(expense_rows=expense_rows,expense_total=expense_total,net_profit=known_profit-expense_total if cost_complete else None,estimated_cost_units=estimated_units,
                cost_complete=cost_complete,missing_cost_units=missing_cost_units,known_cost=known_cost,known_profit=known_profit,
                total_hpp=known_cost if cost_complete else None,gross_profit=known_profit if cost_complete else None,
                rows=rows,best=best,trend=trend,total=int(frame['subtotal'].sum()) if len(frame) else 0,
                units=int(frame['jumlah'].sum()) if len(frame) else 0,
                transactions=int(frame['pesanan'].nunique()),kind=kind,selected=selected,start=start,end=end)
