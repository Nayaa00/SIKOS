from decimal import Decimal, InvalidOperation, ROUND_CEILING
from .services import RuleError,integer
DEFAULT_MARKUPS={'Bahan pokok':10,'Perawatan':20,'Makanan ringan':25,'Minuman':15,'Kesehatan':10}

def markup(value):
    try:
        number=Decimal(str(value))
        if not number.is_finite() or number<0 or number>100 or number!=number.quantize(Decimal('0.01')):raise ValueError()
        return number
    except (ValueError,InvalidOperation):raise RuleError('Markup harus 0–100 persen, maksimal 2 angka desimal.')

def selling_price(hpp,percentage):
    cost=integer(hpp,'Harga beli / HPP')
    price=int((Decimal(cost)*(100+markup(percentage))/Decimal(10000)).to_integral_value(rounding=ROUND_CEILING))*100
    if price>1_000_000_000:raise RuleError('Harga jual hasil perhitungan melebihi Rp1.000.000.000.')
    return price
