"""Bounded, immutable text/image submission values without filesystem access."""
from dataclasses import replace
import unittest
from unittest.mock import patch

from fruitfly_agent.core.data_model import ImageBlock, TextBlock
from fruitfly_agent.core.data_model.media import normalize_input, image_bytes, validate_image
from tests.support.media import image, png_bytes


class MediaInputTests(unittest.TestCase):
    def test_input_rejects_invalid_blocks_bytes_formats_and_declared_mime_mismatch(self):
        for content in ([], [TextBlock(' ')], [object()], [ImageBlock('invalid!', 'image/png')],
                        [replace(image(), media_type='image/bmp')], [replace(image(), media_type='image/jpeg')]):
            with self.subTest(content_type=type(content).__name__), self.assertRaises(ValueError):
                normalize_input(content)
        original = [TextBlock('text'), image()]
        frozen = normalize_input(original)
        original.clear()
        self.assertEqual(frozen, [TextBlock('text'), image()])

    def test_image_number_single_size_and_combined_size_are_bounded(self):
        with self.assertRaisesRegex(ValueError, 'at most 8'):
            normalize_input([image()] * 9)
        with patch('fruitfly_agent.core.data_model.media.MAX_IMAGE_BYTES', 1), self.assertRaisesRegex(ValueError, '10 MiB'):
            image_bytes(image())
        with patch('fruitfly_agent.core.data_model.media.MAX_MEDIA_BYTES', len(png_bytes())), self.assertRaisesRegex(ValueError, 'combined images'):
            normalize_input([image(), image()])

    def test_png_container_corruption_and_incomplete_files_are_rejected(self):
        self.assertEqual(validate_image(png_bytes()), 'image/png')
        for data in (b'', png_bytes()[:-1], png_bytes()[:24] + b'X' + png_bytes()[25:], b'BMunsupported'):
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                validate_image(data)
