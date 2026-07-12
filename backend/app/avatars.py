"""Avatar image handling: validate, square-crop, resize, and store on disk.

Photos live on the local filesystem under MEDIA_ROOT (never in the database and
never off the box), one fixed file per user id. The stored image is always a
256x256 WebP, so uploads are normalised the moment they arrive: whatever the
phone sends (a big rotated JPEG, a PNG, a WebP) becomes the same small square.
"""

import io
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings

# Reject anything larger before we even try to decode it. Phone photos are a
# few MB; 12 MB is generous headroom without inviting a decode-bomb.
MAX_UPLOAD_BYTES = 12 * 1024 * 1024

# Decode ceiling in pixels, checked from the header before any pixel buffer
# is allocated: a small crafted PNG can claim absurd dimensions and cost
# gigabytes to decode. 130 MP clears any phone camera's full-resolution
# output with room to spare.
MAX_PIXELS = 130_000_000

# The one size we store. Retina phone displays render the largest avatar around
# 80pt, so 256px covers 3x density with room to spare.
SIZE = 256


def _dir() -> Path:
    return Path(settings.media_root) / "avatars"


def avatar_path(user_id: int) -> Path:
    """Fixed on-disk path for a user's avatar. The URL is versioned by the
    user's avatar_updated_at, so the filename itself never has to change."""
    return _dir() / f"{user_id}.webp"


class BadImage(ValueError):
    """The uploaded bytes were not a decodable image."""


def process_and_save(raw: bytes, user_id: int) -> None:
    """Decode, orient, centre-crop to a square, downscale, and write the WebP.

    Raises BadImage if the bytes can't be read as an image."""
    try:
        img = Image.open(io.BytesIO(raw))
        if img.width * img.height > MAX_PIXELS:
            raise BadImage("That image is too large.")
        img.load()
    except Image.DecompressionBombError as err:
        # Pillow's own backstop (it fires at open() for the truly absurd,
        # before our dimension check can run).
        raise BadImage("That image is too large.") from err
    except (UnidentifiedImageError, OSError) as err:
        raise BadImage("Could not read that image.") from err

    # Honour the EXIF orientation phones bake in, then drop alpha/palette so
    # the WebP encodes predictably.
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")

    # Centre square crop, then resize down to the one stored size.
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    if side != SIZE:
        img = img.resize((SIZE, SIZE), Image.LANCZOS)

    path = avatar_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp file then rename so a concurrent read never sees a
    # half-written image.
    tmp = path.with_suffix(".webp.tmp")
    img.save(tmp, "WEBP", quality=82, method=6)
    tmp.replace(path)


def delete_avatar(user_id: int) -> None:
    avatar_path(user_id).unlink(missing_ok=True)
