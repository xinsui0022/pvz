"""Build a version-locked, reversible patch; no original game bytes distributed.

The x86 ABI here was checked against the user's 1.0.0.1051 executable.
Reference reconstruction is documentation only; we do not compile it.
"""
import argparse
import base64
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.tools'))
import pefile
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from additional_fixes import add_fixes
from progression_fixes import add_progression
from multi_boss_fixes import add_multi_boss
from tactical_fixes import add_tactical
from v3_fixes import add_v3

ORIGINAL_SHA256 = '343c8edef1687a742b3420fba6d69c82b6b7baeca32a28bd365bdbb7b6d94dbb'
BASE = 0x400000
ks = Ks(KS_ARCH_X86, KS_MODE_32)

def asm(source, va):
    return bytes(ks.asm(source, va)[0])

def sha(data):
    return hashlib.sha256(data).hexdigest()

def align(n, a):
    return (n + a - 1) // a * a

def build(original):
    if sha(original) != ORIGINAL_SHA256:
        raise ValueError('Unsupported executable SHA-256; refusing to patch.')
    pe = pefile.PE(data=original)
    data = bytearray(original)
    section_va = BASE + align(pe.OPTIONAL_HEADER.SizeOfImage, 0x1000)
    section_offset = align(len(data), pe.OPTIONAL_HEADER.FileAlignment)
    code = bytearray()
    symbols = {}
    changes = []

    def emit(name, source):
        code.extend(b'\xCC' * (align(len(code), 16) - len(code)))
        va = section_va + len(code)
        symbols[name] = va
        code.extend(asm(source, va))
        return va

    def patch(va, replacement, size=None):
        if size is not None:
            assert len(replacement) <= size
            replacement += b'\x90' * (size-len(replacement))
        offset = pe.get_offset_from_rva(va - BASE)
        changes.append({'va': hex(va), 'length': len(replacement)})
        data[offset:offset+len(replacement)] = replacement

    # ECX must contain LawnApp*, not Zombie*. Preserve the real boss level
    # behavior, and clean only this boss in I, Zombie. Never kill its allies.
    boss = emit('boss_die', '''
        pushfd
        pushad
        mov edi, ecx
        mov ecx, dword ptr [edi]
        call 0x4539d0
        test al, al
        jnz final_boss
        mov eax, dword ptr [edi]
        call 0x4537d0
        test al, al
        jz mark_dead
        cmp dword ptr [edi+0x6c], -2
        je done
        cmp dword ptr [edi+0x6c], -3
        je done
        mov edx, dword ptr [edi+0x140]
        mov dword ptr [edi+0x140], 0
        test edx, edx
        jz clear_cold
        mov eax, dword ptr [edi]
        call 0x453cf0
    clear_cold:
        mov eax, edi
        call 0x532b40
    mark_dead:
        mov byte ptr [edi+0xec], 1
    done:
        popad
        popfd
        ret
    final_boss:
        popad
        popfd
        push ebp
        mov ebp, esp
        and esp, -8
        jmp 0x5366d6
    ''')
    patch(0x651213, asm(f'jmp {boss}', 0x651213), 5)

    # Also make the original predicate safe during profile teardown.
    predicate = emit('is_final_boss', '''
        cmp dword ptr [ecx+0x768], 0
        je no
        mov eax, dword ptr [ecx+0x7f8]
        cmp eax, 0x23
        je yes
        test eax, eax
        jne no
        mov eax, dword ptr [ecx+0x82c]
        test eax, eax
        je no
        cmp dword ptr [eax+0x24], 50
        jne no
    yes:
        mov al, 1
        ret
    no:
        xor al, al
        ret
    ''')
    patch(0x4539d0, asm(f'jmp {predicate}', 0x4539d0), 7)

    # Called with the original Plant::Die stack argument still in place.
    # Tail-jump preserves its callee-popped argument and return address.
    jack = emit('jack_sun', '''
        pushfd
        pushad
        cmp byte ptr [esi+0x141], 0
        jne done
        cmp dword ptr [esi+0x40], 0
        jle done
        mov eax, dword ptr [esi]
        call 0x4537d0
        test al, al
        jz done
        mov eax, dword ptr [esi+4]
        push dword ptr [eax+0x160]
        call 0x42b9d0
    done:
        popad
        popfd
        jmp 0x4679b0
    ''')
    patch(0x41cc39, asm(f'call {jack}', 0x41cc39))

    # Permit only the three grounded water-zombie phases, only in I, Zombie,
    # and only if a live brain is actually in attack range. Then continue
    # original height/head/kelp/flying/cold/cadence/target checks.
    water = emit('water_brain_gate', '''
        mov eax, dword ptr [edi+0x28]
        cmp eax, 0x33
        je candidate
        cmp eax, 0x38
        je candidate
        cmp eax, 0x39
        jne original
    candidate:
        pushad
        mov eax, dword ptr [edi]
        call 0x4537d0
        test al, al
        jz reject
        mov eax, dword ptr [edi+4]
        push dword ptr [eax+0x160]
        mov eax, edi
        call 0x42b810
        test eax, eax
        jz reject
        popad
        jmp 0x52f5eb
    reject:
        popad
    original:
        mov eax, dword ptr [edi+0x28]
        cmp eax, 0xc
        jmp 0x52f528
    ''')
    patch(0x52f522, asm(f'jmp {water}', 0x52f522), 6)

    fireball = emit('fireball_brain', '''
        pushfd
        pushad
        mov eax, dword ptr [ebx]
        call 0x4537d0
        test al, al
        jz done
        cmp dword ptr [ebx+0x140], 0
        je done
        push 0xc25c0000
        fld dword ptr [esi+0x2c]
        fcomp dword ptr [esp]
        add esp, 4
        fnstsw ax
        test ah, 4
        jnz done
        test ah, 0x41
        jz done
        mov edx, dword ptr [ebx+4]
        mov edi, dword ptr [ebx+0x148]
        cmp edi, 5
        jae done
        mov ebp, dword ptr [edx+0x160]
        xor ebx, ebx
        push 0xc
        call 0x408e40
        test eax, eax
        jz done
        cmp dword ptr [eax+0xc], 0x1d
        je done
        push ebp
        call 0x42ba30
    done:
        popad
        popfd
        xor edi, edi
        mov ebp, 0xffff0000
        jmp 0x535d4f
    ''')
    patch(0x535d48, asm(f'jmp {fireball}', 0x535d48), 7)

    add_fixes(emit, patch, asm, symbols)
    add_progression(emit, patch, asm)
    add_multi_boss(emit, patch, asm)
    add_tactical(emit, patch, asm)
    add_v3(emit, patch, asm)

    # Existing footer buffer: GBK, NUL-terminated, 71 bytes plus terminator.
    # Reuse the same pointer/layout; pad the unused tail with NUL bytes.
    caption = '由心都灬碎了提供，QQ：3389141'.encode('gbk')
    assert len(caption) < 72
    patch(0x65124a, caption + b'\0' * (72-len(caption)))

    # Explicit executable section, rather than depending on unmapped padding.
    header = pe.sections[-1].get_file_offset() + 40
    assert header + 40 <= pe.OPTIONAL_HEADER.SizeOfHeaders
    # Unused header padding contains the six-byte marker "ax!TQE".
    # No data directory refers here; the entire input is hash-locked.
    assert data[header:header+40] == b'\0'*16 + b'ax!TQE' + b'\0'*18
    raw_size = align(len(code), pe.OPTIONAL_HEADER.FileAlignment)
    data[header:header+40] = struct.pack('<8sIIIIIIHHI', b'.izfix\0\0',
        len(code), section_va-BASE, raw_size, section_offset, 0, 0, 0, 0, 0x60000020)
    struct.pack_into('<H', data, pe.FILE_HEADER.get_field_absolute_offset('NumberOfSections'), len(pe.sections)+1)
    struct.pack_into('<I', data, pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'),
                     align(section_va-BASE+len(code), 0x1000))
    struct.pack_into('<I', data, pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfCode'),
                     pe.OPTIONAL_HEADER.SizeOfCode+raw_size)
    # The supplied modified executable's certificate is already invalid. Keep
    # its bytes for reversibility, but do not advertise a stale signature.
    security = pe.OPTIONAL_HEADER.DATA_DIRECTORY[4].get_file_offset()
    data[security:security+8] = b'\0'*8
    data.extend(b'\0'*(section_offset-len(data)))
    data.extend(code)
    data.extend(b'\0'*(raw_size-len(code)))
    updated = pefile.PE(data=bytes(data))
    struct.pack_into('<I', data, updated.OPTIONAL_HEADER.get_field_absolute_offset('CheckSum'), updated.generate_checksum())
    return bytes(data), {'original_sha256': ORIGINAL_SHA256, 'patched_sha256': sha(data),
        'symbols': {k: hex(v) for k,v in symbols.items()}, 'hooks': changes,
        'code_bytes': len(code)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT/'backups/PlantsVsZombies.original.exe')
    parser.add_argument('--output', type=Path, default=ROOT/'backups/PlantsVsZombies.patched.exe')
    args = parser.parse_args()
    patched, manifest = build(args.input.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    (ROOT/'patches').mkdir(exist_ok=True)
    (ROOT/'patches/manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    original = args.input.read_bytes()
    changes=[]
    i=0
    while i<len(patched):
        if i<len(original) and original[i]==patched[i]:
            i+=1
            continue
        start=i
        while i<len(patched) and (i>=len(original) or original[i]!=patched[i]): i+=1
        changes.append({'offset':start,
            'before':base64.b64encode(original[start:i]).decode(),
            'after':base64.b64encode(patched[start:i]).decode()})
    package={k:manifest[k] for k in ('original_sha256','patched_sha256')}
    package.update(original_size=len(original),patched_size=len(patched),changes=changes)
    (ROOT/'patches/izombie-fixes.json').write_text(json.dumps(package,indent=2)+'\n')
    print(json.dumps(manifest, indent=2))

if __name__ == '__main__':
    main()
