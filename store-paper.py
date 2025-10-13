#!/usr/bin/env python3
"""
store-paper.py — encode files into printable QR-code PDF and decode them back, with verbose colored progress updates.
"""

from __future__ import annotations
import argparse
import base64
import io
import os
import sys
import zlib
import hashlib
from typing import List, Tuple
from reportlab.lib.utils import ImageReader

try:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_Q
    from PIL import Image
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from pdf2image import convert_from_path
    from pyzbar.pyzbar import decode as zbar_decode
except Exception as e:
    print("Missing dependency or environment issue:", e)
    sys.exit(1)

# --- Configuration ---
CHUNK_SIZE = 800
ERROR_CORRECTION = ERROR_CORRECT_Q
QR_BORDER = 1
BOX_SIZE = 4
QR_PER_ROW = 5
QR_PER_COL = 7
MARGIN_MM = 8
CAPTION_HEIGHT_MM = 10
PAGE_TOP_SHIFT_MM = 8
META_PREFIX = "STPRv1-META"
PART_PREFIX = "STPRv1-PART"

# ANSI color codes
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
RESET = '\033[0m'

def colored(text, color):
    return f"{color}{text}{RESET}"

def make_qr(payload: str) -> Image.Image:
    qr = qrcode.QRCode(error_correction=ERROR_CORRECTION, border=QR_BORDER, box_size=BOX_SIZE)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    return img

