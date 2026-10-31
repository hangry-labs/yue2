"""Storage migration must preserve user data and refuse unsafe partial moves."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import storage
import download_models


class StorageMigrationTests(unittest.TestCase):
    def fixture(self, root):
        for name in ('models', 'adapters', 'results'):
            folder = root / name
            folder.mkdir()
            (folder / 'user-content').write_bytes(name.encode())

    def test_migration_preserves_data_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.fixture(root)
            with patch.object(storage, 'running_mounts', return_value=[]) as mounts:
                storage.migrate(root)
                storage.migrate(root)
            mounts.assert_called_once()
            for name in ('models', 'adapters', 'results'):
                self.assertFalse((root / name).exists())
                self.assertEqual((root / 'data' / name / 'user-content').read_bytes(), name.encode())

    def test_collision_refuses_all_moves_before_changing_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.fixture(root)
            (root / 'data/adapters').mkdir(parents=True)
            with patch.object(storage, 'running_mounts') as mounts:
                with self.assertRaisesRegex(RuntimeError, 'Both storage locations'):
                    storage.migrate(root)
            mounts.assert_not_called()
            self.assertTrue((root / 'models/user-content').is_file())
            self.assertTrue((root / 'adapters/user-content').is_file())

    def test_live_mount_in_any_directory_blocks_all_moves(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.fixture(root)
            with patch.object(storage, 'running_mounts', return_value=[
                    ('other-container', str(root / 'adapters' / 'nested'))]):
                with self.assertRaisesRegex(RuntimeError, 'other-container still mounts'):
                    storage.migrate(root)
            self.assertTrue((root / 'models/user-content').is_file())
            self.assertFalse((root / 'data').exists())

    def test_move_error_restores_prior_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.fixture(root)
            rename = Path.rename

            def fail_second_move(path, target):
                if path == root / 'adapters':
                    raise OSError('locked directory')
                return rename(path, target)

            with patch.object(storage, 'running_mounts', return_value=[]), \
                    patch.object(Path, 'rename', fail_second_move):
                with self.assertRaisesRegex(OSError, 'locked directory'):
                    storage.migrate(root)
            self.assertTrue((root / 'models/user-content').is_file())
            self.assertFalse((root / 'data/models').exists())

    def test_legacy_models_do_not_trigger_duplicate_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'models').mkdir()
            with patch.object(storage, 'ROOT', root), \
                    patch.object(download_models, 'download') as download:
                with self.assertRaisesRegex(RuntimeError, 'Legacy local data'):
                    download_models.main()
            download.assert_not_called()

    def test_redirected_storage_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory).resolve()
            try:
                (root / 'data').symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest('Directory symlink creation unavailable')
            with self.assertRaisesRegex(RuntimeError, 'redirected data'):
                storage.migration_plan(root)


if __name__ == '__main__':
    unittest.main()
