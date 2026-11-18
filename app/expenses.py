from datetime import date
import re
from sqlalchemy import select,func
from .models import OperatingExpense,Product,Category,utcnow
from .services import RuleError,integer,text
CATEGORIES=('Listrik dan air','Transportasi','Sewa','Gaji','Perlengkapan','Lainnya')

def create_expense(db,actor,token,tanggal,category,description,amount):
    if not re.fullmatch('[a-f0-9]{32}',str(token)):raise RuleError('Token formulir tidak valid. Muat ulang halaman.')
    prior=db.scalar(select(OperatingExpense).where(OperatingExpense.token==token))
    if prior:return prior
    try:
        day=date.fromisoformat(str(tanggal))
        if not 1900<=day.year<=9998:raise ValueError()
    except ValueError:raise RuleError('Tanggal biaya tidak valid.')
    if category not in CATEGORIES:raise RuleError('Pilih kategori biaya yang tersedia.')
    expense=OperatingExpense(token=token,tanggal=day,category=category,description=text(description,'Keterangan',200),amount=integer(amount,'Nominal biaya'),created_by=actor)
    db.add(expense);db.flush();return expense

def void_expense(db,expense_id,actor):
    expense=db.scalar(select(OperatingExpense).where(OperatingExpense.id==expense_id).with_for_update().execution_options(populate_existing=True))
    if expense is None:raise RuleError('Catatan biaya tidak ditemukan.')
    if expense.valid:expense.valid=False;expense.voided_by=actor;expense.voided_at=utcnow()
    return expense

def initialize_product_costs(db):
    # Infer an initial cost from existing selling price and markup; never invent invoices.
    # Lock categories before products, matching product save and category repricing.
    from decimal import Decimal,ROUND_FLOOR
    count=0
    for category in db.scalars(select(Category).order_by(Category.id).with_for_update()):
        for product in db.scalars(select(Product).where(Product.category_id==category.id,Product.hpp.is_(None)).order_by(Product.id).with_for_update().execution_options(populate_existing=True)):
            product.hpp=max(1,int((Decimal(product.harga)*100/(100+category.markup_percent)).to_integral_value(rounding=ROUND_FLOOR)))
            product.hpp_estimated=True;count+=1
    return count


def initialize_history_costs(db):
    from decimal import Decimal,ROUND_FLOOR
    from .models import Order,OrderLine,Sale
    ids=db.scalars(select(Order.id).join(Sale,Sale.order_id==Order.id).where(Sale.valid.is_(True),Order.status.in_(['Dikonfirmasi','Selesai'])).order_by(Order.id)).all()
    count=0
    for oid in ids:
        order=db.scalar(select(Order).where(Order.id==oid).with_for_update().execution_options(populate_existing=True))
        if order.status not in ('Dikonfirmasi','Selesai'):continue
        for line in db.scalars(select(OrderLine).where(OrderLine.order_id==oid,OrderLine.hpp.is_(None)).order_by(OrderLine.id).with_for_update().execution_options(populate_existing=True)):
            percentage=db.scalar(select(Category.markup_percent).join(Product,Product.category_id==Category.id).where(Product.id==line.product_id))
            if percentage is None:continue
            line.hpp=max(1,int((Decimal(line.harga)*100/(100+percentage)).to_integral_value(rounding=ROUND_FLOOR)))
            line.hpp_estimated=True;count+=1
    return count


def plan_calculation(budget,target,percentage):
    from decimal import Decimal,ROUND_CEILING,ROUND_FLOOR
    budget=integer(budget,'Rencana biaya bulanan',True)
    target=integer(target,'Target omzet bulanan')
    percent=Decimal(str(percentage)) if percentage is not None else None
    contribution=int((Decimal(target)*percent/(100+percent)).to_integral_value(rounding=ROUND_FLOOR)) if percent is not None and percent>0 else 0
    bep=int((Decimal(budget)*(100+percent)/percent).to_integral_value(rounding=ROUND_CEILING)) if percent is not None and percent>0 else (0 if budget==0 else None)
    required=(Decimal(budget)*100/(target-budget)).quantize(Decimal('0.01'),rounding=ROUND_CEILING) if target>budget else None
    return dict(budget=budget,target=target,lowest_markup=percent,projected_net=contribution-budget,bep=bep,required_markup=required,covered=contribution>=budget)


def monthly_plan(db):
    from .models import MonthlyPlan
    plan=db.get(MonthlyPlan,1)
    lowest=db.scalar(select(func.min(Category.markup_percent)).where(Category.active.is_(True)))
    result=plan_calculation(plan.budget if plan else 1500000,plan.target_revenue if plan else 20000000,lowest)
    result['is_default']=plan is None
    return result
