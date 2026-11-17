"""Locally hosted, attributed product photos; preserve custom HTTPS URLs."""
from pathlib import Path
import re

PHOTO_ROOT = Path(__file__).resolve().parent / 'static/products'
PLACEHOLDER = '/static/products/placeholder.svg'
RULES = [('beras', 'rice.jpg'), ('minyak', 'oil.jpg'), ('gula', 'sugar.jpg'), ('telur', 'eggs.jpg'), ('tepung', 'flour.jpg'), ('sabun mandi cair', 'liquid-soap.jpg'), ('sabun mandi', 'bar-soap.jpg'), ('detergen', 'detergent.jpg'), ('sabun cuci piring', 'dish-soap.jpg'), ('sikat gigi', 'toothbrush.jpg'), ('pasta gigi', 'toothpaste.jpg'), ('keripik singkong', 'cassava-chips.jpg'), ('keripik kentang', 'potato-chips.jpg'), ('biskuit', 'biscuits.jpg'), ('wafer', 'wafer.jpg'), ('kacang', 'peanuts.jpg'), ('permen', 'mint-candy.jpg'), ('air mineral', 'water.jpg'), ('teh celup', 'tea-bags.jpg'), ('teh siap', 'bottled-tea.jpg'), ('kopi', 'coffee.jpg'), ('susu', 'milk.jpg'), ('isotonik', 'sports-drink.jpg'), ('parasetamol', 'paracetamol.jpg'), ('paracetamol', 'paracetamol.jpg'), ('oralit', 'oral-rehydration.jpg'), ('vitamin', 'vitamin-c.jpg'), ('plester', 'bandage.jpg'), ('kapas', 'cotton.jpg'), ('masker', 'mask.jpg')]

def default_product_image(product):
    name = str(getattr(product, 'nama', '') or '').casefold()
    for term, file in RULES:
        if term in name:
            return '/static/products/' + file
    return PLACEHOLDER

def valid_product_image(value):
    if value.startswith('https://') and len(value)<=500:
        return True
    if re.fullmatch(r'/static/products/[a-z0-9-]+\.(?:jpg|png|webp|svg)', value):
        return (PHOTO_ROOT / value.rsplit('/',1)[-1]).is_file()
    return False

def product_image(product):
    value = str(getattr(product, 'gambar', '') or '')
    return value if valid_product_image(value) else default_product_image(product)
