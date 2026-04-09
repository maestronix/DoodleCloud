from __future__ import annotations

from io import BytesIO
import math

import numpy as np
from PIL import Image

MIN_DIMENSION = 100


def bytes_to_png(binary_data: bytes) -> bytes:
    file_len = len(binary_data)
    len_bytes = file_len.to_bytes(4, byteorder="big")
    payload = len_bytes + binary_data

    pixels_needed = math.ceil(len(payload) / 3)
    min_pixels = MIN_DIMENSION * MIN_DIMENSION
    pixels_needed = max(pixels_needed, min_pixels)

    width = math.ceil(math.sqrt(pixels_needed))
    height = math.ceil(pixels_needed / width)

    total_bytes_needed = width * height * 3
    payload += b"\x00" * (total_bytes_needed - len(payload))

    byte_array = np.frombuffer(payload, dtype=np.uint8)
    image_array = byte_array.reshape((height, width, 3))
    img = Image.fromarray(image_array, "RGB")

    out = BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def png_to_bytes(image_data: bytes) -> bytes:
    img = Image.open(BytesIO(image_data)).convert("RGB")
    flat_bytes = np.array(img).tobytes()
    file_size = int.from_bytes(flat_bytes[:4], byteorder="big")
    if file_size <= 0 or file_size > len(flat_bytes):
        raise ValueError("invalid encoded chunk payload")
    return flat_bytes[4 : 4 + file_size]
