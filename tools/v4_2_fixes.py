"""Butter-safe dancer relationships and private, per-team bobsled ice."""

SLED_MAGIC = 0x32495a49
HP_MAGIC = 0x32505a49


def add_v4_2(emit, patch, asm):
    butter = emit('butter_keep_dancer_leader', '''
        pushfd
        pushad
        cmp dword ptr [esi+0x24], 9
        jne original
        cmp dword ptr [eax+0x24], 8
        jne original
        mov ecx, dword ptr [esi]
        cmp dword ptr [ecx+0x7f8], 61
        jb original
        cmp dword ptr [ecx+0x7f8], 70
        ja original
        popad
        popfd
        jmp 0x532762
    original:
        popad
        popfd
        mov dword ptr [eax+0xf0], 0
        jmp 0x532758
    ''')
    patch(0x53274e, asm(f'jmp {butter}', 0x53274e), 10)

    initialize = emit('sled_private_ice_init', f'''
        pushfd
        pushad
        mov esi, eax
        cmp dword ptr [esi+0x24], 13
        jne done
        mov eax, dword ptr [esi]
        cmp dword ptr [eax+0x7f8], 61
        jb done
        cmp dword ptr [eax+0x7f8], 70
        ja done
        cmp dword ptr [esi+0xf0], 0
        jne done
        cmp dword ptr [esi+0xf4], 0
        je done
        cmp dword ptr [esi+0x134], {SLED_MAGIC}
        je done
        mov eax, 2
        call 0x5af400
        add eax, 4
        imul eax, eax, 80
        mov dword ptr [esi+0x13c], eax
        mov eax, dword ptr [esi+0x2c]
        mov dword ptr [esi+0x138], eax
        mov dword ptr [esi+0x134], {SLED_MAGIC}
    done:
        popad
        popfd
        ret
    ''')

    relocate = emit('sled_random_formation', f'''
        pushfd
        pushad
        mov esi, eax
        cmp dword ptr [esi+0x24], 13
        jne done
        mov eax, dword ptr [esi]
        cmp dword ptr [eax+0x7f8], 61
        jb done
        cmp dword ptr [eax+0x7f8], 70
        ja done
        mov ebp, esp
        sub esp, 528
        and esp, -16
        fxsave [esp]
        fninit
        xor edi, edi
    member:
        mov edx, dword ptr [esi+4]
        mov ecx, dword ptr [esi+edi*4+0xf4]
        call 0x41c7f0
        test eax, eax
        jz next
        cmp dword ptr [eax+0x24], 13
        jne next
        mov edx, dword ptr [esi+0x158]
        cmp dword ptr [eax+0xf0], edx
        jne next
        mov ebx, eax
        lea eax, [edi+1]
        imul eax, eax, 50
        push eax
        fld dword ptr [esi+0x2c]
        fiadd dword ptr [esp]
        add esp, 4
        fstp dword ptr [ebx+0x2c]
        fld dword ptr [ebx+0x2c]
        call 0x6397d0
        mov dword ptr [ebx+8], eax
    next:
        inc edi
        cmp edi, 3
        jb member
        mov eax, esi
        call {initialize}
        fxrstor [esp]
        mov esp, ebp
    done:
        popad
        popfd
        sub esp, 4
        push eax
        mov eax, 5
        jmp 0x651180
    ''')
    patch(0x651177, asm(f'jmp {relocate}', 0x651177), 9)

    ice = emit('sled_private_ice_update', f'''
        pushfd
        pushad
        mov eax, dword ptr [esi]
        cmp dword ptr [eax+0x7f8], 61
        jb original
        cmp dword ptr [eax+0x7f8], 70
        ja original
        mov eax, esi
        call {initialize}
        cmp dword ptr [esi+0xf0], 0
        jne safe
        cmp dword ptr [esi+0x134], {SLED_MAGIC}
        jne safe
        fld dword ptr [esi+0x138]
        fisub dword ptr [esi+0x13c]
        fcomp dword ptr [esi+0x2c]
        fnstsw ax
        test ah, 0x41
        jnz safe
        mov edx, dword ptr [esi+4]
        mov ecx, dword ptr [esi+0x1c]
        cmp ecx, 5
        jae off_ice
        cmp dword ptr [edx+ecx*4+0x624], 0
        jle off_ice
        fld dword ptr [esi+0x2c]
        push 10
        fiadd dword ptr [esp]
        add esp, 4
        fild dword ptr [edx+ecx*4+0x60c]
        fcompp
        fnstsw ax
        test ah, 0x41
        jnz safe
    off_ice:
        popad
        popfd
        jmp 0x528221
    safe:
        popad
        popfd
        jmp 0x52822d
    original:
        popad
        popfd
        mov ecx, dword ptr [esi+0x1c]
        mov edx, dword ptr [esi+4]
        jmp 0x5281db
    ''')
    patch(0x5281d5, asm(f'jmp {ice}', 0x5281d5), 6)

    add_health_display(emit, patch, asm)


