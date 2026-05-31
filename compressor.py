import os
from PIL import Image, ExifTags
from io import BytesIO

SUPPORTED = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff")

# ================================
# FIX EXIF ROTATION
# ================================
def fix_rotation(img):
    try:
        exif = img._getexif()
        if not exif:
            return img
        for tag, value in exif.items():
            if ExifTags.TAGS.get(tag) == "Orientation":
                if value == 3:
                    img = img.rotate(180, expand=True)
                elif value == 6:
                    img = img.rotate(270, expand=True)
                elif value == 8:
                    img = img.rotate(90, expand=True)
                break
    except Exception:
        pass
    return img


# ================================
# COMPRESS TO TARGET RANGE
# ================================
def compress_to_target(img, target_min, target_max):
    """
    Compresses a PIL image to fit within target_min and target_max bytes.
    Returns: (compressed bytes, final size in bytes, success bool)
    """
    buffer = BytesIO()
    quality_min = 10
    quality_max = 95
    best_result = None

    # Binary search for right quality
    while quality_min <= quality_max:
        mid = (quality_min + quality_max) // 2
        buffer = BytesIO()
        img.save(buffer, "JPEG", quality=mid, optimize=True, dpi=(300, 300))
        size = buffer.tell()

        if target_min <= size <= target_max:
            return buffer.getvalue(), size, True
        elif size > target_max:
            quality_max = mid - 1
        else:
            best_result = buffer.getvalue()
            quality_min = mid + 1

    # Still too large — downscale gradually
    buffer = BytesIO()
    img.save(buffer, "JPEG", quality=10, optimize=True, dpi=(300, 300))
    if buffer.tell() > target_max:
        scale = 0.9
        w, h = img.size
        for _ in range(20):
            new_w = int(w * scale)
            new_h = int(h * scale)
            if new_w < 100 or new_h < 100:
                break
            downscaled = img.resize((new_w, new_h), Image.LANCZOS)
            for q in range(95, 9, -5):
                buffer = BytesIO()
                downscaled.save(buffer, "JPEG", quality=q,
                                optimize=True, dpi=(300, 300))
                size = buffer.tell()
                if target_min <= size <= target_max:
                    return buffer.getvalue(), size, True
                elif size < target_min:
                    break
            if buffer.tell() < target_min:
                break
            scale -= 0.1

    # Still too small — upscale gradually
    w, h = img.size
    scale = 1.1
    for _ in range(20):
        new_w = int(w * scale)
        new_h = int(h * scale)
        upscaled = img.resize((new_w, new_h), Image.LANCZOS)
        buffer = BytesIO()
        upscaled.save(buffer, "JPEG", quality=95,
                      optimize=True, dpi=(300, 300))
        size = buffer.tell()
        if target_min <= size <= target_max:
            return buffer.getvalue(), size, True
        elif size > target_max:
            for q in range(94, 10, -1):
                buffer = BytesIO()
                upscaled.save(buffer, "JPEG", quality=q,
                              optimize=True, dpi=(300, 300))
                size = buffer.tell()
                if target_min <= size <= target_max:
                    return buffer.getvalue(), size, True
                elif size < target_min:
                    break
            break
        scale += 0.1

    # Return best we got
    final = buffer.getvalue()
    return final, len(final), False


# ================================
# MAIN FUNCTION FLASK WILL CALL
# ================================
def compress_image(file_storage, target_min_kb, target_max_kb):
    """
    Takes a Flask file upload object, compresses it.
    Returns: (compressed bytes, original size KB, final size KB, success bool)
    """
    target_min = target_min_kb * 1024
    target_max = target_max_kb * 1024
    MAX_DIMENSION = 1200

    # Read original size
    file_storage.seek(0, 2)  # Seek to end
    original_size = file_storage.tell()
    file_storage.seek(0)     # Reset to start

    # Open with Pillow
    img = Image.open(file_storage)
    img = img.convert("RGB")
    img = fix_rotation(img)
    img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)

    # Upscale if too small
    w, h = img.size
    if w < 800 or h < 800:
        new_w = max(w, 800)
        new_h = max(h, 800)
        img = img.resize((new_w, new_h), Image.LANCZOS)

    # Compress
    result_bytes, final_size, success = compress_to_target(
        img, target_min, target_max
    )

    original_kb = round(original_size / 1024, 1)
    final_kb = round(final_size / 1024, 1)

    return result_bytes, original_kb, final_kb, success