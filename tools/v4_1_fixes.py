"""Playable completion grace period. Challenge cloud counters are serialized
and unused in I, Zombie: +90 marker, +94 remaining ticks, +98 final brain row.
No award/end flag is set until the grace period finishes, so input stays live.
"""

GRACE_MAGIC = 0x31475a49


def add_v4_1(emit, patch, asm, reward_once, recovery, boss_tick):
    gate = emit('completion_grace_start', f'''
        call {reward_once}
        pushfd
        pushad
        sub esp, 4
        mov ebp, ecx
        mov eax, dword ptr [ebp]
        cmp dword ptr [eax+0x7f8], 70
        jne original
        cmp dword ptr [ebp+0x60], 5
        jne original
        cmp dword ptr [ebp+0x90], {GRACE_MAGIC}
        je waiting
        mov dword ptr [ebp+0x94], 0
        mov dword ptr [ebp+0xa0], 0
        mov dword ptr [esp], 0
    plant:
        mov edx, dword ptr [ebp+4]
        mov esi, esp
        call 0x41c950
        test al, al
        jz scan_zombies
        mov eax, dword ptr [esp]
        cmp dword ptr [eax+0x24], 1
        jne plant
        cmp byte ptr [eax+0x142], 0
        jne plant
        cmp byte ptr [eax+0x144], 0
        je plant
        cmp dword ptr [eax+0x40], 0
        jle plant
        mov dword ptr [ebp+0x94], 2000
        jmp scan_zombies
    scan_zombies:
        mov dword ptr [esp], 0
    zombie:
        mov edx, dword ptr [ebp+4]
        mov esi, esp
        call 0x41c8f0
        test al, al
        jz scanned
        mov eax, dword ptr [esp]
        cmp dword ptr [eax+0x24], 25
        jne zombie
        cmp dword ptr [eax+0xc8], 0
        jle zombie
        mov edx, dword ptr [eax+0x28]
        dec edx
        cmp edx, 2
        jbe zombie
        mov dword ptr [ebp+0xa0], 1
    scanned:
        cmp dword ptr [ebp+0xa0], 1
        je arm
        cmp dword ptr [ebp+0x94], 0
        je original
    arm:
        cmp dword ptr [ebp+0xa0], 1
        je armed
        mov dword ptr [ebp+0xa0], 4
    armed:
        mov dword ptr [ebp+0x90], {GRACE_MAGIC}
        mov eax, dword ptr [esp+44]
        mov dword ptr [ebp+0x98], eax
    waiting:
        add esp, 4
        popad
        popfd
        ret 4
    original:
        add esp, 4
        popad
        popfd
        jmp 0x429980
    ''')
    patch(0x42b90d, asm(f'call {gate}', 0x42b90d), 5)

    tick = emit('completion_grace_tick', f'''
        pushfd
        pushad
        mov ebp, dword ptr [esp+40]
        call {boss_tick}
        call {recovery}
        mov eax, dword ptr [ebp]
        cmp dword ptr [eax+0x7f8], 70
        jne done
        mov eax, dword ptr [ebp+4]
        cmp byte ptr [eax+0x164], 0
        jne done
        cmp dword ptr [ebp+0x90], {GRACE_MAGIC}
        jne done
        cmp dword ptr [ebp+0x60], 5
        jne reset
        # V4.0.2 serialized the same timer but did not record the ice gate.
        cmp dword ptr [ebp+0xa0], 0
        jne timer
        mov dword ptr [ebp+0xa0], 1
    timer:
        cmp dword ptr [ebp+0x94], 0
        jle boss_wait
        dec dword ptr [ebp+0x94]
        jnz done
    boss_wait:
        cmp dword ptr [ebp+0xa0], 1
        jne dispatch
        # If every boss and its pending car have died, there is no remaining
        # actor capable of completing the ice lane. Do not strand a won game.
        sub esp, 4
        mov dword ptr [esp], 0
    pending:
        mov edx, dword ptr [ebp+4]
        mov esi, esp
        call 0x41c8f0
        test al, al
        jz no_pending
        mov eax, dword ptr [esp]
        cmp dword ptr [eax+0xc8], 0
        jle pending
        mov edx, dword ptr [eax+0x28]
        dec edx
        cmp edx, 2
        jbe pending
        cmp dword ptr [eax+0x24], 25
        je keep_waiting
        cmp dword ptr [eax+0x24], 12
        jne pending
        cmp dword ptr [eax+0x134], 0x33495a49
        jne pending
        mov edx, dword ptr [eax+0x138]
        cmp edx, dword ptr [ebp+0x6c]
        jne pending
    keep_waiting:
        add esp, 4
        jmp done
    no_pending:
        add esp, 4
        mov dword ptr [ebp+0xa0], 2
    dispatch:
        cmp dword ptr [ebp+0xa0], 3
        je done
        mov dword ptr [ebp+0xa0], 3
        mov esi, ebp
        mov ebp, esp
        sub esp, 528
        and esp, -16
        fxsave [esp]
        fninit
        push dword ptr [esi+0x98]
        mov ecx, esi
        xor eax, eax
        call 0x429980
        fxrstor [esp]
        mov esp, ebp
        jmp done
    reset:
        mov dword ptr [ebp+0x90], 0
        mov dword ptr [ebp+0x94], 0
        mov dword ptr [ebp+0xa0], 0
    done:
        popad
        popfd
        push ecx
        push ebx
        push ebp
        mov ebp, dword ptr [esp+16]
        jmp 0x42b347
    ''')
    patch(0x42b340, asm(f'jmp {tick}', 0x42b340), 7)

    # Once the playable grace has elapsed, do not add the native five seconds.
    end = emit('completion_grace_transition', f'''
        mov dword ptr [edi+0x5604], 500
        pushfd
        push eax
        mov eax, dword ptr [edi+0x160]
        cmp dword ptr [eax+0x90], {GRACE_MAGIC}
        jne done
        cmp dword ptr [eax+0x94], 0
        jne done
        mov dword ptr [edi+0x5604], 1
    done:
        pop eax
        popfd
        jmp 0x40c7e9
    ''')
    patch(0x40c7df, asm(f'jmp {end}', 0x40c7df), 10)

    # Completing all brains is already a win. A boss dying during the grace
    # must not turn it into a loss when the wallet and zombie count are low.
    defeat = emit('completion_grace_no_defeat', f'''
        mov ecx, dword ptr [ebp]
        cmp dword ptr [ecx+0x7f8], 70
        jne original
        cmp dword ptr [ebp+0x60], 5
        jne original
        cmp dword ptr [ebp+0x90], {GRACE_MAGIC}
        je 0x42b526
    original:
        mov edx, dword ptr [ecx+0x768]
        jmp 0x42b4aa
    ''')
    patch(0x42b4a1, asm(f'jmp {defeat}', 0x42b4a1), 9)