def add_health_display(emit, patch, asm):
    toggle = emit('health_display_toggle', f'''
        pushfd
        pushad
        cmp dword ptr [esp+40], 119
        jne original
        mov eax, dword ptr [ecx+0x8c]
        cmp dword ptr [eax+0x7f8], 61
        jb original
        cmp dword ptr [eax+0x7f8], 70
        ja original
        mov eax, dword ptr [ecx+0x160]
        test eax, eax
        jz original
        cmp dword ptr [eax+0x9c], {HP_MAGIC}
        je disable
        mov dword ptr [eax+0x9c], {HP_MAGIC}
        jmp done
    disable:
        mov dword ptr [eax+0x9c], 0
    done:
        popad
        popfd
        ret 4
    original:
        popad
        popfd
        push esi
        push edi
        mov edi, dword ptr [esp+12]
        jmp 0x41b826
    ''')
    patch(0x41b820, asm(f'jmp {toggle}', 0x41b820), 6)

    # Read-only body + helmet + shield totals; ignore negative depleted HP.
    sums = []
    for health, maximum in ((0xc8,0xcc), (0xd0,0xd4), (0xdc,0xe0)):
        sums.append(f'''
            mov ecx, dword ptr [esi+{health}]
            test ecx, ecx
            jg current_{health}
            xor ecx, ecx
        current_{health}:
            add eax, ecx
            mov ebx, dword ptr [esi+{maximum}]
            cmp ebx, ecx
            jge maximum_{health}
            mov ebx, ecx
        maximum_{health}:
            add edx, ebx
        ''')
    total = emit('health_display_totals', f'''
        push ebx
        push ecx
        xor eax, eax
        xor edx, edx
        {''.join(sums)}
        pop ecx
        pop ebx
        ret
    ''')

    # Tiny 3x5 bitmap digits, rendered at 2x. No font/resource replacement,
    # C++ string allocation, or changes to the game's graphics font pointer.
    patterns = ('111101101101111', '010110010010111', '111001111100111',
                '111001111001111', '101101111001001', '111100111001111',
                '111100111101111', '111001001001001', '111101111101111',
                '111101111001111')
    select = '\n'.join(f'cmp eax, {i}; je digit_{i}' for i in range(10))
    masks = '\n'.join(f'digit_{i}: mov dword ptr [esp+8], {int(s[::-1],2)}; jmp paint'
                      for i, s in enumerate(patterns))
    digit = emit('health_display_digit', f'''
        pushad
        sub esp, 12
        mov dword ptr [esp], ecx
        mov dword ptr [esp+4], edx
        {select}
        jmp done
        {masks}
    paint:
        xor esi, esi
    pixel:
        bt dword ptr [esp+8], esi
        jnc next
        mov eax, esi
        xor edx, edx
        mov ecx, 3
        div ecx
        lea ecx, [edx*2]
        add ecx, dword ptr [esp]
        lea edx, [eax*2]
        add edx, dword ptr [esp+4]
        push 2
        push 2
        push edx
        push ecx
        mov eax, edi
        call 0x586d50
    next:
        inc esi
        cmp esi, 15
        jb pixel
    done:
        add esp, 12
        popad
        ret
    ''')
    number = emit('health_display_number', f'''
        pushad
        sub esp, 8
        mov dword ptr [esp], edx
        mov dword ptr [esp+4], 0
        mov ebp, ecx
        mov esi, eax
        mov ebx, 10000
    digit:
        mov eax, esi
        xor edx, edx
        div ebx
        mov esi, edx
        test eax, eax
        jnz paint
        cmp ebx, 1
        je paint
        cmp dword ptr [esp+4], 0
        je next
    paint:
        mov dword ptr [esp+4], 1
        mov ecx, ebp
        mov edx, dword ptr [esp]
        call {digit}
        add ebp, 8
    next:
        mov eax, ebx
        xor edx, edx
        mov ecx, 10
        div ecx
        mov ebx, eax
        test ebx, ebx
        jnz digit
        add esp, 8
        popad
        ret
    ''')

    overlay = emit('health_overlay_draw', f'''
        pushfd
        pushad
        mov ebx, dword ptr [esp+40]
        mov eax, dword ptr [ebx+0x8c]
        cmp dword ptr [eax+0x7f8], 61
        jb done
        cmp dword ptr [eax+0x7f8], 70
        ja done
        mov eax, dword ptr [ebx+0x160]
        cmp dword ptr [eax+0x9c], {HP_MAGIC}
        jne done
        mov edi, dword ptr [esp+44]
        mov ebp, esp
        sub esp, 528
        and esp, -16
        fxsave [esp]
        fninit
        sub esp, 64
        mov dword ptr [esp], 0
        mov dword ptr [esp+4], ebx
        mov eax, dword ptr [edi+0x30]
        mov dword ptr [esp+24], eax
        mov eax, dword ptr [edi+0x34]
        mov dword ptr [esp+28], eax
        mov eax, dword ptr [edi+0x38]
        mov dword ptr [esp+32], eax
        mov eax, dword ptr [edi+0x3c]
        mov dword ptr [esp+36], eax
        mov eax, dword ptr [edi+0x44]
        mov dword ptr [esp+40], eax
        mov dword ptr [edi+0x44], 0
        mov dword ptr [edi+0x3c], 255
    zombie:
        mov edx, dword ptr [esp+4]
        mov esi, esp
        call 0x41c8f0
        test al, al
        jz restore
        mov esi, dword ptr [esp]
        mov eax, dword ptr [esi+0x28]
        dec eax
        cmp eax, 2
        jbe zombie
        cmp dword ptr [esi+0x6c], -2
        je zombie
        cmp dword ptr [esi+0x6c], -3
        je zombie
        call {total}
        test eax, eax
        jle zombie
        test edx, edx
        jle zombie
        mov dword ptr [esp+16], eax
        mov dword ptr [esp+20], edx
        fld dword ptr [esi+0x2c]
        call 0x6397d0
        add eax, 36
        cmp dword ptr [esi+0x24], 25
        jne x_bounds
        mov eax, dword ptr [esi+0x158]
        and eax, 3
        imul eax, eax, -60
        add eax, 720
    x_bounds:
        cmp eax, -48
        jl zombie
        cmp eax, 800
        jg zombie
        test eax, eax
        jge x_right
        xor eax, eax
    x_right:
        cmp eax, 748
        jle x_done
        mov eax, 748
    x_done:
        mov dword ptr [esp+8], eax
        fld dword ptr [esi+0x30]
        fsub dword ptr [esi+0x84]
        call 0x6397d0
        sub eax, 12
        cmp eax, 80
        jge y_bottom
        mov eax, 80
    y_bottom:
        cmp eax, 566
        jle y_done
        mov eax, 566
    y_done:
        mov dword ptr [esp+12], eax
        mov dword ptr [edi+0x30], 18
        mov dword ptr [edi+0x34], 22
        mov dword ptr [edi+0x38], 18
        mov ecx, dword ptr [esp+8]
        dec ecx
        dec eax
        push 18
        push 50
        push eax
        push ecx
        mov eax, edi
        call 0x586d50
        mov dword ptr [edi+0x30], 70
        mov dword ptr [edi+0x34], 220
        mov dword ptr [edi+0x38], 90
        mov eax, dword ptr [esp+16]
        imul eax, eax, 48
        xor edx, edx
        div dword ptr [esp+20]
        test eax, eax
        jnz width
        inc eax
    width:
        cmp eax, 24
        ja color_done
        mov dword ptr [edi+0x30], 255
        mov dword ptr [edi+0x34], 190
        cmp eax, 12
        ja color_done
        mov dword ptr [edi+0x34], 65
    color_done:
        mov ecx, dword ptr [esp+8]
        mov edx, dword ptr [esp+12]
        push 4
        push eax
        push edx
        push ecx
        mov eax, edi
        call 0x586d50
        mov dword ptr [edi+0x30], 255
        mov dword ptr [edi+0x34], 255
        mov dword ptr [edi+0x38], 255
        mov eax, dword ptr [esp+16]
        mov ecx, dword ptr [esp+8]
        mov edx, dword ptr [esp+12]
        add edx, 6
        call {number}
        jmp zombie
    restore:
        mov eax, dword ptr [esp+24]
        mov dword ptr [edi+0x30], eax
        mov eax, dword ptr [esp+28]
        mov dword ptr [edi+0x34], eax
        mov eax, dword ptr [esp+32]
        mov dword ptr [edi+0x38], eax
        mov eax, dword ptr [esp+36]
        mov dword ptr [edi+0x3c], eax
        mov eax, dword ptr [esp+40]
        mov dword ptr [edi+0x44], eax
        add esp, 64
        fxrstor [esp]
        mov esp, ebp
    done:
        popad
        popfd
        ret 8
    ''')
    draw = emit('health_overlay_board_draw', f'''
        push dword ptr [esp+8]
        push dword ptr [esp+8]
        call {overlay}
        sub esp, 0x64
        push ebx
        push ebp
        jmp 0x419ae5
    ''')
    patch(0x419ae0, asm(f'jmp {draw}', 0x419ae0), 5)
