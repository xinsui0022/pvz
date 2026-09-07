"""Second-pass x86 hooks. All gameplay additions are scoped to I, Zombie."""
def add_fixes(emit, patch, asm, symbols):
    damage = emit('projectile_damage', '''
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
        jz apply_damage
        cmp dword ptr [esi+0x24], 1
        jne apply_damage
        cmp byte ptr [esi+0x141], 0
        jne apply_damage
        cmp byte ptr [esi+0x142], 0
        jne apply_damage
        cmp dword ptr [esi+0x40], 0
        jle apply_damage
        mov ebx, dword ptr [ebp+24]
        test ebx, ebx
        jle apply_damage
        mov eax, dword ptr [esi+0x40]
        xor edx, edx
        mov ecx, 40
        div ecx
        lea edi, [eax+1]
        mov eax, dword ptr [esi+0x40]
        sub eax, ebx
        jle payout
        xor edx, edx
        div ecx
        inc eax
        sub edi, eax
    payout:
        test edi, edi
        jle apply_damage
        xor ebx, ebx
    coin_loop:
        push 2
        push 4
        push dword ptr [esi+12]
        mov eax, dword ptr [esi+8]
        add eax, ebx
        push eax
        mov ecx, dword ptr [esi+4]
        call 0x40cb10
        add ebx, 5
        dec edi
        jnz coin_loop
    apply_damage:
        mov eax, dword ptr [ebp+24]
        sub dword ptr [esi+0x40], eax
        cmp dword ptr [esi+0x40], 0
        jg done
        cmp byte ptr [esi+0x141], 0
        jne done
        mov eax, dword ptr [esi]
        call 0x4537d0
        test al, al
        jz done
        push esi
        call 0x4679b0
    done:
        fxrstor [esp]
        mov esp, ebp
        popad
        popfd
        ret
    ''')
    basketball=emit('basketball_sun',f'call {damage}; cmp eax, 25; jmp 0x46d7ac')
    patch(0x46d7a6,asm(f'jmp {basketball}',0x46d7a6),6)
    pea=emit('pea_damage',f'''
        pushad
        mov esi, eax
        mov ecx, edx
        call {damage}
        popad
        cmp ecx, 25
        jmp 0x46cff1
    ''')
    patch(0x46cfeb,asm(f'jmp {pea}',0x46cfeb),6)

    # Jalapeno's per-plant kill uses EAX rather than ESI.
    jalapeno_sun=emit('jalapeno_sun',f'''
        push esi
        mov esi, eax
        push dword ptr [esp+8]
        call {symbols['jack_sun']}
        pop esi
        ret 4
    ''')
    patch(0x527729,asm(f'call {jalapeno_sun}',0x527729))

    # Reusable brain squish by row. EDX=board, EDI=row. Preserve all state.
    squish=emit('squish_brain_in_row','''
        pushfd
        pushad
        cmp edi, 5
        jae done
        mov ebp, dword ptr [edx+0x160]
        xor ebx, ebx
        push 12
        call 0x408e40
        test eax, eax
        jz done
        cmp dword ptr [eax+0xc], 29
        je done
        push ebp
        call 0x42ba30
    done:
        popad
        popfd
        ret
    ''')
    jalapeno_brain=emit('jalapeno_brain',f'''
        pushfd
        pushad
        mov eax, dword ptr [edi]
        call 0x4537d0
        test al, al
        jz done
        cmp byte ptr [edi+0xb8], 0
        jne done
        mov edx, dword ptr [edi+4]
        mov edi, dword ptr [edi+0x1c]
        call {squish}
    done:
        popad
        popfd
        jmp 0x530510
    ''')
    patch(0x527740,asm(f'call {jalapeno_brain}',0x527740))

    pogo=emit('pogo_brain','''
        pushad
        mov eax, dword ptr [edi]
        call 0x4537d0
        test al, al
        jz original
        mov eax, dword ptr [edi+4]
        push dword ptr [eax+0x160]
        mov eax, edi
        call 0x42b810
        test eax, eax
        jz original
        push 0
        push edi
        call 0x525350
        popad
        jmp 0x525722
    original:
        popad
        cmp eax, 0x15
        jmp 0x5254ef
    ''')
    # Only after original death/frozen/butter/phase/chimney guards.
    # The resumed original x87 instructions do not disturb CMP's flags.
    patch(0x5254e2,asm(f'jmp {emit("pogo_height_gate",f"cmp dword ptr [edi+0x64], 8; je 0x525722; jmp {pogo}")}',0x5254e2),10)

    # Normalize the two aquatic types before their original state machine.
    # No board tiles are changed: this applies only to these zombies.
    aquatic=emit('aquatic_mode','''
        pushfd
        pushad
        mov edi, eax
        mov eax, dword ptr [edi]
        call 0x4537d0
        test al, al
        jz done
        cmp byte ptr [edi+0xec], 0
        jne done
        mov eax, dword ptr [edi+0x28]
        cmp dword ptr [edi+0x24], 14
        je dolphin
        cmp dword ptr [edi+0x24], 11
        jne done
        cmp eax, 0x39
        jne done
        mov dword ptr [edi+0x28], 0x3b
        mov dword ptr [edi+0x84], 0x41200000
        jmp swim
    dolphin:
        cmp eax, 0x38
        je dolphin_swim
        cmp eax, 0x33
        jne check_brain
        mov dword ptr [edi+0x28], 0x35
        mov byte ptr [edi+0xbd], 1
        mov dword ptr [edi+0x64], 0
        mov dword ptr [edi+0x84], 0
        mov dword ptr [edi+0x9c], -29
        mov dword ptr [edi+0xa0], 0
        mov dword ptr [edi+0xa4], 70
        mov dword ptr [edi+0xa8], 115
        push 0x41400000
        push 0
        push 1
        push 0x66ed94
        call 0x528b00
    check_brain:
        cmp dword ptr [edi+0x28], 0x35
        jne done
        mov eax, dword ptr [edi+4]
        push dword ptr [eax+0x160]
        mov eax, edi
        call 0x42b810
        test eax, eax
        jz done
    dolphin_swim:
        mov dword ptr [edi+0x28], 0x37
        mov dword ptr [edi+0x9c], 30
        mov dword ptr [edi+0xa0], 0
        mov dword ptr [edi+0xa4], 30
        mov dword ptr [edi+0xa8], 115
        mov dword ptr [edi+0x84], 0
    swim:
        mov byte ptr [edi+0xbd], 1
        mov dword ptr [edi+0x64], 0
        push 0x41400000
        push 0
        push 1
        push 0x66edb4
        call 0x528b00
    done:
        popad
        popfd
        ret
    ''')
    for name,site,prolog,resume,length in [
        ('dolphin_update',0x5261e0,'push ebp; mov ebp, esp; and esp, -8',0x5261e6,6),
        ('snorkel_update',0x526720,'push ecx; push ebx; push ebp; push esi; push edi',0x526725,5)]:
        dest=emit(name,f'call {aquatic}; {prolog}; jmp {resume}')
        patch(site,asm(f'jmp {dest}',site),length)

    # Keep swimming at the left edge; retain original exits outside I, Zombie.
    for name,site,length,resume,iz_dest,replay in [
        ('snorkel_pool_edge',0x52695d,6,0x526963,0x5269c6,'mov ecx, dword ptr [edi+8]; cmp ecx, 25'),
        ('dolphin_swim_edge',0x5266b9,6,0x5266bf,0x52670f,'mov ecx, dword ptr [edi+8]; cmp ecx, 10'),
        ('dolphin_ride_edge',0x5263e4,6,0x5263ea,0x52642f,'cmp dword ptr [edi+8], 10; jg 0x52642f')]:
        dest=emit(name,f'''
            pushad
            mov eax, dword ptr [edi]
            call 0x4537d0
            test al, al
            jz original
            popad
            jmp {iz_dest}
        original:
            popad
            {replay}
            jmp {resume}
        ''')
        patch(site,asm(f'jmp {dest}',site),length)

    # Uniform 35-way draw: original 33 types plus two extra boss tickets.
    # Boss probability = 3/35 = 8.57%; all other types = 1/35.
    random=emit('weighted_random','''
        push ecx
        push edx
        mov eax, dword ptr [ebx]
        call 0x4537d0
        test al, al
        jz original
        mov eax, 35
        call 0x5af400
        cmp eax, 33
        jb done
        mov eax, 25
        jmp done
    original:
        mov eax, 33
        call 0x5af400
    done:
        pop edx
        pop ecx
        ret
    ''')
    patch(0x6510e9,asm(f'call {random}',0x6510e9))
