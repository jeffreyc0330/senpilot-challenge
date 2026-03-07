"""
zipper.py — compress a list of files into a ZIP archive.
"""

import os
import zipfile
from pathlib import Path

from config import DOWNLOAD_DIR


def compress_files(file_paths: list, output_path: str) -> str:
    """
    Compress file_paths into a ZIP archive at output_path.

    Files are stored using only their basenames (no directory structure inside the ZIP).

    Args:
        file_paths: list of absolute file path strings
        output_path: destination path for the .zip file

    Returns:
        The output_path string (for convenience)
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print(f"[zipper] Creating ZIP: {output_path}")
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fp in file_paths:
            if not os.path.exists(fp):
                print(f"[zipper] Warning: file not found, skipping: {fp}")
                continue
            arcname = os.path.basename(fp)
            zf.write(fp, arcname=arcname)
            print(f"[zipper]   Added: {arcname}")

    size_kb = os.path.getsize(output_path) / 1024
    print(f"[zipper] ZIP created: {output_path} ({size_kb:.1f} KB)")
    return output_path


def make_zip_path(matter_number: str) -> str:
    """Return the standard output ZIP path for a given matter number."""
    zips_dir = os.path.join(DOWNLOAD_DIR, "zips")
    return os.path.join(zips_dir, f"{matter_number}.zip")
