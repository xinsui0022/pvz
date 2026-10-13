"""Challenge formations retain native roles and enforce live-board limits."""
from challenge_mode import CHALLENGE_FIELD, CHALLENGE_MAGIC

EXCLUDED_SEEDS = frozenset((9, 11, 16, 19, 24, 25, 27, 33, 35, 38, 43, 45, 47))
ONE_SHOT_SEEDS = frozenset((2, 4, 14, 15, 17, 20))
INSTANT_NATIVE_SEEDS = frozenset((4, 6, 17))
PUMPKIN_BLOCKED_SEEDS = ONE_SHOT_SEEDS | {12, 21, 46}
PUMPKIN_CHANCE = 20
FAMILY_CHANCE = 70
MAX_ICE_SHROOMS = 2
MAX_NORMAL_INSTANTS = 3
MAX_NORMAL_ROW_INSTANTS = 1
STAGE_PROFILE_FIELD = 0xA8
MAGNET_LIMIT_FIELD = 0xAC
PROFILE_NORMAL, PROFILE_INSTANT, PROFILE_STAR = range(3)

# Preserve the native income positions, upgrading every sunflower to a twin.
# Merge the former ordinary/twin weights so this does not add extra income slots.
# Ordinary roles cannot roll a disposable bomb, including through imitater.
PLANT_WEIGHTS = {
    0: 2, 3: 2, 5: 4, 6: 3, 7: 4, 8: 1,
    10: 4, 12: 3, 13: 2, 18: 8, 21: 2, 22: 5, 23: 12,
    26: 4, 28: 4, 29: 8, 31: 4, 32: 2, 34: 2, 36: 3, 37: 6,
    39: 14, 40: 18, 41: 5, 42: 14, 44: 18, 46: 10, 48: 4,
}
INSTANT_WEIGHTS = {2: 8, 4: 1, 6: 1, 14: 4, 15: 6, 17: 1, 20: 8}
INSTANT_GLOBAL_WEIGHTS = {**PLANT_WEIGHTS, **INSTANT_WEIGHTS}
ATTACK_WEIGHTS = {s: w for s, w in PLANT_WEIGHTS.items()
                  if s in (0, 5, 6, 7, 8, 10, 13, 18, 26, 28, 29,
                           32, 34, 39, 40, 42, 44, 46)}
FAMILY_WEIGHTS = {
    'pea': {0: 1, 5: 2, 7: 2, 18: 4, 28: 2, 40: 14},
    'nut': {3: 2, 23: 14},
    'pult': {32: 1, 34: 1, 39: 8, 44: 14},
    'instant': INSTANT_WEIGHTS,
    'shroom': {8: 1, 10: 2, 13: 1, 42: 12},
    'spike': {21: 2, 46: 12},
}
SEED_FAMILY = {
    **dict.fromkeys((0, 5, 7, 18, 28, 40), 'pea'),
    **dict.fromkeys((3, 23), 'nut'),
    **dict.fromkeys((32, 34, 39, 44), 'pult'),
    **dict.fromkeys(INSTANT_NATIVE_SEEDS, 'instant'),
    **dict.fromkeys((8, 10, 13, 42), 'shroom'),
    **dict.fromkeys((21, 46), 'spike'),
}


def _tickets(weights):
    return tuple(seed for seed, weight in weights.items() for _ in range(weight))


