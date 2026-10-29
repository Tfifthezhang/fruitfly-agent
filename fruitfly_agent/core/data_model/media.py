"""Shared media input values and bounded submission validation.

Media interpretation and API encoding belong to tools and Providers respectively.
"""
from __future__ import annotations

import base64
import binascii
import struct
import zlib
from typing import TypeAlias

from .messages import ImageBlock, TextBlock

UserContent: TypeAlias = str | list[TextBlock | ImageBlock]
MAX_IMAGES = 8
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_MEDIA_BYTES = 32 * 1024 * 1024
IMAGE_TYPES = frozenset({'image/png', 'image/jpeg', 'image/gif', 'image/webp'})


def image_bytes(image: ImageBlock) -> bytes:
    if image.media_type not in IMAGE_TYPES:
        raise ValueError('unsupported image format; use PNG, JPEG, GIF or WebP')
    if len(image.data) > 4 * ((MAX_IMAGE_BYTES + 2) // 3):
        raise ValueError('image exceeds the 10 MiB input limit')
    try:
        data = base64.b64decode(image.data, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError('image content must be valid Base64') from exc
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError('image must contain between 1 byte and 10 MiB')
    return data


def normalize_input(content: UserContent, *, vision: bool | None = None) -> UserContent:
    """Copy a submitted value before queueing; reject unsupported fresh inputs."""
    if isinstance(content, str):
        if not content.strip():
            raise ValueError('prompt must not be empty')
        return content.strip()
    if not isinstance(content, list) or any(not isinstance(b, (TextBlock, ImageBlock)) for b in content):
        raise ValueError('input must be text or a list of text/image blocks')
    images = [b for b in content if isinstance(b, ImageBlock)]
    if images and vision is False:
        raise ValueError('the active model does not declare image input support; choose a vision model')
    if len(images) > MAX_IMAGES:
        raise ValueError('at most 8 images may be submitted together')
    total_bytes = 0
    for block in images:
        data = image_bytes(block)
        if validate_image(data) != block.media_type:
            raise ValueError('image media type differs from its contents')
        total_bytes += len(data)
    if total_bytes > MAX_MEDIA_BYTES:
        raise ValueError('combined images exceed the 32 MiB input limit')
    if not images and not any(b.text.strip() for b in content if isinstance(b, TextBlock)):
        raise ValueError('prompt must not be empty')
    return list(content)


def input_label(content: UserContent) -> str:
    if isinstance(content, str):
        return content
    return '\n'.join(b.text if isinstance(b, TextBlock) else f'[attachment: {b.media_type}]' for b in content)


def image_type(data: bytes) -> str | None:
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if data.startswith((b'GIF87a', b'GIF89a')):
        return 'image/gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    return None


def decode_text_file(data: bytes) -> str:
    """Reject known binary containers and invalid UTF-8 rather than invent text."""
    if (data.startswith((b'BM', b'RIFF', b'ID3', b'OggS', b'fLaC', b'\x1aE\xdf\xa3', b'%PDF', b'PK\x03\x04'))
            or data[4:8] == b'ftyp' or b'\x00' in data):
        raise ValueError('unsupported binary/media file; read supports UTF-8 text and PNG, JPEG, GIF or WebP images')
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError('file is not UTF-8 text or a supported image') from exc


def validate_image(data: bytes) -> str:
    """Check size and container integrity, without claiming full pixel decoding."""
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError('image must contain between 1 byte and 10 MiB')
    mime = image_type(data)
    valid = False
    if mime == 'image/png':
        offset, first, pixels = 8, True, False
        while offset + 12 <= len(data):
            size = struct.unpack('>I', data[offset:offset + 4])[0]
            end = offset + 12 + size
            if end > len(data):
                break
            kind = data[offset + 4:offset + 8]
            body = data[offset + 8:end - 4]
            if zlib.crc32(kind + body) & 0xffffffff != struct.unpack('>I', data[end - 4:end])[0]:
                break
            if first:
                if kind != b'IHDR' or size != 13:
                    break
                width, height = struct.unpack('>II', body[:8])
                if not width or not height or width * height > 40_000_000:
                    raise ValueError('image dimensions exceed the 40 megapixel limit or are invalid')
                first = False
            pixels = pixels or kind == b'IDAT'
            offset = end
            if kind == b'IEND':
                valid = size == 0 and pixels and offset == len(data)
                break
    elif mime == 'image/jpeg':
        valid = len(data) >= 12 and data.rstrip().endswith(b'\xff\xd9') and b'\xff\xda' in data
    elif mime == 'image/gif':
        valid = len(data) >= 14 and all(struct.unpack('<HH', data[6:10])) and data.endswith(b';')
    elif mime == 'image/webp':
        valid = len(data) >= 20 and struct.unpack('<I', data[4:8])[0] + 8 == len(data) and data[12:16] in {b'VP8 ', b'VP8L', b'VP8X'}
    if not valid:
        raise ValueError('unsupported, empty or damaged image; use a complete PNG, JPEG, GIF or WebP file')
    assert mime is not None
    return mime


