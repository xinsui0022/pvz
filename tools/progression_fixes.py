"""I, Zombie health and completion rewards, with verified x86 hook ABIs."""
# Low-health random results get the more forgiving 65/25/4/3/3 roll.
# V4 also includes dancing and bungee zombies, only on random conversion.
WEAK_TYPES = (0, 1, 5, 6, 8, 9, 10, 11, 14, 15, 16, 17, 18, 20, 24, 26, 29, 30, 31)
HEALTH_WEIGHTS = (65, 25, 4, 3, 3)

def add_progression(emit, patch, asm):
    checks = '\n'.join(f'cmp edx, {kind}; je weighted' for kind in WEAK_TYPES)
    health = emit('weak_health_roll', f'''
        push ebx
        mov ebx, dword ptr [esp+8]
        push ecx
        push edx
        mov eax, dword ptr [ebx]
        call 0x4537d0
        test al, al
        jz original
        mov edx, dword ptr [ebx+0x24]
        cmp edx, 12
        je full
        cmp edx, 22
        je full
        {checks}
    original:
        mov eax, 5
        call 0x5af400
        jmp done
    weighted:
        mov eax, 100
        call 0x5af400
        cmp eax, 65
        jb full
        cmp eax, 90
        jb half
        cmp eax, 94
        jb third
        cmp eax, 97
        jb quarter
        mov eax, 4
        jmp done
    full:
        xor eax, eax
        jmp done
    half:
        mov eax, 1
        jmp done
    third:
        mov eax, 2
        jmp done
    quarter:
        mov eax, 3
    done:
        pop edx
        pop ecx
        pop ebx
        ret
    ''')
    # Caller has pushed the NEW zombie. EBX still refers to the dead cone.
    patch(0x651180, asm(f'call {health}', 0x651180))

    coin_drop = emit('completion_reward_coins', '''
        # EAX=Board*, ECX=amount.  One sun coin is 25, so all three reward
        # sources remain exact while the player still has to pick them up.
        pushfd
        pushad
        mov ebp, eax
        mov esi, ecx
        xor edi, edi
    coin:
        cmp esi, 25
        jb done
        push 2
        push 4
        push 300
        lea eax, [edi+300]
        push eax
        mov ecx, ebp
        call 0x40cb10
        add edi, 12
        sub esi, 25
        jmp coin
    done:
        popad
        popfd
        ret
    ''')

    reward_only = emit('completion_reward_once', f'''
        pushfd
        pushad
        sub esp, 4
        mov ebp, ecx
        mov eax, dword ptr [ebp]
        cmp dword ptr [eax+0x7f8], 70
        jne done
        cmp dword ptr [ebp+0x60], 5
        jne done
        mov eax, dword ptr [ebp+0x6c]
        inc eax
        or eax, 0xb0000000
        cmp dword ptr [ebp+0x70], eax
        je done
        mov dword ptr [ebp+0x70], eax
        xor edi, edi
        mov eax, dword ptr [ebp+0x6c]
        inc eax
        xor edx, edx
        mov ecx, 3
        div ecx
        test edx, edx
        jnz ten
        add edi, 100
    ten:
        mov eax, dword ptr [ebp+0x6c]
        inc eax
        xor edx, edx
        mov ecx, 10
        div ecx
        test edx, edx
        jnz plants
        add edi, 500
    plants:
        mov dword ptr [esp], 0
    next_plant:
        mov edx, dword ptr [ebp+4]
        mov esi, esp
        call 0x41c950
        test al, al
        jz cleared
        mov eax, dword ptr [esp]
        cmp byte ptr [eax+0x142], 0
        jne next_plant
        cmp byte ptr [eax+0x144], 0
        je next_plant
        cmp dword ptr [eax+0x24], 21
        je next_plant
        cmp dword ptr [eax+0x24], 46
        je next_plant
        jmp pay
    cleared:
        add edi, 75
    pay:
        test edi, edi
        jz done
        mov eax, dword ptr [ebp+4]
        mov ecx, edi
        call {coin_drop}
    done:
        add esp, 4
        popad
        popfd
        ret
    ''')
    reward = emit('completion_rewards', f'''
        call {reward_only}
        push ebx
        push ebp
        push esi
        push edi
        mov edi, eax
        jmp 0x429986
    ''')
    # PuzzlePhaseComplete: ECX=Challenge; EAX=grid X. Preserve whole prologue.
    # +0x70 is the serialized slot-machine roll count, unused in I, Zombie.
    patch(0x429980, asm(f'jmp {reward}', 0x429980), 6)
    return reward_only
