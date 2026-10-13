"""Advanced I, Zombie plant distribution, gated by the saved ruleset marker.

Native grid enumeration still uses the traditional seed, column restrictions,
row restrictions and counts. Only an eligible cell's allocation is replaced.
NewPlant deliberately bypasses player upgrade prerequisites. Pumpkin shells
are a separate optional layer and never consume a normal plant slot.
"""

from challenge_mode import CHALLENGE_FIELD, CHALLENGE_MAGIC

EXCLUDED_SEEDS = frozenset((11, 16, 19, 24, 25, 27, 33, 35, 38, 43, 45, 47))
PUMPKIN_CHANCE = 20
FAMILY_CHANCE = 70

# The remaining ordinary plants have small, nonzero weights. Sunflower slots
# from the native formation remain sunflower, preserving the original budget.
PLANT_WEIGHTS = {
    0: 2, 1: 2, 2: 12, 3: 2, 4: 1, 5: 4, 6: 3, 7: 4, 8: 1,
    9: 2, 10: 4, 12: 5, 13: 2, 14: 9, 15: 10, 17: 2, 18: 8,
    20: 12, 21: 2, 22: 5, 23: 12, 26: 4, 28: 4, 29: 8, 31: 7,
    32: 2, 34: 2, 36: 3, 37: 6, 39: 14, 40: 18, 41: 3, 42: 14,
    44: 18, 46: 10, 48: 4,
}
FAMILY_WEIGHTS = {
    'pea': {0: 1, 5: 2, 7: 2, 18: 4, 28: 2, 40: 14},
    'nut': {3: 2, 23: 14},
    'pult': {32: 1, 34: 1, 39: 8, 44: 14},
    'instant': {2: 8, 4: 1, 6: 1, 14: 4, 15: 6, 17: 1, 20: 8},
    'shroom': {8: 1, 10: 2, 13: 1, 42: 12},
    'spike': {21: 2, 46: 12},
}
SEED_FAMILY = {
    **dict.fromkeys((0, 5, 7, 18, 28, 40), 'pea'),
    **dict.fromkeys((3, 23), 'nut'),
    **dict.fromkeys((32, 34, 39, 44), 'pult'),
    **dict.fromkeys((2, 4, 6, 14, 15, 17, 20), 'instant'),
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
    mimic, mimic_size = table('iz_challenge_imitater_pool',
                             {s: w for s, w in PLANT_WEIGHTS.items() if s != 48})
    families = {name: table('iz_challenge_plant_' + name, weights)
                for name, weights in FAMILY_WEIGHTS.items()}
    dispatch = '\n'.join(
        f'cmp ebx, {seed}\nje family_{family}'
        for seed, family in SEED_FAMILY.items())
    family_labels = '\n'.join(
        f'family_{name}:\nmov ecx, {address}\nmov edx, {size}\njmp family_roll'
        for name, (address, size) in families.items())
    picker = emit('iz_challenge_pick_plant', f'''
        # EAX=native seed. Return EAX=replacement; preserve nonvolatile regs.
        push ebx
        mov ebx, eax
        cmp ebx, 1
        je sunflower
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
        mov eax, {pool_size}
        call 0x5af400
        movzx eax, byte ptr [eax+{pool}]
        pop ebx
        ret
    sunflower:
        mov eax, 1
        pop ebx
        ret
    ''')
    imitater = emit('iz_challenge_pick_imitater_target', f'''
        mov eax, {mimic_size}
        call 0x5af400
        movzx eax, byte ptr [eax+{mimic}]
        ret
    ''')
    place = emit('iz_challenge_generate_cell', f'''
        # EDI=Challenge*, EBX=native seed, stack=(column,row); ret8.
        # Preserve all registers for both native allocation paths.
        pushad
        sub esp, 12
        mov eax, ebx
        call {picker}
        mov dword ptr [esp], eax
        mov dword ptr [esp+4], eax
        mov dword ptr [esp+8], -1
        cmp eax, 48
        jne allocate
        call {imitater}
        mov dword ptr [esp], eax
        mov dword ptr [esp+8], eax
    allocate:
        mov eax, dword ptr [esp+4]
        mov edx, dword ptr [esp+8]
        mov ecx, dword ptr [esp+48]
        mov ebp, dword ptr [esp+52]
        push edx
        push eax
        push ebp
        push ecx
        mov eax, dword ptr [edi+4]
        call 0x40ce20
        push eax
        mov eax, edi
        call 0x42a530
        # Ground spikes deliberately stay uncovered. The actual target is
        # also checked when the host is an untransformed imitater.
        cmp dword ptr [esp], 21
        je done
        cmp dword ptr [esp], 46
        je done
        mov eax, 100
        call 0x5af400
        cmp eax, {PUMPKIN_CHANCE}
        jae done
        # Respect existing layers and any native terrain restriction.
        mov eax, dword ptr [esp+52]
        mov ecx, dword ptr [esp+48]
        push 30
        push ecx
        push dword ptr [edi+4]
        call 0x40e020
        test eax, eax
        jnz done
        mov ecx, dword ptr [esp+48]
        mov edx, dword ptr [esp+52]
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
        add esp, 12
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
        # Validate the traditional seed before choosing its replacement.
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
        # Native weighted-grid selection has already chosen EBX=(col,row,w).
        # Its enumeration used the original seed and formation restrictions.
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
