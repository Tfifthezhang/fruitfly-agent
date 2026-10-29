"""Small original image containers and model declarations for offline tests."""
import base64
import struct
import zlib

from fruitfly_agent.core.data_model import ImageBlock


def png_bytes():
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00')) + chunk(b'IEND', b''))


def image():
    return ImageBlock(base64.b64encode(png_bytes()).decode('ascii'), 'image/png')


def write_models(root, *, vision=True):
    path = root / '.fruitfly/models.yaml'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('models:\n  offline:\n    sdk: openai\n    protocol: chat-completions\n'
                    '    model: offline-model\n    api_key_env: TEST_KEY\n    context_window: 16000\n'
                    '    max_output_tokens: 1024\n    capabilities:\n      vision: ' + str(vision).lower() + '\n')
