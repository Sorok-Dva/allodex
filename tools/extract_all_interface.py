#!/usr/bin/env python3
"""Extrait l'intégralité du pack Interface.Mini.pak en convertissant toutes les UITextures en PNG.

Sortie par défaut : /mnt/h/MyGames/Allods Online FR (FR)/extracted_interface
(accessible directement sous Windows dans H:\\MyGames\\Allods Online FR (FR)\\extracted_interface)
"""
import os
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.uitexture import decode_uitexture, trim_transparent_padding

DEFAULT_PAK = "/mnt/h/MyGames/Allods Online FR (FR)/data/Packs/Interface.Mini.pak"
DEFAULT_OUT = "/mnt/h/MyGames/Allods Online FR (FR)/extracted_interface"
TEXTURE_SUFFIX = ".(UITexture).bin"

def process_item(item):
    name, data, out_dir = item
    try:
        if name.endswith(TEXTURE_SUFFIX):
            rel = name[:-len(TEXTURE_SUFFIX)] + ".png"
            target = os.path.join(out_dir, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            img, _ = decode_uitexture(data)
            trimmed = trim_transparent_padding(img)
            trimmed.save(target)
            return True, name, None
        else:
            target = os.path.join(out_dir, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as f:
                f.write(data)
            return True, name, None
    except Exception as e:
        return False, name, str(e)

def main():
    pak_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PAK
    out_dir = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT

    print(f"Opening pak: {pak_path}")
    print(f"Target directory: {out_dir}")
    os.makedirs(out_dir, exist_ok=True)

    zf = zipfile.ZipFile(pak_path)
    names = zf.namelist()
    total = len(names)
    print(f"Total entries to extract: {total}")

    # Read all file bytes in main process or stream batches
    batch_size = 500
    success_count = 0
    fail_count = 0
    start_time = time.time()

    with ProcessPoolExecutor(max_workers=os.cpu_count() or 8) as executor:
        for i in range(0, total, batch_size):
            batch_names = names[i:i + batch_size]
            batch_items = [(n, zf.read(n), out_dir) for n in batch_names]
            results = executor.map(process_item, batch_items)
            for ok, n, err in results:
                if ok:
                    success_count += 1
                else:
                    fail_count += 1
                    print(f"Error extracting {n}: {err}", file=sys.stderr)
            elapsed = time.time() - start_time
            print(f"Progress: {success_count + fail_count}/{total} ({(success_count+fail_count)/total*100:.1f}%) in {elapsed:.1f}s")

    total_time = time.time() - start_time
    print(f"\nExtraction complete in {total_time:.1f}s!")
    print(f"Successfully extracted: {success_count}")
    print(f"Failed: {fail_count}")
    print(f"Destination: {out_dir}")

if __name__ == "__main__":
    main()
