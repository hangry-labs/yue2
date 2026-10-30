"""Regression checks for the weight-free image packaging guard."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('weights', ROOT / 'scripts/check_no_weights.py')
weights = importlib.util.module_from_spec(spec)
spec.loader.exec_module(weights)


class WeightPackagingTests(unittest.TestCase):
    def test_code_and_download_manifest_are_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'manifest.json').write_text('{"filename": "model.gguf"}')
            (root / 'yue-server').write_bytes(b'\x7fELFexample')
            weights.check(root)

    def test_weight_extensions_fail_even_for_empty_misplaced_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'opt' / 'yue'
            root.mkdir(parents=True)
            for suffix in ('.gguf', '.safetensors', '.pt', '.pth', '.ckpt', '.bin',
                           '.onnx', '.h5', '.hdf5', '.tflite', '.npz', '.ggml'):
                with self.subTest(suffix=suffix):
                    path = root / ('accident' + suffix.upper())
                    path.touch()
                    with self.assertRaisesRegex(ValueError, 'accident'):
                        weights.check(tmp)
                    path.unlink()

    def test_renamed_gguf_and_legacy_weights_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'innocent.dat'
            for magic in weights.WEIGHT_MAGIC:
                with self.subTest(magic=magic):
                    path.write_bytes(magic + b'payload')
                    with self.assertRaisesRegex(ValueError, 'innocent.dat'):
                        weights.check(tmp)

    def test_missing_scan_root_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'does not exist'):
                weights.check(Path(tmp) / 'missing')


if __name__ == '__main__':
    unittest.main()