def create_pdf(qr_images: List[Tuple[Image.Image, str]], out_pdf: str, filename: str, size: int, total_qrs: int, sha256: str) -> None:
    page_w, page_h = A4
    margin = MARGIN_MM * mm
    caption_h = CAPTION_HEIGHT_MM * mm
    page_shift = PAGE_TOP_SHIFT_MM * mm
    avail_w = page_w - 2 * margin
    avail_h = page_h - 2 * margin
    cols = QR_PER_ROW
    rows = QR_PER_COL
    cell_w = avail_w / cols
    cell_h = avail_h / rows

    c = canvas.Canvas(out_pdf, pagesize=A4)
    info_text = f"{filename} - {size} bytes - {total_qrs} QR codes - SHA256: {sha256}"
    c.setFont("Helvetica", 8)
    c.drawString(margin, page_h - margin, info_text)

    print(colored(f"{YELLOW}Building PDF pages...{RESET}", YELLOW))
    idx = 0
    total = len(qr_images)
    for page_num in range((total + cols*rows - 1) // (cols*rows)):
        for r in range(rows):
            for col in range(cols):
                if idx >= total:
                    break
                img, _ = qr_images[idx]
                max_img_w = cell_w * 0.95
                max_img_h = cell_h * 0.95
                w, h = img.size
                dpi = 300.0
                w_pt = w / dpi * 72.0
                h_pt = h / dpi * 72.0
                scale = min(max_img_w / w_pt, max_img_h / h_pt, 1.0)
                draw_w = w_pt * scale
                draw_h = h_pt * scale
                x = margin + col * cell_w + (cell_w - draw_w) / 2
                y = page_h - margin - (r + 1) * cell_h + (cell_h - draw_h) / 2 - caption_h + page_shift
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                img_byte_arr.seek(0)
                c.drawImage(ImageReader(img_byte_arr), x, y, width=draw_w, height=draw_h)
                idx += 1
                progress_pct = idx / total * 100
                bar_len = 40
                filled_len = int(bar_len * idx / total)
                bar = '=' * filled_len + '-' * (bar_len - filled_len)
                print(f"{YELLOW}[{idx}/{total}] [{bar}] {progress_pct:.2f}%{RESET}", end='\r', flush=True)
            if idx >= total:
                break
        c.showPage()
    c.save()
    print(colored(f"\nPDF creation complete! Total QR codes: {total}. Written to {out_pdf}", GREEN))

def encode_file(input_path: str, output_pdf: str) -> None:
    print(colored(f"{YELLOW}Reading input file...{RESET}", YELLOW))
    with open(input_path, 'rb') as f:
        data = f.read()
    orig_size = len(data)
    print(colored(f"{YELLOW}Compressing data ({orig_size} bytes)...{RESET}", YELLOW))
    compressed = zlib.compress(data, level=9)
    print(colored(f"{GREEN}Compression complete: {len(compressed)} bytes{RESET}", GREEN))
    print(colored(f"{YELLOW}Encoding to Base64...{RESET}", YELLOW))
    b64 = base64.b64encode(compressed).decode('ascii')
    print(colored(f"{YELLOW}Splitting into chunks...{RESET}", YELLOW))
    chunks = [b64[i:i+CHUNK_SIZE] for i in range(0, len(b64), CHUNK_SIZE)]
    total = len(chunks) + 1
    qr_images: List[Tuple[Image.Image, str]] = []
    filename = os.path.basename(input_path)
    meta_payload = f"{META_PREFIX}|{filename}|{total}|{orig_size}|{hashlib.sha256(data).hexdigest()}"
    qr_images.append((make_qr(meta_payload), ''))
    for i, chunk in enumerate(chunks, start=1):
        payload = f"{PART_PREFIX}|{filename}|{total}|{i}|{chunk}"
        qr_images.append((make_qr(payload), ''))
    print(colored(f"{YELLOW}Generating QR codes ({len(qr_images)} total)...{RESET}", YELLOW))
    create_pdf(qr_images, output_pdf, filename, orig_size, total, hashlib.sha256(data).hexdigest())

def decode_pdf(input_pdf_or_folder: str, output_path: str) -> None:
    images = []
    if os.path.isdir(input_pdf_or_folder):
        for fn in sorted(os.listdir(input_pdf_or_folder)):
            if fn.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp')):
                images.append(Image.open(os.path.join(input_pdf_or_folder, fn)).convert('RGB'))
    else:
        images = convert_from_path(input_pdf_or_folder, dpi=300)
    found_parts = {}
    expected_total = None
    filename_hint = None
    expected_sha256 = None
    for page_idx, img in enumerate(images, start=1):
        barcodes = zbar_decode(img)
        for b in barcodes:
            try:
                content = b.data.decode('utf-8')
            except Exception:
                continue
            if content.startswith(META_PREFIX):
                parts = content.split('|')
                if len(parts) >= 5:
                    _, fn, tot, _, sha = parts[:5]
                    expected_total = int(tot)
                    filename_hint = fn
                    expected_sha256 = sha
            elif content.startswith(PART_PREFIX):
                parts = content.split('|', 4)
                if len(parts) >= 5:
                    _, fn, tot, idx_s, b64data = parts
                    idx = int(idx_s)
                    found_parts[idx] = b64data
    if expected_total is None:
        print(colored("No metadata found. Exiting.", RED))
        return
    num_parts = expected_total - 1
    missing = [i for i in range(1, num_parts+1) if i not in found_parts]
    if missing:
        print(colored(f"Missing parts: {missing}", RED))
        return
    assembled_b64 = ''.join(found_parts[i] for i in range(1, num_parts+1))
    data = zlib.decompress(base64.b64decode(assembled_b64))
    sha256_calc = hashlib.sha256(data).hexdigest()
    if expected_sha256 and expected_sha256 != sha256_calc:
        print(colored(f"Warning: SHA256 mismatch.", RED))
    out_name = output_path
    if os.path.isdir(output_path):
        out_name = os.path.join(output_path, filename_hint or 'restored.bin')
    with open(out_name, 'wb') as f:
        f.write(data)
    print(colored(f"Wrote reconstructed file to {out_name} ({len(data)} bytes). SHA256 {sha256_calc}.", GREEN))

def main():
    p = argparse.ArgumentParser(description='Encode a file to printable QR PDF, or decode from printed PDF.')
    p.add_argument('mode', choices=['encode', 'decode'])
    p.add_argument('input', help='input file (encode: file to store, decode: PDF or folder of images)')
    p.add_argument('output', help='output file (encode: PDF to create, decode: restored file name)')
    args = p.parse_args()
    if args.mode == 'encode':
        encode_file(args.input, args.output)
    else:
        decode_pdf(args.input, args.output)

if __name__ == '__main__':
    main()