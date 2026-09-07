"""V3 hooks for the supplied 1.0.0.1051 binary (100 logic ticks/second)."""

BOSS_LAST_STAND = 0x31505a49


def add_v3(emit, patch, asm):
    # Init picks a complete bungee target. Skip the mod's later cone-X copy.
    bungee = emit('random_bungee_target', '''
        cmp dword ptr [eax+0x24], 20
        jne original
        push ecx
        mov ecx, dword ptr [eax]
        cmp dword ptr [ecx+0x7f8], 61
        jb restore
        cmp dword ptr [ecx+0x7f8], 70
        ja restore
        pop ecx
        jmp 0x651177
    restore:
        pop ecx
    original:
        mov edx, dword ptr [ebx+0x2c]
        mov dword ptr [eax+0x2c], edx
        jmp 0x651177
    ''')
    patch(0x651171, asm(f'jmp {bungee}', 0x651171), 6)

    ice = emit('izombie_ice_trail', '''
        push ecx
        mov ecx, dword ptr [esi]
        cmp dword ptr [ecx+0x7f8], 61
        jb normal
        cmp dword ptr [ecx+0x7f8], 70
        ja normal
        mov dword ptr [eax+edx*4+0x624], 4500
        jmp done
    normal:
        mov dword ptr [eax+edx*4+0x624], 3000
    done:
        pop ecx
        jmp 0x52a8ba
    ''')
    patch(0x52a8af, asm(f'jmp {ice}', 0x52a8af), 11)

    # Eating starts the native jump. Defer brain damage until impact.
    squash_eat = emit('squash_head_brain', '''
        mov eax, edi
        call 0x52f250
        cmp dword ptr [edi+0x24], 30
        jne original
        push eax
        mov eax, dword ptr [edi]
        cmp dword ptr [eax+0x7f8], 61
        jb restore
        cmp dword ptr [eax+0x7f8], 70
        ja restore
        pop eax
        jmp 0x42b9c2
    restore:
        pop eax
    original:
        jmp 0x42b996
    ''')
    patch(0x42b98f, asm(f'jmp {squash_eat}', 0x42b98f), 7)

    # GetBrainTarget checks row/range and excludes an already squished brain.
    # EAX is SquishBrain's GridItem argument; its Challenge is on the stack.
    squash_hit = emit('squash_head_brain_impact', '''
        pushfd
        pushad
        mov eax, dword ptr [edi]
        call 0x4537d0
        test al, al
        jz done
        mov eax, dword ptr [edi+4]
        mov ebp, dword ptr [eax+0x160]
        push ebp
        mov eax, edi
        call 0x42b810
        test eax, eax
        jz done
        push ebp
        call 0x42ba30
    done:
        popad
        popfd
        jmp 0x52e920
    ''')
    patch(0x527e2e, asm(f'call {squash_hit}', 0x527e2e), 5)

    for site in (0x527c26, 0x527db2):
        tail = ('mov edx, dword ptr [ebp]; mov eax, dword ptr [edx+0x820]'
                if site == 0x527c26 else 'fld dword ptr [ebp+0x30]; mov eax, dword ptr [ebp]')
        size = 9 if site == 0x527c26 else 6
        target = emit(f'squash_brain_aim_{site:x}', f'''
            pushfd
            pushad
            mov eax, dword ptr [ebp]
            call 0x4537d0
            test al, al
            jz done
            mov eax, dword ptr [ebp+4]
            push dword ptr [eax+0x160]
            mov eax, ebp
            call 0x42b810
            test eax, eax
            jz done
            mov dword ptr [esp+0x40], -40
        done:
            popad
            popfd
            {tail}
            jmp {site+size}
        ''')
        patch(site, asm(f'jmp {target}', site), size)

    # Prevent the running phase itself, including a loaded turned Yeti.
    yeti = emit('izombie_yeti_forward', '''
        push ecx
        mov ecx, dword ptr [eax]
        cmp dword ptr [ecx+0x7f8], 61
        jb original
        cmp dword ptr [ecx+0x7f8], 70
        ja original
        cmp dword ptr [eax+0x28], 0x5b
        jne done
        mov dword ptr [eax+0x28], 0
        mov byte ptr [eax+0xbc], 1
    done:
        pop ecx
        ret
    original:
        pop ecx
        cmp byte ptr [eax+0xb8], 0
        jmp 0x52a8e7
    ''')
    patch(0x52a8e0, asm(f'jmp {yeti}', 0x52a8e0), 7)

    boss_health = emit('izombie_boss_health', '''
        cmp dword ptr [ecx+0x7f8], 61
        jb original
        cmp dword ptr [ecx+0x7f8], 70
        ja original
        mov edx, 500
    original:
        mov dword ptr [edi+0xc8], edx
        jmp 0x523638
    ''')
    patch(0x523632, asm(f'jmp {boss_health}', 0x523632), 6)

    # The serialized baseline slot also marks a living boss left at 1 HP by
    # the penalty. Native lethal body damage clamps HP to 1 as a death signal.
    boss_alive = emit('izombie_boss_death_check', f'''
        cmp dword ptr [edi+0xc8], 1
        jne done
        push eax
        mov eax, dword ptr [edi]
        cmp dword ptr [eax+0x7f8], 61
        jb original
        cmp dword ptr [eax+0x7f8], 70
        ja original
        cmp dword ptr [edi+0x154], {BOSS_LAST_STAND}
        jne original
        pop eax
        cmp dword ptr [edi+0xc8], 0
        ret
    original:
        pop eax
        cmp dword ptr [edi+0xc8], 1
    done:
        ret
    ''')
    for site in (0x536242, 0x536516):
        patch(site, asm(f'call {boss_alive}', site), 7)

    boss_damage = emit('izombie_boss_actual_damage', '''
        pushfd
        pushad
        cmp dword ptr [ebp+0x24], 25
        jne done
        cmp dword ptr [esp+0x44], 0
        jle done
        mov eax, dword ptr [ebp]
        cmp dword ptr [eax+0x7f8], 61
        jb done
        cmp dword ptr [eax+0x7f8], 70
        ja done
        mov dword ptr [ebp+0x154], 0
    done:
        popad
        popfd
        mov dword ptr [ebp+0xc8], edi
        jmp 0x53131f
    ''')
    patch(0x531319, asm(f'jmp {boss_damage}', 0x531319), 6)

    boss_enter = emit('izombie_boss_head_baseline', f'''
        mov dword ptr [edi+0x13c], eax
        pushfd
        pushad
        mov eax, dword ptr [edi]
        call 0x4537d0
        test al, al
        jz done
        mov eax, dword ptr [edi+0xc8]
        cmp eax, 1
        jne record
        cmp dword ptr [edi+0x154], {BOSS_LAST_STAND}
        je done
    record:
        mov dword ptr [edi+0x154], eax
    done:
        popad
        popfd
        jmp 0x5353d5
    ''')
    patch(0x5353cf, asm(f'jmp {boss_enter}', 0x5353cf), 6)

    # Apply the penalty 50 ticks before raising the head. All three native
    # death checks must distinguish this living 1 HP from lethal damage.
    boss_check = emit('izombie_boss_head_min_damage', f'''
        pushfd
        pushad
        mov eax, dword ptr [edi]
        call 0x4537d0
        test al, al
        jz done
        cmp dword ptr [edi+0x68], 50
        jne done
        mov eax, dword ptr [edi+0xc8]
        cmp eax, 1
        jle done
        cmp eax, dword ptr [edi+0x154]
        jne done
        mov dword ptr [edi+0xc8], 1
        mov dword ptr [edi+0x154], {BOSS_LAST_STAND}
    done:
        popad
        popfd
        call {boss_alive}
        jmp 0x5365fc
    ''')
    patch(0x5365f5, asm(f'jmp {boss_check}', 0x5365f5), 7)

    add_pause(emit, patch, asm)


