"""Category-specific, transactional product numbering."""
import re
import unicodedata
from sqlalchemy import select, or_
from .models import Category, Product
from .services import RuleError, text

STANDARD_PREFIXES = {'Bahan pokok':'BPK','Perawatan':'PRW','Makanan ringan':'MKR','Minuman':'MNM','Kesehatan':'SHT'}

def choose_prefix(name, used, requested=''):
    requested=str(requested or '').strip().upper()
    standard=next((prefix for label,prefix in STANDARD_PREFIXES.items() if label.casefold()==name.casefold()),None)
    if requested and not re.fullmatch('[A-Z]{3}',requested):
        raise RuleError('Awalan kode harus tepat 3 huruf A–Z.')
    if standard and requested and requested!=standard:
        raise RuleError(f'Awalan kategori {name} adalah {standard}.')
    preferred=standard or requested
    if preferred:
        if preferred in used:raise RuleError('Awalan kode sudah digunakan kategori lain.')
        return preferred
    letters=re.sub('[^A-Z]','',unicodedata.normalize('NFKD',name).encode('ascii','ignore').decode().upper())
    if not letters:raise RuleError('Nama kategori harus memiliki huruf untuk membuat awalan kode.')
    base=(letters+'XXX')[:3]
    if base not in used and base not in STANDARD_PREFIXES.values():return base
    for a in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        for b in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            candidate=base[0]+a+b
            if candidate not in used and candidate not in STANDARD_PREFIXES.values():return candidate
    raise RuleError('Awalan kode otomatis tidak tersedia. Isi awalan lain.')

def next_product_code(db, category_id, reserve=True):
    statement=select(Category).where(Category.id==category_id)
    if reserve:statement=statement.with_for_update().execution_options(populate_existing=True)
    category=db.scalar(statement)
    if category is None or not category.active:raise RuleError('Pilih kategori yang aktif.')
    prefix=category.code_prefix
    if not prefix:
        used=set(db.scalars(select(Category.code_prefix).where(Category.code_prefix.is_not(None))))
        prefix=choose_prefix(category.nama,used)
        if reserve:category.code_prefix=prefix
    counter=int(category.code_counter or 0)
    # Includes archived products and historical import aliases: codes are never reused.
    existing=db.scalars(select(Product.kode).where(Product.kode.like(prefix+'%'))).all()
    for value in existing:
        if re.fullmatch(re.escape(prefix)+r'[0-9]+',value):counter=max(counter,int(value[3:]))
    while True:
        counter+=1
        if counter>1_000_000_000:raise RuleError('Nomor produk kategori mencapai batas.')
        value=f'{prefix}{counter:03d}'
        if db.scalar(select(Product.id).where(or_(Product.kode==value,Product.source_code==value))) is None:break
    if reserve:
        category.code_counter=counter
        db.flush()
    return value
