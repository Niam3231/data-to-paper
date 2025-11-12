#!/usr/bin/env python3
import argparse, os, io, math, zlib, base64, hashlib
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from pdf2image import convert_from_path
from PIL import Image

META_PREFIX = b'STPRv2META'

def bytes_to_bits(data: bytes):
    for byte in data:
        for i in range(8):
            yield (byte >> (7 - i)) & 1

def bits_to_bytes(bits):
    out = bytearray()
    byte = 0
    for i, bit in enumerate(bits):
        byte = (byte << 1) | bit
        if (i + 1) % 8 == 0:
            out.append(byte)
            byte = 0
    if len(bits) % 8 != 0:
        out.append(byte << (8 - len(bits) % 8))
    return bytes(out)

def encode_file(input_path, output_pdf, dpi=600, margin_inch=0.5):
    data = open(input_path, 'rb').read()
    compressed = zlib.compress(data, 9)
    meta = META_PREFIX + b'|' + hashlib.sha256(data).hexdigest().encode() + b'|' + str(len(data)).encode() + b'|'
    payload = meta + compressed
    bits = list(bytes_to_bits(payload))

    page_w, page_h = A4
    px_w = int(page_w / inch * dpi)
    px_h = int(page_h / inch * dpi)
    margin_px = int(margin_inch * dpi)
    usable_w = px_w - 2 * margin_px
    usable_h = px_h - 2 * margin_px
    bits_per_page = usable_w * usable_h

    total_pages = math.ceil(len(bits) / bits_per_page)
    print(f"Encoding {len(bits)} bits into {total_pages} pages...")

    c = canvas.Canvas(output_pdf, pagesize=A4)
    for p in range(total_pages):
        start = p * bits_per_page
        chunk = bits[start:start + bits_per_page]
        img = Image.new('1', (usable_w, usable_h), 1)
        img.putdata(chunk + [1] * (usable_w * usable_h - len(chunk)))
        img = img.resize((usable_w, usable_h), Image.NEAREST)
        img_byte = io.BytesIO()
        img.save(img_byte, format='PNG')
        img_byte.seek(0)
        c.drawImage(ImageReader(img_byte), margin_px / dpi * 72, margin_px / dpi * 72,
                    width=usable_w / dpi * 72, height=usable_h / dpi * 72)
        c.showPage()
    c.save()
    print(f"Done. Written to {output_pdf} ({total_pages} pages).")

def decode_pdf(input_pdf_or_folder, output_path, dpi=600, margin_inch=0.5):
    images = []
    if os.path.isdir(input_pdf_or_folder):
        for fn in sorted(os.listdir(input_pdf_or_folder)):
            if fn.lower().endswith(('.png', '.jpg', '.jpeg')):
                images.append(Image.open(os.path.join(input_pdf_or_folder, fn)).convert('1'))
    else:
        images = convert_from_path(input_pdf_or_folder, dpi=dpi)

    bits = []
    for img in images:
        img = img.convert('1')
        bits.extend([0 if p else 1 for p in img.getdata()])

    payload = bits_to_bytes(bits)
    if META_PREFIX not in payload:
        raise ValueError("Metadata not found")
    prefix_index = payload.index(META_PREFIX)
    payload = payload[prefix_index + len(META_PREFIX) + 1:]
    sha, size_str, rest = payload.split(b'|', 2)
    expected_sha, expected_size = sha.decode(), int(size_str.decode())
    decompressed = zlib.decompress(rest)
    actual_sha = hashlib.sha256(decompressed).hexdigest()
    if actual_sha != expected_sha:
        print("WARNING: SHA256 mismatch!")
    with open(output_path, 'wb') as f:
        f.write(decompressed[:expected_size])
    print(f"Decoded to {output_path}, {expected_size} bytes, SHA256={actual_sha}")

def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['encode', 'decode'])
    p.add_argument('input')
    p.add_argument('output')
    p.add_argument('--dpi', type=int, default=600)
    p.add_argument('--margin', type=float, default=0.5)
    args = p.parse_args()
    if args.mode == 'encode':
        encode_file(args.input, args.output, args.dpi, args.margin)
    else:
        decode_pdf(args.input, args.output, args.dpi, args.margin)

if __name__ == '__main__':
    main()
