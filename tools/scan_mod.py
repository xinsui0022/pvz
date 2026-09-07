import sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.tools'))
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
p=pefile.PE('gdi42.dll'); md=Cs(CS_ARCH_X86,CS_MODE_32)
lines=[]
for i in md.disasm(p.sections[0].get_data(),0x10001000):
    lines.append(f'{i.address:08x} {i.mnemonic:8} {i.op_str}')
Path('.tools/mod-disasm.txt').write_text('\n'.join(lines))
b=Path('gdi42.dll').read_bytes()
for m in re.finditer(rb'[\x20-\x7e]{8,}',b):
    s=m.group().decode()
    if any(x in s.lower() for x in ['pvz','zombie','pdb','virtual','writeprocess','hook']):print(hex(m.start()),s)
