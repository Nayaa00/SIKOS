import pandas as pd
from sqlalchemy import select
from .models import Order, OrderLine, Sale
from .services import period

def analyze(db, kind, selected):
    start,end=period(kind,selected)
    records=db.execute(select(Sale,Order,OrderLine).join(Order,Sale.order_id==Order.id).join(OrderLine,OrderLine.order_id==Order.id).where(Sale.valid.is_(True),Sale.created_at>=start,Sale.created_at<end).order_by(Sale.created_at,OrderLine.id)).all()
    rows=[dict(pesanan=o.kode,anggota=o.member.nama,tanggal=s.created_at,kode=line.kode,produk=line.nama,jumlah=line.qty,harga=line.harga,subtotal=line.subtotal) for s,o,line in records]
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
    return dict(rows=rows,best=best,trend=trend,total=int(frame['subtotal'].sum()) if len(frame) else 0,
                units=int(frame['jumlah'].sum()) if len(frame) else 0,
                transactions=int(frame['pesanan'].nunique()),kind=kind,selected=selected,start=start,end=end)
