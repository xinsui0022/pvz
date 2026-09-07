import json
import sys
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from patch_game import transform, bundled_partner, partner_files

class DistributionTests(unittest.TestCase):
    def test_round_trip_is_byte_exact(self):
        p=json.loads((ROOT/'patches/izombie-fixes.json').read_text())
        original=(ROOT/'backups/PlantsVsZombies.original.exe').read_bytes()
        patched=(ROOT/'backups/PlantsVsZombies.patched.exe').read_bytes()
        self.assertEqual(transform(original,p),patched)
        self.assertEqual(transform(patched,p,restore=True),original)

    def test_corruption_rejected(self):
        p=json.loads((ROOT/'patches/izombie-fixes.json').read_text())
        with self.assertRaises(ValueError): transform(b'unsupported',p)

    def test_partner_pair_install_restore_idempotence(self):
        bundled=bundled_partner(ROOT)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'properties').mkdir()
            originals={name:(ROOT/'backups/steam-partner'/name).read_bytes() for name in bundled}
            for name,data in originals.items(): (root/'properties'/name).write_bytes(data)
            with patch('patch_game.bundled_partner',return_value=bundled):
                self.assertEqual(partner_files(root,check=True),2)
                self.assertEqual(partner_files(root),2)
                self.assertEqual(partner_files(root),0)
                for name,value in bundled.items():
                    self.assertEqual((root/'properties'/name).read_bytes(),value)
                    self.assertEqual((root/'backups/steam-partner'/name).read_bytes(),originals[name])
                partner_files(root,restore=True)
                for name,value in originals.items(): self.assertEqual((root/'properties'/name).read_bytes(),value)

    def test_partner_unknown_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'properties').mkdir()
            active=root/'properties/partner.xml';active.write_bytes(b'user edited')
            with patch('patch_game.bundled_partner',return_value=bundled_partner(ROOT)):
                with self.assertRaises(ValueError): partner_files(root)
            self.assertEqual(active.read_bytes(),b'user edited')

if __name__=='__main__': unittest.main()
