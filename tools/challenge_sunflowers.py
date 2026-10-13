"""Upgrade challenge income plants before native initialization selects resources.

IZInitLevel allocates some fixed sunflowers inline, bypassing AddPlant and the
challenge random picker. Intercepting PlantInitialize covers those paths too.
The native Twin Sunflower definition retains the ordinary 300 health. Its
damage payout is doubled by the existing challenge economy hooks.
"""


def add_challenge_sunflowers(emit, patch, asm, symbols):
    scope = symbols['challenge_plant_scope']
    initialize = emit('iz_challenge_twin_initialize', f'''
        # EAX=row, ECX=column; stack=(Plant*, seed, imitater target).
        # Change the real init argument, not just mSeedType, so native code
        # creates the Twin Sunflower reanimation and its proper layers.
        pushfd
        pushad
        cmp dword ptr [esp+44], 1
        je check_scope
        cmp dword ptr [esp+44], 48
        jne done
        cmp dword ptr [esp+48], 1
        jne done
    check_scope:
        mov eax, dword ptr [esp+40]
        call {scope}
        test al, al
        jz done
        cmp dword ptr [esp+44], 1
        jne imitater
        mov dword ptr [esp+44], 41
        jmp done
    imitater:
        mov dword ptr [esp+48], 41
    done:
        popad
        popfd
        push ebp
        mov ebp, esp
        and esp, -8
        jmp 0x45db66
    ''')
    patch(0x45db60, asm(f'jmp {initialize}', 0x45db60), 6)