def add_challenge_generation(emit, patch, asm, symbols):
    def table(name, weights):
        tickets = _tickets(weights)
        return emit(name, '.byte ' + ','.join(map(str, tickets))), len(tickets)

    pool, pool_size = table('iz_challenge_plant_pool', PLANT_WEIGHTS)
    instant_pool, instant_size = table('iz_challenge_instant_pool', INSTANT_GLOBAL_WEIGHTS)
    mimic, mimic_size = table('iz_challenge_imitater_pool',
                             {s: w for s, w in PLANT_WEIGHTS.items() if s != 48})
    instant_mimic, instant_mimic_size = table('iz_challenge_instant_imitater_pool',
                             {s: w for s, w in INSTANT_GLOBAL_WEIGHTS.items() if s != 48})
    attack, attack_size = table('iz_challenge_attack_pool', ATTACK_WEIGHTS)
    families = {name: table('iz_challenge_plant_' + name, weights)
                for name, weights in FAMILY_WEIGHTS.items()}
    dispatch = '\n'.join(f'cmp ebx, {seed}\nje family_{family}'
                         for seed, family in SEED_FAMILY.items())
    instant_dispatch = '\n'.join(f'cmp ebx, {seed}\nje instant_global'
                                 for seed in sorted(INSTANT_NATIVE_SEEDS))
    family_labels = '\n'.join(
        f'family_{name}:\nmov ecx, {address}\nmov edx, {size}\njmp family_roll'
        for name, (address, size) in families.items())
    picker = emit('iz_challenge_pick_plant', f'''
        # EAX=native seed; return EAX=replacement, preserve nonvolatile regs.
        push ebx
        mov ebx, eax
        cmp ebx, 1
        je twin_sunflower
        cmp ebx, 41
        je preserve
        cmp ebx, 29
        je preserve
        cmp ebx, 31
        je preserve
        {dispatch}
        jmp global_roll
        {family_labels}
    family_roll:
        push ecx
        push edx
        mov eax, 100
        call 0x5af400
        pop edx
        pop ecx
        cmp eax, {FAMILY_CHANCE}
        jae global_roll
        mov eax, edx
        push ecx
        call 0x5af400
        pop ecx
        movzx eax, byte ptr [ecx+eax]
        pop ebx
        ret
    global_roll:
        {instant_dispatch}
        mov eax, {pool_size}
        call 0x5af400
        movzx eax, byte ptr [eax+{pool}]
        pop ebx
        ret
    instant_global:
        mov eax, {instant_size}
        call 0x5af400
        movzx eax, byte ptr [eax+{instant_pool}]
        pop ebx
        ret
    twin_sunflower:
        mov eax, 41
        pop ebx
        ret
    preserve:
        mov eax, ebx
        pop ebx
        ret
    ''')
    imitater = emit('iz_challenge_pick_imitater_target', f'''
        # EAX=native role; only disposable native roles may mimic a bomb.
        cmp eax, 4
        je instant
        cmp eax, 6
        je instant
        cmp eax, 17
        je instant
        mov eax, {mimic_size}
        call 0x5af400
        movzx eax, byte ptr [eax+{mimic}]
        ret
    instant:
        mov eax, {instant_mimic_size}
        call 0x5af400
        movzx eax, byte ptr [eax+{instant_mimic}]
        ret
    ''')
    fallback = emit('iz_challenge_pick_attack_fallback', f'''
        mov eax, {attack_size}
        call 0x5af400
        movzx eax, byte ptr [eax+{attack}]
        ret
    ''')
    instant_compare = '\n'.join(f'cmp eax, {s}\nje instant' for s in sorted(ONE_SHOT_SEEDS))
    scan = emit('iz_challenge_count_plants', f'''
        # EAX=Board*, EDX=row, ECX=out[instant,rowInstant,ice,magnet].
        # Match native PlantIterator high-water, ID-generation and dead checks.
        pushad
        mov edi, ecx
        mov ebx, edx
        mov dword ptr [edi], 0
        mov dword ptr [edi+4], 0
        mov dword ptr [edi+8], 0
        mov dword ptr [edi+12], 0
        mov esi, dword ptr [eax+0xac]
        mov ebp, dword ptr [eax+0xb0]
        imul ebp, ebp, 0x14c
        add ebp, esi
    loop:
        cmp esi, ebp
        jae done
        test dword ptr [esi+0x148], 0xffff0000
        jz next
        cmp byte ptr [esi+0x141], 0
        jne next
        mov eax, dword ptr [esi+0x24]
        cmp eax, 48
        jne resolved
        mov eax, dword ptr [esi+0x138]
    resolved:
        cmp eax, 31
        jne check_ice
        inc dword ptr [edi+12]
        jmp next
    check_ice:
        cmp eax, 14
        jne check_instant
        inc dword ptr [edi+8]
    check_instant:
        {instant_compare}
        jmp next
    instant:
        inc dword ptr [edi]
        cmp dword ptr [esi+0x1c], ebx
        jne next
        inc dword ptr [edi+4]
    next:
        add esi, 0x14c
        jmp loop
    done:
        popad
        ret
    ''')
    blocked_dispatch = '\n'.join(f'cmp dword ptr [esp], {s}\nje done'
                                 for s in sorted(PUMPKIN_BLOCKED_SEEDS))
    selected_instant_dispatch = '\n'.join(
        f'cmp eax, {s}\nje check_instant_limit' for s in sorted(ONE_SHOT_SEEDS))
    place = emit('iz_challenge_generate_cell', f'''
        # EDI=Challenge*, EBX=native seed, stack=(column,row); ret8.
        # Locals: actual type, allocated seed, mimic, 4 live-board counts.
        pushad
        sub esp, 28
        mov eax, ebx
        call {picker}
        mov dword ptr [esp], eax
        mov dword ptr [esp+4], eax
        mov dword ptr [esp+8], -1
        cmp eax, 48
        jne count_existing
        mov eax, ebx
        call {imitater}
        mov dword ptr [esp], eax
        mov dword ptr [esp+8], eax
    count_existing:
        mov eax, dword ptr [edi+4]
        mov edx, dword ptr [esp+68]
        lea ecx, [esp+12]
        call {scan}
        # Keep sunflower budget; first eligible other cell supplies a magnet.
        cmp ebx, 1
        je allocate
        cmp ebx, 41
        je allocate
        cmp dword ptr [esp+24], 0
        je force_magnet
        mov eax, dword ptr [esp]
        cmp eax, 31
        jne check_ice
        mov ecx, dword ptr [edi+{MAGNET_LIMIT_FIELD}]
        cmp ecx, 1
        jae magnet_limit
        mov ecx, 1
    magnet_limit:
        cmp dword ptr [esp+24], ecx
        jae attack_fallback
        jmp allocate
    check_ice:
        cmp eax, 14
        jne check_instant
        cmp dword ptr [esp+20], {MAX_ICE_SHROOMS}
        jae attack_fallback
    check_instant:
        {selected_instant_dispatch}
        jmp allocate
    check_instant_limit:
        cmp dword ptr [edi+{STAGE_PROFILE_FIELD}], {PROFILE_INSTANT}
        je allocate
        cmp dword ptr [esp+12], {MAX_NORMAL_INSTANTS}
        jae attack_fallback
        cmp dword ptr [esp+16], {MAX_NORMAL_ROW_INSTANTS}
        jae attack_fallback
        jmp allocate
    force_magnet:
        mov eax, 31
        jmp replace_selected
    attack_fallback:
        # One bounded draw, with no retry loop even under adversarial RNG.
        call {fallback}
    replace_selected:
        mov dword ptr [esp], eax
        mov dword ptr [esp+4], eax
        mov dword ptr [esp+8], -1
    allocate:
        mov eax, dword ptr [esp+4]
        mov edx, dword ptr [esp+8]
        mov ecx, dword ptr [esp+64]
        mov ebp, dword ptr [esp+68]
        push edx
        push eax
        push ebp
        push ecx
        mov eax, dword ptr [edi+4]
        call 0x40ce20
        push eax
        mov eax, edi
        call 0x42a530
        {blocked_dispatch}
        mov eax, 100
        call 0x5af400
        cmp eax, {PUMPKIN_CHANCE}
        jae done
        mov eax, dword ptr [esp+68]
        mov ecx, dword ptr [esp+64]
        push 30
        push ecx
        push dword ptr [edi+4]
        call 0x40e020
        test eax, eax
        jnz done
        mov ecx, dword ptr [esp+64]
        mov edx, dword ptr [esp+68]
        push -1
        push 30
        push edx
        push ecx
        mov eax, dword ptr [edi+4]
        call 0x40ce20
        push eax
        mov eax, edi
        call 0x42a530
    done:
        add esp, 28
        popad
        ret 8
    ''')
    square = emit('iz_challenge_place_square', f'''
        pushfd
        pushad
        cmp dword ptr [edi+{CHALLENGE_FIELD}], {CHALLENGE_MAGIC}
        jne original
        mov eax, dword ptr [edi]
        cmp dword ptr [eax+0x7f8], 61
        jb original
        cmp dword ptr [eax+0x7f8], 70
        ja original
        mov eax, dword ptr [esp+44]
        mov ecx, dword ptr [esp+40]
        push ebx
        push ecx
        push dword ptr [edi+4]
        call 0x40e020
        test eax, eax
        jnz done
        push dword ptr [esp+44]
        push dword ptr [esp+44]
        call {place}
    done:
        popad
        popfd
        ret 8
    original:
        popad
        popfd
        push ecx
        mov eax, dword ptr [esp+8]
        jmp 0x42a665
    ''')
    patch(0x42a660, asm(f'jmp {square}', 0x42a660), 5)

    batch = emit('iz_challenge_place_batch_cell', f'''
        pushfd
        pushad
        cmp dword ptr [ecx+{CHALLENGE_FIELD}], {CHALLENGE_MAGIC}
        jne original
        mov eax, dword ptr [ecx]
        cmp dword ptr [eax+0x7f8], 61
        jb original
        cmp dword ptr [eax+0x7f8], 70
        ja original
        push edi
        push ebp
        mov edi, ecx
        mov ebx, dword ptr [esp+0x2dc]
        call {place}
        popad
        popfd
        mov dword ptr [ebx+8], 0
        jmp 0x42a874
    original:
        popad
        popfd
        lea esi, [eax+0xac]
        call 0x41de80
        jmp 0x42a843
    ''')
    patch(0x42a838, asm(f'jmp {batch}', 0x42a838), 11)

    initialize = emit('iz_challenge_generation_init', f'''
        mov edi, dword ptr [ebp+8]
        xor ebx, ebx
        pushfd
        pushad
        cmp dword ptr [edi+{CHALLENGE_FIELD}], {CHALLENGE_MAGIC}
        jne done
        mov eax, dword ptr [edi]
        cmp dword ptr [eax+0x7f8], 61
        jb done
        cmp dword ptr [eax+0x7f8], 70
        ja done
        mov dword ptr [edi+{STAGE_PROFILE_FIELD}], {PROFILE_NORMAL}
        mov dword ptr [edi+{MAGNET_LIMIT_FIELD}], 1
    done:
        popad
        popfd
        jmp 0x42a8a1
    ''')
    patch(0x42a89c, asm(f'jmp {initialize}', 0x42a89c), 5)

    formation = emit('iz_challenge_generation_formation', f'''
        # EAX=row, stack=(Challenge*, nativeSeed, count) before native prologue.
        pushfd
        pushad
        mov edi, dword ptr [esp+40]
        cmp dword ptr [edi+{CHALLENGE_FIELD}], {CHALLENGE_MAGIC}
        jne done
        mov ecx, dword ptr [edi]
        cmp dword ptr [ecx+0x7f8], 61
        jb done
        cmp dword ptr [ecx+0x7f8], 70
        ja done
        mov ebx, dword ptr [esp+44]
        mov ecx, dword ptr [esp+48]
        cmp ebx, 31
        jne special
        cmp ecx, dword ptr [edi+{MAGNET_LIMIT_FIELD}]
        jbe done
        mov dword ptr [edi+{MAGNET_LIMIT_FIELD}], ecx
        jmp done
    special:
        cmp eax, -1
        jne done
        cmp ebx, 4
        jne star
        cmp ecx, 4
        jb done
        mov dword ptr [edi+{STAGE_PROFILE_FIELD}], {PROFILE_INSTANT}
        jmp done
    star:
        cmp ebx, 29
        jne spike
        cmp ecx, 4
        jb done
        jmp mark_star
    spike:
        cmp ebx, 21
        jne done
        cmp ecx, 9
        jb done
    mark_star:
        mov dword ptr [edi+{STAGE_PROFILE_FIELD}], {PROFILE_STAR}
    done:
        popad
        popfd
        sub esp, 0x298
        jmp 0x42a6c6
    ''')
    patch(0x42a6c0, asm(f'jmp {formation}', 0x42a6c0), 6)
