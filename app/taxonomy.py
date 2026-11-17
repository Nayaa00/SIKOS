from .services import RuleError, text

CATEGORIES = ('Bahan pokok', 'Perawatan', 'Makanan ringan', 'Minuman', 'Kesehatan')
LEGACY = {name: 'Bahan pokok' for name in ('Beras','Minyak','Gula','Telur','Tepung','Mi instan','Bumbu','Saus dan kecap')}
LEGACY['Susu'] = 'Minuman'

def category_name(value):
    value = text(value, 'Kategori', 100)
    for name in CATEGORIES:
        if value.casefold() == name.casefold():
            return name
    return value

def classify_import(category, label):
    category = text(category, 'Kategori', 100)
    legacy = next((name for name in LEGACY if name.casefold() == category.casefold()), None)
    if legacy:
        return LEGACY[legacy], text(label or legacy, 'Label', 100)
    return category_name(category), text(label, 'Label', 100)
