from pathlib import Path
from tempfile import TemporaryDirectory
import unittest,zipfile
from tools.package_windows import package_windows


class WindowsPackageTests(unittest.TestCase):
    def test_self_contained_bundle_has_launcher_guide_and_no_sibling_data(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);bundle=root/'app';(bundle/'_internal').mkdir(parents=True)
            (bundle/'IdleonDarts.exe').write_bytes(b'synthetic executable')
            (bundle/'_internal/python312.dll').write_bytes(b'synthetic runtime')
            (root/'profiles').mkdir();(root/'profiles/private.json').write_text('private')
            result=package_windows(bundle,root/'release.zip','0.6.0')
            with zipfile.ZipFile(result['archive']) as archive:
                self.assertEqual(archive.testzip(),None)
                self.assertEqual(len(archive.namelist()),4)
                self.assertIn('--data-dir',archive.read('IdleonDarts-0.6.0/Lancer.cmd').decode())
                self.assertNotIn('private',str(archive.namelist()))
            with self.assertRaises(FileExistsError):package_windows(bundle,root/'release.zip','0.6.0')

    def test_private_capture_directory_in_bundle_is_rejected(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);bundle=root/'app';(bundle/'_internal').mkdir(parents=True)
            (bundle/'IdleonDarts.exe').write_bytes(b'exe');(bundle/'captures').mkdir()
            with self.assertRaises(ValueError):package_windows(bundle,root/'bad.zip')
