import os
import time
import shutil
from PIL import Image, ExifTags
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ================================
# SETTINGS — change these only
# ================================
INPUT_FOLDER = "input_images"
OUTPUT_FOLDER = "output_images"
TARGET_MIN_KB = 17
TARGET_MAX_KB = 20
MAX_DIMENSION = 1200

# ================================
TARGET_MIN = TARGET_MIN_KB * 1024
TARGET_MAX = TARGET_MAX_KB * 1024
SUPPORTED = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff")

os.makedirs(OUTPUT_FOLDER, exist_ok=True)


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
def compress_to_target(img, output_path):
    quality_min = 10
    quality_max = 95
    best_quality = None
    best_size = None

    while quality_min <= quality_max:
        mid = (quality_min + quality_max) // 2
        img.save(output_path, "JPEG", quality=mid, optimize=True, dpi=(300, 300))
        size = os.path.getsize(output_path)

        if TARGET_MIN <= size <= TARGET_MAX:
            return size, True
        elif size > TARGET_MAX:
            quality_max = mid - 1
        else:
            best_quality = mid
            best_size = size
            quality_min = mid + 1

    # Still above 20KB — downscale gradually
    img.save(output_path, "JPEG", quality=10, optimize=True, dpi=(300, 300))
    if os.path.getsize(output_path) > TARGET_MAX:
        scale = 0.9
        w, h = img.size
        for _ in range(20):
            new_w = int(w * scale)
            new_h = int(h * scale)
            if new_w < 100 or new_h < 100:
                break
            downscaled = img.resize((new_w, new_h), Image.LANCZOS)
            for q in range(95, 9, -5):
                downscaled.save(output_path, "JPEG", quality=q, optimize=True, dpi=(300, 300))
                size = os.path.getsize(output_path)
                if TARGET_MIN <= size <= TARGET_MAX:
                    return size, True
                elif size < TARGET_MIN:
                    break
            size = os.path.getsize(output_path)
            if size < TARGET_MIN:
                break
            scale -= 0.1

    # Still under 17KB — upscale gradually
    if best_size and best_size < TARGET_MIN:
        scale = 1.1
        w, h = img.size
        for _ in range(20):
            new_w = int(w * scale)
            new_h = int(h * scale)
            upscaled = img.resize((new_w, new_h), Image.LANCZOS)
            upscaled.save(output_path, "JPEG", quality=95, optimize=True, dpi=(300, 300))
            size = os.path.getsize(output_path)
            if TARGET_MIN <= size <= TARGET_MAX:
                return size, True
            elif size > TARGET_MAX:
                for q in range(94, 10, -1):
                    upscaled.save(output_path, "JPEG", quality=q, optimize=True, dpi=(300, 300))
                    size = os.path.getsize(output_path)
                    if TARGET_MIN <= size <= TARGET_MAX:
                        return size, True
                    elif size < TARGET_MIN:
                        break
                break
            scale += 0.1

    final_size = os.path.getsize(output_path)
    return final_size, False


# ================================
# PROCESS SINGLE IMAGE
# ================================
def process_image(img_path, output_path):
    try:
        # Create output subfolder if needed
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        img = Image.open(img_path)
        img = img.convert("RGB")
        img = fix_rotation(img)
        img.thumbnail((MAX_DIMENSION, MAX_DIMENSION))

        w, h = img.size
        if w < 800 or h < 800:
            new_w = max(w, 800)
            new_h = max(h, 800)
            img = img.resize((new_w, new_h), Image.LANCZOS)

        final_size, in_range = compress_to_target(img, output_path)
        final_kb = final_size / 1024
        filename = os.path.basename(img_path)

        if in_range:
            print(f"  ✓ {filename} → {final_kb:.1f}KB ✅ in range")
        elif final_size > TARGET_MAX:
            print(f"  ⚠ {filename} → {final_kb:.1f}KB (above {TARGET_MAX_KB}KB)")
        else:
            print(f"  ⚠ {filename} → {final_kb:.1f}KB (below {TARGET_MIN_KB}KB)")

        img.close()
        return True

    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


# ================================
# SCAN FOLDER RECURSIVELY
# Handles subfolders and image folders
# ================================
def scan_and_process_folder(input_folder, output_folder):
    found = 0
    success = 0
    failed = 0

    for root, dirs, files in os.walk(input_folder):
        for file in files:
            if file.lower().endswith(SUPPORTED):
                found += 1
                img_path = os.path.join(root, file)

                # Mirror folder structure in output
                relative = os.path.relpath(root, input_folder)
                out_dir = os.path.join(output_folder, relative)
                output_path = os.path.join(out_dir, os.path.splitext(file)[0] + ".jpg")

                print(f"\n[{found}] {img_path}")
                result = process_image(img_path, output_path)
                if result:
                    success += 1
                else:
                    failed += 1

    return found, success, failed


# ================================
# AUTO WATCHER
# Detects new images added to folder
# ================================
class ImageHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            # New folder pasted — scan entire folder
            print(f"\n📁 New folder detected: {event.src_path}")
            time.sleep(1)  # Wait for files to finish copying
            found, success, failed = scan_and_process_folder(
                event.src_path,
                OUTPUT_FOLDER
            )
            print(f"\nFolder done — {success} processed, {failed} failed")

        elif event.src_path.lower().endswith(SUPPORTED):
            # Single image added
            print(f"\n🖼 New image detected: {os.path.basename(event.src_path)}")
            time.sleep(0.5)  # Wait for file to finish copying

            relative = os.path.relpath(
                os.path.dirname(event.src_path), INPUT_FOLDER
            )
            out_dir = os.path.join(OUTPUT_FOLDER, relative)
            output_path = os.path.join(
                out_dir,
                os.path.splitext(os.path.basename(event.src_path))[0] + ".jpg"
            )
            process_image(event.src_path, output_path)


# ================================
# MAIN — PROCESS EXISTING + WATCH
# ================================
print(f"\nPassport Image Compressor")
print(f"{'='*50}")
print(f"Target size:   {TARGET_MIN_KB}KB — {TARGET_MAX_KB}KB")
print(f"Watching:      {INPUT_FOLDER}")
print(f"Output:        {OUTPUT_FOLDER}")
print(f"{'='*50}")

# First — process any existing images
print(f"\nScanning existing images...")
found, success, failed = scan_and_process_folder(INPUT_FOLDER, OUTPUT_FOLDER)

if found == 0:
    print(f"No existing images found — watching for new ones...")
else:
    print(f"\n{'='*50}")
    print(f"Existing images done — ✓ {success} processed, ✗ {failed} failed")
    print(f"{'='*50}")

# Then — watch for new images
print(f"\n👁 Watching '{INPUT_FOLDER}' for new images...")
print(f"Add images or paste folders — they compress automatically!")
print(f"Press Ctrl+C to stop\n")

observer = Observer()
observer.schedule(ImageHandler(), INPUT_FOLDER, recursive=True)
observer.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    observer.stop()
    print(f"\nStopped watching. Goodbye!")

observer.join()