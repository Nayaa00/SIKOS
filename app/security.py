import hashlib
import secrets
import hmac
from fastapi import HTTPException

ITERATIONS = 600_000

def hash_password(password):
    if len(password) < 8 or len(password) > 128:
        raise ValueError('Password harus 8–128 karakter.')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),ITERATIONS).hex()
    return f'pbkdf2_sha256${ITERATIONS}${salt}${digest}'

def verify_password(password, encoded):
    if not password or len(password) > 128:
        return False
    try:
        scheme, count, salt, expected = encoded.split('$')
        if scheme != 'pbkdf2_sha256':
            return False
        actual = hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),int(count)).hex()
        return hmac.compare_digest(actual,expected)
    except (ValueError,TypeError):
        return False

def csrf_token(request):
    if 'csrf' not in request.session:
        request.session['csrf'] = secrets.token_hex(32)
    return request.session['csrf']

def check_csrf(request, form):
    expected = request.session.get('csrf','')
    actual = str(form.get('csrf',''))
    if not expected or not hmac.compare_digest(expected,actual):
        raise HTTPException(403,'Form kedaluwarsa. Muat ulang halaman dan coba lagi.')
