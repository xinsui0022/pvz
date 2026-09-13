"""V4.0.3: witnessed boss ice, one-use rescue and local lethal-plant reach.

Serialized IZ-only Challenge fields: A0 completion gate (1 waiting, 2 witnessed,
3 dispatched, 4 sunflower only), A4 rescue marker. Zamboni 134/138 tag provenance and stage.
"""
import struct
from v4_1_fixes import GRACE_MAGIC

ICE_MAGIC = 0x33495a49
RESCUE_MAGIC = 0x33525a49


def add_v4_3(emit, patch, asm):
    initialize = emit('iz_challenge_state_init', '''
        pushfd
        pushad
        mov eax, dword ptr [edi]
        cmp dword ptr [eax+0x7f8], 61
        jb done
        cmp dword ptr [eax+0x7f8], 70
        ja done
        xor eax, eax
        mov dword ptr [edi+0x90], eax
        mov dword ptr [edi+0x94], eax
        mov dword ptr [edi+0x98], eax
        mov dword ptr [edi+0x9c], eax
        mov dword ptr [edi+0xa0], eax
        mov dword ptr [edi+0xa4], eax
    done:
        popad
        popfd
        push 0x36
        lea eax, [edi+0x14]
        jmp 0x41f21d
    ''')
    patch(0x41f218, asm(f'jmp {initialize}', 0x41f218), 5)
    text = '触发恢复机制，恢复5000阳光，最后一次恢复'.encode('gbk')
    label = emit('rescue_label', '.byte ' + ','.join(map(str, text+b'\0')))
    # MSVC string layout: allocator, 16-byte union, size, capacity. Read-only
    # input to SetLabel, which translates/copies it into its own owned string.
    string = struct.pack('<7I', 0, label, 0, 0, 0, len(text), len(text))
    string_va = emit('rescue_string', '.byte '+','.join(map(str, string)))
    recovery = emit('sun_rescue_once', f'''
        pushfd
        pushad
        mov eax, dword ptr [ebp]
        cmp dword ptr [eax+0x7f8], 61
        jb done
        cmp dword ptr [eax+0x7f8], 70
        ja done
        mov ebx, dword ptr [ebp+4]
        cmp byte ptr [ebx+0x164], 0
        jne done
        cmp dword ptr [ebp+0xa4], {RESCUE_MAGIC}
        je done
        cmp dword ptr [ebx+0x5560], 25
        jg done
        sub esp, 4
        mov dword ptr [esp], 0
    rescue_scan:
        mov edx, ebx
        mov esi, esp
        call 0x41c8f0
        test al, al
        jz rescue_empty
        mov eax, dword ptr [esp]
        cmp dword ptr [eax+0xc8], 0
        jle rescue_scan
        mov edx, dword ptr [eax+0x28]
        dec edx
        cmp edx, 2
        jbe rescue_scan
        add esp, 4
        jmp done
    rescue_empty:
        add esp, 4
        mov dword ptr [ebp+0xa4], {RESCUE_MAGIC}
        add dword ptr [ebx+0x5560], 5000
        mov esi, dword ptr [ebx+0x140]
        test esi, esi
        jz done
        mov edi, esp
        sub esp, 528
        and esp, -16
        fxsave [esp]
        fninit
        mov edx, {string_va}
        mov ecx, 7
        call 0x459010
        fxrstor [esp]
        mov esp, edi
    done:
        popad
        popfd
        ret
    ''')

    spawn = emit('boss_ice_provenance', f'''
        pushfd
        pushad
        mov edx, dword ptr [esi]
        cmp dword ptr [edx+0x7f8], 70
        jne done
        cmp dword ptr [eax+0x24], 12
        jne done
        mov edx, dword ptr [esi+4]
        mov edx, dword ptr [edx+0x160]
        cmp dword ptr [edx+0x60], 5
        jne done
        cmp dword ptr [edx+0x90], {GRACE_MAGIC}
        jne done
        cmp dword ptr [edx+0xa0], 1
        jne done
        mov dword ptr [eax+0x134], {ICE_MAGIC}
        mov ecx, dword ptr [edx+0x6c]
        mov dword ptr [eax+0x138], ecx
    done:
        popad
        popfd
        fld dword ptr [0x679fe4]
        jmp 0x534e22
    ''')
    patch(0x534e1c, asm(f'jmp {spawn}', 0x534e1c), 6)
    witness = emit('boss_ice_full_lane', f'''
        pushfd
        pushad
        cmp eax, 25
        jg done
        cmp dword ptr [esi+0x134], {ICE_MAGIC}
        jne done
        cmp byte ptr [esi+0xec], 0
        jne done
        cmp dword ptr [esi+0xc8], 0
        jle done
        mov ecx, dword ptr [esi]
        cmp dword ptr [ecx+0x7f8], 70
        jne done
        mov ecx, dword ptr [edx+0x160]
        cmp dword ptr [ecx+0x90], {GRACE_MAGIC}
        jne done
        cmp dword ptr [ecx+0x60], 5
        jne done
        mov ebx, dword ptr [esi+0x138]
        cmp ebx, dword ptr [ecx+0x6c]
        jne done
        cmp dword ptr [ecx+0xa0], 1
        jne done
        mov dword ptr [ecx+0xa0], 2
    done:
        popad
        popfd
        mov ecx, dword ptr [esi+0x1c]
        cmp eax, dword ptr [edx+ecx*4+0x60c]
        jmp 0x52a897
    ''')
    patch(0x52a88d, asm(f'jmp {witness}', 0x52a88d), 10)

    # Keep all native overlap/row/state predicates; this extra upper bound
    # prevents a lethal plant reaching a leader two columns away. Use the
    # original plant column even after a squash has moved to its landing X.
    reach = emit('dancer_lethal_reach', '''
        push ecx
        push edx
        xor eax, eax
        cmp dword ptr [esi+0x24], 8
        jne done
        mov ecx, dword ptr [edi]
        cmp dword ptr [ecx+0x7f8], 61
        jb done
        cmp dword ptr [ecx+0x7f8], 70
        ja done
        mov ecx, dword ptr [edi+0x24]
        cmp ecx, 4
        je check
        cmp ecx, 6
        je check
        cmp ecx, 17
        jne done
    check:
        mov ecx, dword ptr [edi+0x28]
        imul ecx, ecx, 80
        add ecx, 200
        mov edx, dword ptr [esi+8]
        add edx, 36
        cmp edx, ecx
        setge al
    done:
        pop edx
        pop ecx
        ret
    ''')
    for name, site, length, setup, replay, resume, reject in (
        ('target',0x467657,9,'','mov eax, dword ptr [edi]; cmp dword ptr [eax+0x7f8], 26',0x467660,0x467884),
        ('squash_target',0x460829,6,'mov esi, ebx; mov edi, ebp','mov eax, dword ptr [ebx+0x1c]; sub eax, dword ptr [ebp+0x1c]',0x46082f,0x46099f),
        ('squash_damage',0x460739,6,'','mov eax, dword ptr [esi+0x1c]; sub eax, dword ptr [edi+0x1c]',0x46073f,0x4607bb)):
        hook = emit('dancer_reach_'+name, f'''
            pushfd
            pushad
            {setup}
            call {reach}
            test eax, eax
            jz original
            popad
            popfd
            jmp {reject}
        original:
            popad
            popfd
            {replay}
            jmp {resume}
        ''')
        patch(site, asm(f'jmp {hook}', site), length)
    return recovery
