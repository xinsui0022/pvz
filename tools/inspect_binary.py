"""Local analysis helper (not needed by the game)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.tools'))
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

path = sys.argv[1]
pe = pefile.PE(path)
base = pe.OPTIONAL_HEADER.ImageBase
md = Cs(CS_ARCH_X86, CS_MODE_32)
if len(sys.argv) > 2:
    start, end = (int(s, 16) for s in sys.argv[2:4])
    for ins in md.disasm(pe.get_data(start-base, end-start), start):
        print(f'{ins.address:08x}  {ins.bytes.hex():24} {ins.mnemonic:8} {ins.op_str}')
else:
    print('Entry', hex(base+pe.OPTIONAL_HEADER.AddressOfEntryPoint))
    for sec in pe.sections:
        print(sec.Name, hex(base+sec.VirtualAddress), hex(sec.Misc_VirtualSize))
    for item in getattr(pe, 'DIRECTORY_ENTRY_EXPORT', []).symbols:
        print(hex(base+item.address), item.name)
