"""Bind every boss render part to its actual zombie array slot."""
def add_multi_boss(emit, patch, asm):
    # RenderItem's union cannot hold both a pointer and part. Pack a bounded
    # 16-bit DataArray slot (+1 to distinguish legacy values) and 3-bit part.
    for name, site, size, target, part in [
        ('back_leg', 0x4167a8, 8, '[ebx+ecx*4+8]', 0),
        ('front_leg', 0x4167d1, 8, '[ebx+ecx*4+8]', 1),
        ('main', 0x4167f4, 7, '[ecx+8]', 2),
        ('arm', 0x416815, 7, '[ecx+8]', 3),
        ('ball', 0x416867, 7, '[ebx+8]', 4),
    ]:
        dest = emit('boss_item_'+name, f'''
            push eax
            movzx eax, word ptr [ebp+0x158]
            inc eax
            shl eax, 3
            or eax, {part}
            mov dword ptr {target}, eax
            pop eax
            jmp {site+size}
        ''')
        patch(site, asm(f'jmp {dest}', site), size)
    resolve = emit('boss_item_resolve', '''
        mov edx, dword ptr [ebp+8]
        mov eax, dword ptr [ebx]
        shr eax, 3
        test eax, eax
        jz legacy
        dec eax
        cmp eax, dword ptr [edx+0x94]
        jae invalid
        imul eax, eax, 0x15c
        add eax, dword ptr [edx+0x90]
        test dword ptr [eax+0x158], 0xffff0000
        jz invalid
        cmp dword ptr [eax+0x24], 25
        jne invalid
        jmp 0x417122
    legacy:
        call 0x41d390
        jmp 0x417122
    invalid:
        xor eax, eax
        jmp 0x417122
    ''')
    patch(0x41711a, asm(f'jmp {resolve}', 0x41711a), 8)
    # Decode the part without changing the original x87 FADD stack state.
    part = emit('boss_part_decode', '''
        mov edx, dword ptr [ebx]
        and edx, 7
        push edx
        fadd dword ptr [esi+8]
        jmp 0x417142
    ''')
    patch(0x41713c, asm(f'jmp {part}', 0x41713c), 6)
    draw = emit('boss_distinct_draw', '''
        pushad
        sub esp, 12
        mov eax, dword ptr [ebx+8]
        mov dword ptr [esp], eax
        mov eax, dword ptr [edi+0xac]
        mov dword ptr [esp+4], eax
        mov eax, dword ptr [edi]
        call 0x4537d0
        test al, al
        jz draw
        mov edx, dword ptr [edi+4]
        mov edx, dword ptr [edx+0x90]
        xor eax, eax
    count:
        cmp edx, edi
        jae counted
        test dword ptr [edx+0x158], 0xffff0000
        jz next
        cmp byte ptr [edx+0xec], 0
        jne next
        cmp dword ptr [edx+0x24], 25
        jne next
        inc eax
    next:
        add edx, 0x15c
        jmp count
    counted:
        test eax, eax
        jz draw
        mov dword ptr [edi+0xac], 1
        cmp dword ptr [esp+48], 4
        je draw
        cmp eax, 3
        jbe offset
        mov eax, 3
    offset:
        imul eax, eax, -80
        mov dword ptr [esp+8], eax
        fild dword ptr [esp+8]
        fadd dword ptr [ebx+8]
        fstp dword ptr [ebx+8]
    draw:
        push dword ptr [esp+48]
        call 0x536940
        mov eax, dword ptr [esp]
        mov dword ptr [ebx+8], eax
        mov eax, dword ptr [esp+4]
        mov dword ptr [edi+0xac], eax
        add esp, 12
        popad
        ret 4
    ''')
    # Blue tint is draw-only: the chilled state is restored before updating.
    # Fireball positions are not translated, so their visuals match collision.
    patch(0x417150, asm(f'call {draw}', 0x417150))
