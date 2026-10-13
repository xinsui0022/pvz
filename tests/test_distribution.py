import json
import sys
import unittest
import tempfile
import os
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from patch_game import transform, bundled_partner, partner_files

class DistributionTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt','Windows image-loader validation')
    def test_windows_loader_accepts_the_candidate_image(self):
        import ctypes
        from ctypes import wintypes
        from build_patch import build
        binary,_=build((ROOT/'backups/PlantsVsZombies.original.exe').read_bytes())
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,
                                    wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        kernel.CreateFileW.restype=wintypes.HANDLE
        kernel.CreateFileMappingW.argtypes=[wintypes.HANDLE,wintypes.LPVOID,wintypes.DWORD,
                                           wintypes.DWORD,wintypes.DWORD,wintypes.LPCWSTR]
        kernel.CreateFileMappingW.restype=wintypes.HANDLE
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        with tempfile.TemporaryDirectory() as directory:
            image=Path(directory)/'candidate.exe'; image.write_bytes(binary)
            file=kernel.CreateFileW(str(image),0x80000000,7,None,3,0x80,None)
            self.assertNotEqual(file,ctypes.c_void_p(-1).value)
            try:
                mapping=kernel.CreateFileMappingW(file,None,0x01000002,0,0,None)
                self.assertTrue(mapping,f'Windows rejected image: {ctypes.get_last_error()}')
                if mapping: kernel.CloseHandle(mapping)
            finally:
                kernel.CloseHandle(file)

    def test_traditional_baseline_remains_byte_exact(self):
        from build_patch import build, sha
        original=(ROOT/'backups/PlantsVsZombies.original.exe').read_bytes()
        baseline,_=build(original,challenge=False)
        self.assertEqual(sha(baseline),'3a43abb5464860f25dbfab7f6850e555bcb3a9939633d28bf36098b1f967c01c')

    def test_selector_data_is_writable_without_writable_code(self):
        from build_patch import build
        import pefile
        binary,manifest=build((ROOT/'backups/PlantsVsZombies.original.exe').read_bytes())
        pe=pefile.PE(data=binary)
        for name in ('iz_challenge_selection_pending','iz_challenge_selection_loading'):
            section=pe.get_section_by_rva(int(manifest['symbols'][name],16)-0x400000)
            self.assertEqual(section.Name.rstrip(b'\0'),b'.izdata')
            self.assertTrue(section.Characteristics & 0x80000000)
            self.assertFalse(section.Characteristics & 0x20000000)
        code=next(s for s in pe.sections if s.Name.rstrip(b'\0')==b'.izfix')
        self.assertFalse(code.Characteristics & 0x80000000)
        data=next(s for s in pe.sections if s.Name.rstrip(b'\0')==b'.izdata')
        self.assertEqual(data.VirtualAddress, code.VirtualAddress +
                         ((code.Misc_VirtualSize+0xfff)//0x1000)*0x1000)

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
