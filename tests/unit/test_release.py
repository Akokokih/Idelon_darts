from pathlib import Path
import tempfile
import unittest
import zipfile
from tools.build_release import build_release


class ReleaseTests(unittest.TestCase):
    def project(self, path):
        (path/'src/idleon_darts').mkdir(parents=True)
        (path/'src/idleon_darts/__init__.py').write_text('')
        (path/'README.md').write_text('test')
        (path/'pyproject.toml').write_text('[project]\nname="synthetic"')

    def test_only_allowlisted_files_packaged_private_sibling_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root/'project'
            self.project(project)
            (root/'private').mkdir()
            (root/'private/capture.py').write_text('private')
            (root/'private/shot.png').write_bytes(b'private')
            (project/'notes.txt').write_text('unlisted')
            archive = root/'release.zip'
            build_release(project, archive)
            with zipfile.ZipFile(archive) as z:
                names = z.namelist()
                self.assertEqual(z.testzip(), None)
                self.assertEqual(len(names), 3)
                self.assertFalse(any('private' in n or 'notes' in n for n in names))

    def test_private_files_inside_project_reject_build(self):
        for relative in ['sessions/metadata.json', 'work/capture.py',
                         'src/idleon_darts/shot.png', 'capture.py', 'dataset/raw.jsonl']:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                project = root/'project'
                self.project(project)
                p = project/relative
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('must not ship')
                with self.assertRaises(ValueError):
                    build_release(project, root/'release.zip')

    def test_symbolic_link_rejected_even_when_not_allowlisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root/'project'
            self.project(project)
            (root/'secret').write_text('private')
            (project/'linked').symlink_to(root/'secret')
            with self.assertRaises(ValueError):
                build_release(project, root/'release.zip')
