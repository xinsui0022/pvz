"""V4: jack explosions and leader-owned dancer movement for modes 61..70."""


def add_v4(emit, patch, asm):
    early = emit('jack_early_roll', '''
        push ecx
        mov ecx, dword ptr [edi]
        mov eax, 20
        cmp dword ptr [ecx+0x7f8], 61
        jb draw
        cmp dword ptr [ecx+0x7f8], 70
        ja draw
        mov eax, 5
    draw:
        pop ecx
        jmp 0x5af400
    ''')
    patch(0x522fe8, asm(f'call {early}', 0x522fe8), 5)

    # KillAllPlantsInRadius: EDI=board, EBX=center Y, stack=center X, ret 4.
    # This call site is reached only by a non-hypnotized jack's real blast.
    brains = emit('jack_blast_brains', '''
        push dword ptr [esp+4]
        call 0x41cbf0
        pushfd
        pushad
        mov ebp, esp
        sub esp, 528
        and esp, -16
        fxsave [esp]
        fninit
        mov eax, dword ptr [esi]
        call 0x4537d0
        test al, al
        jz done
        sub esp, 24
        mov eax, dword ptr [ebp+40]
        mov dword ptr [esp+16], eax
        mov dword ptr [esp+20], ebx
        mov ebx, edi
        xor edi, edi
    row:
        push ebx
        mov edx, ebx
        xor ebx, ebx
        push 12
        call 0x408e40
        pop ebx
        test eax, eax
        jz next
        cmp byte ptr [eax+0x20], 0
        jne next
        cmp dword ptr [eax+0xc], 29
        je next
        mov esi, eax
        fld dword ptr [esi+0x24]
        call 0x6397d0
        mov dword ptr [esp], eax
        fld dword ptr [esi+0x28]
        call 0x6397d0
        mov dword ptr [esp+4], eax
        mov dword ptr [esp+8], 32
        mov dword ptr [esp+12], 31
        mov eax, esp
        mov ecx, dword ptr [esp+16]
        mov edx, dword ptr [esp+20]
        push 90
        call 0x41c850
        add esp, 4
        test al, al
        jz next
        mov eax, esi
        push dword ptr [ebx+0x160]
        call 0x42ba30
    next:
        inc edi
        cmp edi, 5
        jb row
        add esp, 24
    done:
        fxrstor [esp]
        mov esp, ebp
        popad
        popfd
        ret 4
    ''')
    patch(0x526c7f, asm(f'call {brains}', 0x526c7f), 5)

    # EDX=board, ECX=ID. Native lookup checks both slot and generation.
    # Ignore dying, removed, or detached objects even before array release.
    live = emit('dancer_live_lookup', '''
        call 0x41c7f0
        test eax, eax
        jz done
        cmp byte ptr [eax+0xec], 0
        jne invalid
        cmp dword ptr [eax+0x28], 1
        jb done
        cmp dword ptr [eax+0x28], 3
        ja done
    invalid:
        xor eax, eax
    done:
        ret
    ''')

    native = emit('dancer_native_walk', '''
        push ecx
        push ebx
        push edi
        mov eax, esi
        jmp 0x52aa45
    ''')

    # Each zombie used to walk independently, using its own _ground track.
    # Followers finish rising at 150 ticks; the leader holds for 200 ticks.
    # Only the leader now advances a linked team, distributing its actual
    # displacement once. No per-tick cache or serialized custom state needed.
    walk = emit('dancer_team_walk', f'''
        pushfd
        pushad
        mov eax, dword ptr [esi]
        call 0x4537d0
        test al, al
        jz original
        cmp byte ptr [esi+0xec], 0
        jne original
        mov eax, dword ptr [esi+0x28]
        dec eax
        cmp eax, 2
        jbe original
        cmp dword ptr [esi+0x24], 8
        je leader
        cmp dword ptr [esi+0x24], 9
        jne original
        mov edx, dword ptr [esi+4]
        mov ecx, dword ptr [esi+0xf0]
        call {live}
        test eax, eax
        jz original
        cmp dword ptr [eax+0x24], 8
        jne original
        mov cl, byte ptr [eax+0xb8]
        cmp cl, byte ptr [esi+0xb8]
        jne original
        mov edx, dword ptr [esi+0x158]
        xor ecx, ecx
    membership:
        cmp dword ptr [eax+ecx*4+0xf4], edx
        je done
        inc ecx
        cmp ecx, 4
        jb membership
        jmp original
    leader:
        # Older saves can retain the leader's follower ID after ApplyButter
        # cleared only the follower's backlink. Repair only that exact orphan.
        xor edi, edi
    repair_link:
        mov edx, dword ptr [esi+4]
        mov ecx, dword ptr [esi+edi*4+0xf4]
        call {live}
        test eax, eax
        jz next_link
        cmp dword ptr [eax+0x24], 9
        jne next_link
        cmp dword ptr [eax+0xf0], 0
        jne next_link
        mov dl, byte ptr [esi+0xb8]
        cmp byte ptr [eax+0xb8], dl
        jne next_link
        mov edx, dword ptr [esi+0x158]
        mov dword ptr [eax+0xf0], edx
    next_link:
        inc edi
        cmp edi, 4
        jb repair_link
        mov ebp, esp
        sub esp, 528
        and esp, -16
        fxsave [esp]
        fninit
        sub esp, 20
        mov dword ptr [esp+16], 0x3f000000
        mov eax, dword ptr [esi+0x2c]
        mov dword ptr [esp], eax
        call {native}
        fld dword ptr [esi+0x2c]
        fsub dword ptr [esp]
        fstp dword ptr [esp+4]
        xor edi, edi
    follower:
        mov edx, dword ptr [esi+4]
        mov ecx, dword ptr [esi+edi*4+0xf4]
        call {live}
        test eax, eax
        jz next
        cmp dword ptr [eax+0x24], 9
        jne next
        mov edx, dword ptr [esi+0x158]
        cmp dword ptr [eax+0xf0], edx
        jne next
        mov dl, byte ptr [esi+0xb8]
        cmp byte ptr [eax+0xb8], dl
        jne next
        mov ebx, eax
        fld dword ptr [ebx+0x2c]
        fadd dword ptr [esp+4]
        fstp dword ptr [ebx+0x2c]
        # Repair an old save's existing drift while walking, by at most half
        # this tick's displacement. A stopped team receives zero correction;
        # no teleport, reverse step, or correction through an eating pause.
        fld dword ptr [esi+0x2c]
        push 100
        cmp edi, 2
        je front
        cmp edi, 3
        jne target
        fiadd dword ptr [esp]
        jmp target
    front:
        fisub dword ptr [esp]
    target:
        add esp, 4
        fsub dword ptr [ebx+0x2c]
        fstp dword ptr [esp+8]
        fld dword ptr [esp+4]
        fabs
        fmul dword ptr [esp+16]
        fstp dword ptr [esp+12]
        fld dword ptr [esp+8]
        fcomp dword ptr [esp+12]
        fnstsw ax
        test ah, 0x41
        jnz lower_bound
        fld dword ptr [esp+12]
        fstp dword ptr [esp+8]
        jmp correct
    lower_bound:
        fld dword ptr [esp+12]
        fchs
        fcomp dword ptr [esp+8]
        fnstsw ax
        test ah, 0x41
        jnz correct
        fld dword ptr [esp+12]
        fchs
        fstp dword ptr [esp+8]
    correct:
        fld dword ptr [ebx+0x2c]
        fadd dword ptr [esp+8]
        fstp dword ptr [ebx+0x2c]
        fld dword ptr [ebx+0x2c]
        call 0x6397d0
        mov dword ptr [ebx+8], eax
    next:
        inc edi
        cmp edi, 4
        jb follower
        add esp, 20
        fxrstor [esp]
        mov esp, ebp
    done:
        popad
        popfd
        ret
    original:
        popad
        popfd
        jmp {native}
    ''')
    patch(0x52aa40, asm(f'jmp {walk}', 0x52aa40), 5)

    # SummonBackupDancers passes integer X; retain the leader's fractional
    # part too so upper/lower start aligned and front/rear start at +/-100.
    spawn = emit('dancer_spawn_alignment', f'''
        push dword ptr [esp+8]
        push dword ptr [esp+8]
        call 0x528760
        pushfd
        pushad
        mov ebx, eax
        mov eax, dword ptr [esi]
        call 0x4537d0
        test al, al
        jz done
        mov edx, dword ptr [esi+4]
        mov ecx, ebx
        call {live}
        test eax, eax
        jz done
        push 100
        fld dword ptr [esi+0x2c]
        cmp ebp, 2
        je front
        cmp ebp, 3
        jne place
        fiadd dword ptr [esp]
        jmp place
    front:
        fisub dword ptr [esp]
    place:
        fstp dword ptr [eax+0x2c]
        add esp, 4
        mov ebx, eax
        fld dword ptr [ebx+0x2c]
        call 0x6397d0
        mov dword ptr [ebx+8], eax
    done:
        popad
        popfd
        ret 8
    ''')
    patch(0x528a17, asm(f'call {spawn}', 0x528a17), 5)
