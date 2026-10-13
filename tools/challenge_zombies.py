"""Challenge-only zombie health, preserving the traditional conversion code.

The random carrier is a cone zombie. Challenge adds the native 270-point
body value to its 370-point helmet, making the helmet 640 HP. Conversion
still happens immediately when that helmet disappears, exactly as before.
Newborn health is changed only in initialization/conversion, never in Update.
"""

NORMAL_BODY_HEALTH = 270
CONE_HELMET_HEALTH = 370
CHALLENGE_RANDOM_HELMET_HEALTH = NORMAL_BODY_HEALTH + CONE_HELMET_HEALTH
CHALLENGE_BOSS_HEALTH = 10000
CHALLENGE_BOSS_HALF_HEALTH = CHALLENGE_BOSS_HEALTH // 2
TRADITIONAL_IMP_HEALTH = 70


def add_challenge_zombies(emit, patch, asm, symbols):
    scope = symbols['iz_challenge_mode_predicate']

    # This is the native type-2 initialization assignment, shared by bought
    # and randomly produced carriers. Their body stays 270; only the helmet
    # current/max value grows. Neither DropHelm nor body-death logic changes.
    helmet = emit('challenge_random_helmet_health', f'''
        pushfd
        push eax
        mov eax, dword ptr [edi+4]
        call {scope}
        test eax, eax
        jz original
        mov dword ptr [edi+0xd0], {CHALLENGE_RANDOM_HELMET_HEALTH}
        mov dword ptr [edi+0xd4], {CHALLENGE_RANDOM_HELMET_HEALTH}
        jmp done
    original:
        mov dword ptr [edi+0xd0], {CONE_HELMET_HEALTH}
    done:
        pop eax
        popfd
        jmp 0x522896
    ''')
    patch(0x52288c, asm(f'jmp {helmet}', 0x52288c), 10)

    # The new zombie is the stack argument; EBX still names the old carrier.
    # Returning zero makes the original x87 division use one for all three
    # current/max HP pairs, including armor and vehicles. Traditional mode
    # still tail-calls its exact existing health roll.
    health = emit('challenge_random_full_health', f'''
        push ecx
        mov ecx, dword ptr [esp+8]
        mov eax, dword ptr [ecx+4]
        call {scope}
        test eax, eax
        pop ecx
        jz original
        xor eax, eax
        ret
    original:
        jmp {symbols['weak_health_roll']}
    ''')
    patch(0x651180, asm(f'call {health}', 0x651180), 5)

    imp = emit('challenge_imp_body_health', f'''
        pushfd
        push eax
        mov eax, dword ptr [edi+4]
        call {scope}
        test eax, eax
        jz original
        mov dword ptr [edi+0xc8], {NORMAL_BODY_HEALTH}
        jmp done
    original:
        mov dword ptr [edi+0xc8], {TRADITIONAL_IMP_HEALTH}
    done:
        pop eax
        popfd
        jmp 0x5235b0
    ''')
    patch(0x5235a6, asm(f'jmp {imp}', 0x5235a6), 10)

    boss = emit('challenge_boss_initial_health', f'''
        push eax
        mov eax, dword ptr [edi+4]
        call {scope}
        test eax, eax
        pop eax
        jz original
        mov edx, {CHALLENGE_BOSS_HEALTH}
        mov dword ptr [edi+0xc8], edx
        jmp 0x523638
    original:
        jmp {symbols['izombie_boss_health']}
    ''')
    patch(0x523632, asm(f'jmp {boss}', 0x523632), 6)

    # The supplied mod has a second 500 HP assignment after AddZombieInRow.
    # This branch bypasses the other random health hooks, so roll once here.
    # Half-health bosses retain the full maximum for native damage stages.
    random_boss = emit('challenge_random_boss_health', f'''
        pushfd
        pushad
        mov esi, eax
        mov eax, dword ptr [eax+4]
        call {scope}
        test eax, eax
        jz original
        mov eax, 2
        call 0x5af400
        test eax, eax
        jz full
        mov eax, {CHALLENGE_BOSS_HALF_HEALTH}
        jmp assign
    full:
        mov eax, {CHALLENGE_BOSS_HEALTH}
    assign:
        mov dword ptr [esi+0xc8], eax
        mov dword ptr [esi+0xcc], {CHALLENGE_BOSS_HEALTH}
        jmp done
    original:
        mov dword ptr [esi+0xc8], 500
        mov dword ptr [esi+0xcc], 500
    done:
        popad
        popfd
        jmp 0x651157
    ''')
    patch(0x651143, asm(f'jmp {random_boss}', 0x651143), 20)

    # Native lethal damage clamps boss HP to one. Challenge no longer has
    # the traditional living-at-one penalty marker, including loaded saves.
    death_check = emit('challenge_boss_death_check', f'''
        push eax
        mov eax, dword ptr [edi+4]
        call {scope}
        test eax, eax
        pop eax
        jz original
        cmp dword ptr [edi+0xc8], 1
        ret
    original:
        jmp {symbols['izombie_boss_death_check']}
    ''')
    for site in (0x536242, 0x536516):
        patch(site, asm(f'call {death_check}', site), 7)

    no_penalty = emit('challenge_boss_no_health_penalty', f'''
        push eax
        mov eax, dword ptr [edi+4]
        call {scope}
        test eax, eax
        pop eax
        jz original
        cmp dword ptr [edi+0xc8], 1
        jmp 0x5365fc
    original:
        jmp {symbols['izombie_boss_head_min_damage']}
    ''')
    patch(0x5365f5, asm(f'jmp {no_penalty}', 0x5365f5), 7)