# Unused Beghouled fields are serialized. The actual array at +0x14..+0x49
# is 54 bytes, enough for 27 packed type/column/row records.
QUEUE_MAGIC = 0x33515a49
QUEUE_CAPACITY = 27


def add_pause(emit, patch, asm):
    pause = emit('izombie_pause_no_dialog', '''
        cmp dword ptr [ecx+0x7f8], 61
        jb original
        cmp dword ptr [ecx+0x7f8], 70
        ja original
        pushad
        mov ecx, dword ptr [ecx+0x768]
        test ecx, ecx
        jz done
        mov al, 1
        call 0x4127a0
    done:
        popad
        ret
    original:
        push ebp
        mov ebp, esp
        and esp, -8
        jmp 0x4502c6
    ''')
    patch(0x4502c0, asm(f'jmp {pause}', 0x4502c0), 6)

    # LostFocus also calls DoPauseDialog. Only the keyboard toggles pause.
    toggle = emit('izombie_pause_toggle', '''
        cmp dword ptr [ecx+0x7f8], 61
        jb original
        cmp dword ptr [ecx+0x7f8], 70
        ja original
        pushad
        mov ecx, dword ptr [ecx+0x768]
        mov al, byte ptr [ecx+0x164]
        xor al, 1
        call 0x4127a0
        popad
        ret
    original:
        jmp 0x4502c0
    ''')
    patch(0x41b8ec, asm(f'call {toggle}', 0x41b8ec), 5)

    can_pick = emit('izombie_pause_can_pick', '''
        cmp byte ptr [edi+0x164], 0
        je 0x48850f
        mov eax, dword ptr [edi+0x8c]
        cmp dword ptr [eax+0x7f8], 61
        jb 0x488589
        cmp dword ptr [eax+0x7f8], 70
        ja 0x488589
        jmp 0x48850f
    ''')
    patch(0x488506, asm(f'jmp {can_pick}', 0x488506), 9)

    board_pick = emit('izombie_pause_mouse_down', '''
        mov ecx, dword ptr [eax+4]
        cmp byte ptr [ecx+0x164], 0
        je 0x412235
        push edx
        mov edx, dword ptr [ecx+0x8c]
        cmp dword ptr [edx+0x7f8], 61
        jb blocked
        cmp dword ptr [edx+0x7f8], 70
        ja blocked
        pop edx
        jmp 0x412235
    blocked:
        pop edx
        jmp 0x412320
    ''')
    patch(0x412225, asm(f'jmp {board_pick}', 0x412225), 16)

    # Check before both the debit and easy-planting branch; full queues cannot
    # consume sun or advance the alternating bungee purchase price.
    capacity = emit('izombie_queue_capacity', f'''
        mov edx, dword ptr [ebp]
        cmp dword ptr [edx+0x7f8], 61
        jb original
        cmp dword ptr [edx+0x7f8], 70
        ja original
        mov edx, dword ptr [ebp+4]
        cmp byte ptr [edx+0x164], 0
        je original
        cmp dword ptr [ebp+0x10], {QUEUE_MAGIC}
        jne original
        cmp dword ptr [ebp+0xc], {QUEUE_CAPACITY}
        jae 0x42a51a
    original:
        mov edx, dword ptr [ebp]
        cmp byte ptr [edx+0x814], 0
        jmp 0x42a3c7
    ''')
    patch(0x42a3bd, asm(f'jmp {capacity}', 0x42a3bd), 10)

    enqueue = emit('izombie_queue_placement', f'''
        pushfd
        pushad
        mov ebp, ecx
        mov edx, dword ptr [ebp]
        cmp dword ptr [edx+0x7f8], 61
        jb original
        cmp dword ptr [edx+0x7f8], 70
        ja original
        mov edx, dword ptr [ebp+4]
        cmp byte ptr [edx+0x164], 0
        je original
        cmp dword ptr [ebp+0x10], {QUEUE_MAGIC}
        je initialized
        mov dword ptr [ebp+0x10], {QUEUE_MAGIC}
        mov dword ptr [ebp+0xc], 0
    initialized:
        mov edi, dword ptr [ebp+0xc]
        cmp edi, {QUEUE_CAPACITY}
        jae done
        shl eax, 10
        mov edx, dword ptr [esp+44]
        shl edx, 6
        or eax, edx
        or eax, dword ptr [esp+40]
        mov word ptr [ebp+edi*2+0x14], ax
        inc dword ptr [ebp+0xc]
    done:
        popad
        popfd
        ret 8
    original:
        popad
        popfd
        push ebx
        push ebp
        mov ebp, dword ptr [esp+0xc]
        jmp 0x42a0f6
    ''')
    patch(0x42a0f0, asm(f'jmp {enqueue}', 0x42a0f0), 6)

    update = emit('izombie_pause_update', f'''
        pushfd
        pushad
        mov eax, dword ptr [ebp+0x8c]
        cmp dword ptr [eax+0x7f8], 61
        jb original
        cmp dword ptr [eax+0x7f8], 70
        ja original
        cmp byte ptr [ebp+0x164], 0
        je drain
        mov edi, dword ptr [ebp+0x13c]
        call 0x438da0
        mov esi, dword ptr [ebp+0x138]
        call 0x438780
        popad
        popfd
        jmp 0x415e18
    drain:
        mov ebx, dword ptr [ebp+0x160]
        cmp dword ptr [ebx+0x10], {QUEUE_MAGIC}
        jne original
        mov edi, dword ptr [ebx+0xc]
        cmp edi, {QUEUE_CAPACITY}
        ja original
        mov dword ptr [ebx+0xc], 0
        xor esi, esi
    next:
        cmp esi, edi
        jae original
        movzx edx, word ptr [ebx+esi*2+0x14]
        mov eax, edx
        shr eax, 6
        and eax, 15
        push eax
        mov eax, edx
        and eax, 63
        push eax
        mov eax, edx
        shr eax, 10
        mov ecx, ebx
        call 0x42a0f0
        inc esi
        jmp next
    original:
        popad
        popfd
        cmp byte ptr [ebp+0x164], 0
        je 0x415e2e
        jmp 0x415df9
    ''')
    patch(0x415df0, asm(f'jmp {update}', 0x415df0), 9)
