"""V5 single-boss credit, reversible current-track music and ice-wait UX.

IZ-only serialized Challenge storage: 78 magic, 7C deferred draws remaining,
80 music owned, 84 previous tune, 88 music stage, 8C advice refresh ticks.
Native Challenge construction zeros these six otherwise-unused cloud IDs.
"""
import struct
from v4_1_fixes import GRACE_MAGIC
from v4_3_fixes import ICE_MAGIC

V5_MAGIC = 0x35565a49


def add_v5(emit, patch, asm, symbols):
    init = emit('v5_state_init', f'''
        cmp dword ptr [ebp+0x78], {V5_MAGIC}
        je done
        mov dword ptr [ebp+0x78], {V5_MAGIC}
        mov dword ptr [ebp+0x7c], 0
        mov dword ptr [ebp+0x80], 0
        mov dword ptr [ebp+0x84], -1
        mov dword ptr [ebp+0x88], -1
        mov dword ptr [ebp+0x8c], 0
    done:
        ret
    ''')
    scan = emit('v5_live_boss_and_car', f'''
        push ebx
        push ecx
        push esi
        push edi
        sub esp, 12
        mov dword ptr [esp], 0
        mov dword ptr [esp+4], 0
        mov dword ptr [esp+8], 0
    next:
        mov edx, dword ptr [ebp+4]
        mov esi, esp
        call 0x41c8f0
        test al, al
        jz done
        mov eax, dword ptr [esp]
        cmp dword ptr [eax+0xc8], 0
        jle next
        mov ecx, dword ptr [eax+0x28]
        dec ecx
        cmp ecx, 2
        jbe next
        cmp dword ptr [eax+0x24], 25
        jne car
        cmp dword ptr [esp+4], 0
        jne next
        mov dword ptr [esp+4], eax
        jmp next
    car:
        cmp dword ptr [eax+0x24], 12
        jne next
        cmp dword ptr [eax+0x134], {ICE_MAGIC}
        jne next
        mov ecx, dword ptr [ebp+0x6c]
        cmp ecx, dword ptr [eax+0x138]
        jne next
        mov dword ptr [esp+8], 1
        jmp next
    done:
        mov eax, dword ptr [esp+4]
        mov edx, dword ptr [esp+8]
        add esp, 12
        pop edi
        pop esi
        pop ecx
        pop ebx
        ret
    ''')
    random = emit('v5_single_boss_random', f'''
        push ebp
        push edi
        push esi
        push ecx
        push edx
        call {symbols['weighted_random']}
        mov edi, eax
        mov eax, dword ptr [ebx]
        cmp dword ptr [eax+0x7f8], 61
        jb result
        cmp dword ptr [eax+0x7f8], 70
        ja result
        mov eax, dword ptr [ebx+4]
        mov ebp, dword ptr [eax+0x160]
        call {init}
        call {scan}
        test eax, eax
        jz available
        cmp edi, 25
        jne result
        cmp dword ptr [ebp+0x7c], 0
        jne replacement
        mov dword ptr [ebp+0x7c], 5
    replacement:
        mov eax, 32
        call 0x5af400
        cmp eax, 25
        jb nonboss
        inc eax
    nonboss:
        mov edi, eax
        jmp result
    available:
        cmp edi, 25
        je paid
        cmp dword ptr [ebp+0x7c], 0
        je result
        dec dword ptr [ebp+0x7c]
        jnz result
        mov edi, 25
    paid:
        mov dword ptr [ebp+0x7c], 0
    result:
        mov eax, edi
        pop edx
        pop ecx
        pop esi
        pop edi
        pop ebp
        ret
    ''')
    patch(0x6510e9, asm(f'call {random}', 0x6510e9), 5)

    # EBP=Challenge. Restore the actual pre-boss tune, including NONE. No
    # mode-derived default; a trainer's current tune is captured as-is.
    restore = emit('v5_restore_music', '''
        pushfd
        pushad
        cmp dword ptr [ebp+0x80], 1
        jne done
        mov eax, dword ptr [ebp]
        mov esi, dword ptr [eax+0x83c]
        test esi, esi
        jz done
        mov dword ptr [ebp+0x80], 0
        mov edi, esp
        sub esp, 528
        and esp, -16
        fxsave [esp]
        fninit
        call 0x45abb0
        mov ecx, dword ptr [ebp+0x84]
        cmp ecx, -1
        je restored
        mov eax, -1
        mov edx, -1
        call 0x45adb0
    restored:
        fxrstor [esp]
        mov esp, edi
    done:
        popad
        popfd
        ret
    ''')
    text = '正在等待冰车僵尸'.encode('gbk')
    label = emit('v5_wait_label', '.byte '+','.join(map(str,text+b'\0')))
    raw = struct.pack('<7I',0,label,0,0,0,len(text),len(text))
    string = emit('v5_wait_string','.byte '+','.join(map(str,raw)))
    # Music and advice engine calls may use floating point. Save caller state
    # once around the whole routine; array traversal itself is integer-only.
    tick = emit('v5_boss_tick', f'''
        pushfd
        pushad
        mov eax, dword ptr [ebp]
        cmp dword ptr [eax+0x7f8], 61
        jb done
        cmp dword ptr [eax+0x7f8], 70
        ja done
        mov eax, dword ptr [ebp+4]
        cmp byte ptr [eax+0x164], 0
        jne done
        call {init}
        mov edi, esp
        sub esp, 528
        and esp, -16
        fxsave [esp]
        fninit
        push edi
        call {scan}
        mov ebx, eax
        push edx
        test ebx, ebx
        jz restore
        # Normalize older multi-boss saves, retaining the first living boss
        # and one deferred credit. Never touch non-boss allies.
        sub esp, 4
        mov dword ptr [esp], 0
    duplicate:
        mov edx, dword ptr [ebp+4]
        mov esi, esp
        call 0x41c8f0
        test al, al
        jz music
        mov ecx, dword ptr [esp]
        cmp ecx, ebx
        je duplicate
        cmp dword ptr [ecx+0x24], 25
        jne duplicate
        cmp dword ptr [ecx+0xc8], 0
        jle duplicate
        mov eax, dword ptr [ecx+0x28]
        dec eax
        cmp eax, 2
        jbe duplicate
        cmp dword ptr [ebp+0x7c], 0
        jne remove
        mov dword ptr [ebp+0x7c], 5
    remove:
        call {symbols['boss_die']}
        jmp duplicate
    music:
        add esp, 4
        mov eax, dword ptr [ebp]
        mov esi, dword ptr [eax+0x83c]
        test esi, esi
        jz advice
        cmp dword ptr [ebp+0x80], 1
        je playing
        mov eax, dword ptr [esi+8]
        mov dword ptr [ebp+0x84], eax
        mov eax, dword ptr [ebp+0x6c]
        mov dword ptr [ebp+0x88], eax
        mov dword ptr [ebp+0x80], 1
    playing:
        mov eax, esi
        mov edi, 12
        call 0x45b750
        jmp advice
    restore:
        call {restore}
    advice:
        mov eax, dword ptr [ebp]
        cmp dword ptr [eax+0x7f8], 70
        jne clear_advice
        cmp dword ptr [ebp+0x60], 5
        jne clear_advice
        cmp dword ptr [ebp+0x90], {GRACE_MAGIC}
        jne clear_advice
        cmp dword ptr [ebp+0xa0], 1
        jne clear_advice
        test ebx, ebx
        jz show_advice
        # Let ongoing animations finish. Prioritize a new car only while
        # no earlier boss car is still trying to lay its full lane.
        cmp dword ptr [esp], 0
        jne car_in_progress
        cmp dword ptr [ebx+0x114], 50
        jle other_attacks
        mov dword ptr [ebx+0x114], 50
        jmp other_attacks
    car_in_progress:
        mov dword ptr [ebx+0x114], 200
    other_attacks:
        mov dword ptr [ebx+0x134], 1000
        mov dword ptr [ebx+0x138], 1000
        mov dword ptr [ebx+0x13c], 1000
    show_advice:
        cmp dword ptr [ebp+0x8c], 0
        jle show
        dec dword ptr [ebp+0x8c]
        jmp finish
    show:
        mov eax, dword ptr [ebp+4]
        mov esi, dword ptr [eax+0x140]
        test esi, esi
        jz finish
        mov edx, {string}
        mov ecx, 7
        call 0x459010
        mov dword ptr [ebp+0x8c], 400
        jmp finish
    clear_advice:
        cmp dword ptr [ebp+0x8c], 0
        je finish
        mov dword ptr [ebp+0x8c], 0
        mov eax, dword ptr [ebp+4]
        mov esi, dword ptr [eax+0x140]
        test esi, esi
        jz finish
        lea esi, [esi+4]
        mov edi, {label}
        mov ecx, {len(text)+1}
        cld
        repe cmpsb
        jne finish
        mov eax, dword ptr [ebp+4]
        mov eax, dword ptr [eax+0x140]
        mov dword ptr [eax+0x88], 0
    finish:
        add esp, 4
        pop edi
        fxrstor [esp]
        mov esp, edi
    done:
        popad
        popfd
        ret
    ''')
    force_car = emit('v5_prioritize_boss_car', f'''
        pushfd
        push edx
        mov edx, dword ptr [esi]
        cmp dword ptr [edx+0x7f8], 70
        jne done
        mov edx, dword ptr [esi+4]
        mov edx, dword ptr [edx+0x160]
        cmp dword ptr [edx+0x60], 5
        jne done
        cmp dword ptr [edx+0x90], {GRACE_MAGIC}
        jne done
        cmp dword ptr [edx+0xa0], 1
        jne done
        mov eax, 12
    done:
        pop edx
        popfd
        mov ecx, dword ptr [esi+0x130]
        jmp 0x534e10
    ''')
    patch(0x534e0a,asm(f'jmp {force_car}',0x534e0a),6)
    transition = emit('v5_stage_music_restore', f'''
        pushfd
        pushad
        mov ebp, edi
        mov eax, dword ptr [ebp]
        cmp dword ptr [eax+0x7f8], 70
        jne done
        cmp dword ptr [ebp+0x78], {V5_MAGIC}
        jne done
        call {restore}
        mov dword ptr [ebp+0x8c], 0
    done:
        popad
        popfd
        jmp 0x40ca50
    ''')
    patch(0x42a000,asm(f'call {transition}',0x42a000),5)
    return tick
