from io import BytesIO
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from .services import RuleError

MAX_PROOF_SIZE=5*1024*1024

def validate_payment_proof(raw):
    if not raw or len(raw)>MAX_PROOF_SIZE:
        raise RuleError('Bukti pembayaran wajib berupa gambar, maksimal 5 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as im:
                if im.format not in ('JPEG','PNG','WEBP') or im.width*im.height>20_000_000:
                    raise RuleError('Gunakan gambar JPG, PNG atau WebP maksimal 20 megapiksel.')
                im.load()
                image=ImageOps.exif_transpose(im).convert('RGB')
                image.thumbnail((2560,2560))
                output=BytesIO();image.save(output,format='JPEG',quality=90)
                return output.getvalue()
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise RuleError('File bukti tidak dapat dibaca sebagai gambar yang valid.')
