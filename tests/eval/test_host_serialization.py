"""Derived machine settings preserve all owner-admitted execution controls."""
from pathlib import Path
import tempfile
import unittest
import yaml
from fruitfly_eval.harbor.host import HostConfig


class HostSerializationTests(unittest.TestCase):
    def test_effective_host_roundtrip_preserves_relay_and_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = {'cache': str(root / 'cache'),
                'agent': {'python': '/runtime/bin/python', 'mounts': [
                    {'source': str(root / 'runtime'), 'target': '/runtime'}]},
                'backend': {'file': 'runner.yaml'},
                'model_relay': {'network_url': 'https://relay.example', 'listen_host': '0.0.0.0',
                    'certificate': 'server.pem', 'private_key': 'server-key.pem', 'ca': 'ca.pem'}}
            original = root / 'host.yaml'
            original.write_text(yaml.safe_dump(payload))
            host = HostConfig.read(root, original)
            effective = host.to_dict()
            self.assertEqual(effective['model_relay'], dict(host.model_relay))
            self.assertEqual(effective['evidence'], dict(host.evidence))
            self.assertEqual(Path(effective['backend']['file']), root / 'runner.yaml')
            derived = root / 'derived/host.yaml'
            derived.parent.mkdir()
            derived.write_text(yaml.safe_dump(effective))
            restored = HostConfig.read(root, derived)
            self.assertEqual(restored.identity(), host.identity())
            self.assertEqual(restored.to_dict(), effective)
