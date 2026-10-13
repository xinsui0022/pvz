"""Challenge I, Zombie plant behavior, using verified 1.0.0.1051 ABIs.

Both puzzles use the native cardboard drawing and idle animation treatment.
Challenge plants keep native weapons/armor; only reactive explosives change.
PuzzleNextStageClear already kills all grid items, including doom craters.
"""
from challenge_mode import CHALLENGE_MAGIC


COSMETIC_PREDICATE_SITES = (
    0x461257, 0x461539, 0x461F8B, 0x464616, 0x464CFC,
    0x465DEB, 0x4682CC,
)


def add_challenge_plants(emit, patch, asm, symbols):
    # EAX=Plant*, EAX=bool result; preserve ECX/EDX. Do not interpret B4
    # as challenge state outside the serialized I, Zombie game modes.
    scope = emit('challenge_plant_scope', f'''
        push ecx
        push edx
        test eax, eax
        jz no
        mov ecx, dword ptr [eax]
        test ecx, ecx
        jz no
        cmp dword ptr [ecx+0x7f8], 61
        jb no
        cmp dword ptr [ecx+0x7f8], 70
        ja no
        mov edx, dword ptr [eax+4]
        test edx, edx
        jz no
        mov edx, dword ptr [edx+0x160]
        test edx, edx
        jz no
        cmp dword ptr [edx+0xb4], {CHALLENGE_MAGIC}
        jne no
        mov eax, 1
        jmp done
    no:
        xor eax, eax
    done:
        pop edx
        pop ecx
        ret
    ''')

    # Leave the native IZ predicates (including the inlined magnet check)
    # intact. IZombieDrawPlant draws the actual body and its attachments;
    # it has no seed-type whitelist, so upgrades receive the same outline.
    native_setup = emit('challenge_native_plant_setup', '''
        mov ecx, dword ptr [eax]
        mov edx, dword ptr [ecx+0x820]
        jmp 0x42a538
    ''')

    # Old challenge saves contain moving idle reanimations. Freeze only
    # looping idle layers, preserving one-shot shooting/magnet/chomper/
    # imitater animations whose loopCount drives native combat transitions.
    # EAX=Plant*, preserve every register and flags, never reset combat state.
    idle = emit('challenge_cardboard_idle', '''
        pushfd
        pushad
        mov ebp, eax
        mov dword ptr [ebp+0xb0], 0
        cmp dword ptr [ebp+0xa4], 0
        je layers
        mov esi, ebp
        call 0x464390
    layers:
        lea esi, [ebp+0x94]
        mov edi, 4
    next:
        mov ecx, dword ptr [esi]
        test ecx, ecx
        jz advance
        mov eax, dword ptr [ebp]
        call 0x453cb0
        test eax, eax
        jz advance
        cmp dword ptr [eax+0x10], 0
        jne advance
        mov dword ptr [eax+8], 0
    advance:
        add esi, 4
        dec edi
        jnz next
        popad
        popfd
        ret
    ''')

    # EAX=Challenge*, stack Plant*, ret4. Wake mushrooms and arm the custom
    # explosives first, then execute native IZ setup to freeze all four
    # body/head layers, arm potato mines and suppress blinking.
    setup = emit('challenge_plant_setup', f'''
        pushfd
        pushad
        mov ebp, dword ptr [esp+40]
        mov eax, ebp
        call {scope}
        test al, al
        jz original
        push 0
        mov eax, ebp
        call 0x45e860
        mov eax, dword ptr [ebp+0x24]
        cmp eax, 2
        je waiting_bomb
        cmp eax, 20
        je waiting_bomb
        cmp eax, 14
        je waiting
        cmp eax, 15
        jne refresh
        jmp waiting
    waiting_bomb:
        # Both native bomb resources provide anim_idle. Keep its first frame
        # visible while armed; DoSpecial supplies the immediate blast effect.
        # PlayBodyReanim(rate0) preserves the old rate, so clear it explicitly.
        push 0
        push 0
        push 0x6580d4
        xor ecx, ecx
        mov eax, ebp
        call 0x45fd90
        mov ecx, dword ptr [ebp+0x94]
        mov eax, dword ptr [ebp]
        call 0x453cb0
        test eax, eax
        jz waiting
        mov dword ptr [eax+4], 0
        mov dword ptr [eax+8], 0
    waiting:
        mov dword ptr [ebp+0x50], 0
        mov dword ptr [ebp+0x3c], 0
    refresh:
        mov eax, dword ptr [ebp+4]
        mov eax, dword ptr [eax+0x160]
        push ebp
        call {native_setup}
        popad
        popfd
        ret 4
    original:
        popad
        popfd
        mov ecx, dword ptr [eax]
        mov edx, dword ptr [ecx+0x820]
        jmp 0x42a538
    ''')
    patch(0x42A530, asm(f'jmp {setup}', 0x42A530), 8)

    # Native imitater morph uses AddPlant, which does not invoke IZ setup.
    # Refresh the returned plant before its first update, preserving EAX and
    # the old imitater pointer in ESI for the native gray filter assignment.
    morph = emit('challenge_imitater_setup', f'''
        pushfd
        pushad
        mov ebp, eax
        call {scope}
        test al, al
        jz done
        mov eax, dword ptr [ebp+4]
        mov eax, dword ptr [eax+0x160]
        push ebp
        call 0x42a530
    done:
        popad
        popfd
        mov ecx, dword ptr [esi+0x138]
        jmp 0x466ba8
    ''')
    patch(0x466BA2, asm(f'jmp {morph}', 0x466BA2), 6)

    # EAX=Plant*, return EAX=bool, preserve all other registers. The native
    # rectangle/circle geometry and explosive damage eligibility are reused.
    # locals: iterator,count,Rect[4],centerX,centerY,radius,rowRange,threshold,kind.
    trigger = emit('challenge_explosive_trigger', '''
        pushad
        sub esp, 48
        mov ebp, eax
        mov dword ptr [esp], 0
        mov dword ptr [esp+4], 0
        mov eax, dword ptr [ebp+0x10]
        sar eax, 1
        add eax, dword ptr [ebp+8]
        mov dword ptr [esp+24], eax
        mov eax, dword ptr [ebp+0x14]
        sar eax, 1
        add eax, dword ptr [ebp+12]
        mov dword ptr [esp+28], eax
        mov eax, dword ptr [ebp+0x24]
        mov dword ptr [esp+44], eax
        mov dword ptr [esp+40], 1
        mov dword ptr [esp+32], 115
        mov dword ptr [esp+36], 1
        cmp eax, 2
        je scan
        cmp eax, 20
        je scan
        mov dword ptr [esp+40], 3
        mov dword ptr [esp+32], 250
        mov dword ptr [esp+36], 3
        cmp eax, 14
        je scan
        cmp eax, 15
        jne no
    scan:
        mov edx, dword ptr [ebp+4]
        mov esi, esp
        call 0x41c8f0
        test al, al
        jz no
        mov ebx, dword ptr [esp]
        cmp dword ptr [ebx+0xc8], 0
        jle scan
        cmp dword ptr [ebx+0x6c], -2
        je scan
        cmp dword ptr [ebx+0x6c], -3
        je scan
        cmp byte ptr [ebx+0xb8], 0
        jne scan
        mov eax, ebx
        call 0x534700
        test al, al
        jnz scan
        cmp dword ptr [esp+44], 14
        je counted
        mov esi, ebx
        push 127
        call 0x531a80
        test al, al
        jz scan
        mov eax, dword ptr [ebx+0x1c]
        sub eax, dword ptr [ebp+0x1c]
        cmp dword ptr [ebx+0x24], 25
        jne row_check
        xor eax, eax
    row_check:
        cmp dword ptr [esp+44], 20
        jne circular
        test eax, eax
        jnz scan
        jmp counted
    circular:
        mov ecx, dword ptr [esp+36]
        cmp eax, ecx
        jg scan
        neg ecx
        cmp eax, ecx
        jl scan
        lea edi, [esp+8]
        call 0x5320b0
        mov ecx, dword ptr [esp+24]
        mov edx, dword ptr [esp+28]
        lea eax, [esp+8]
        push dword ptr [esp+32]
        call 0x41c850
        add esp, 4
        test al, al
        jz scan
    counted:
        inc dword ptr [esp+4]
        mov eax, dword ptr [esp+4]
        cmp eax, dword ptr [esp+40]
        jb scan
        mov dword ptr [esp+76], 1
        jmp done
    no:
        mov dword ptr [esp+76], 0
    done:
        add esp, 48
        popad
        ret
    ''')

    # Native doom/ice automatically arm during UpdateAbilities, and native
    # cherry/jalapeno start with a countdown. Challenge waits for its trigger
    # and invokes the original effect exactly once, immediately.
    update = emit('challenge_plant_update', f'''
        pushfd
        pushad
        mov ebp, eax
        call {scope}
        test al, al
        jz original
        mov eax, ebp
        call {idle}
        mov eax, dword ptr [ebp+0x24]
        cmp eax, 2
        je explosive
        cmp eax, 20
        je explosive
        cmp eax, 14
        je explosive
        cmp eax, 15
        jne original
    explosive:
        mov dword ptr [ebp+0x50], 0
        cmp byte ptr [ebp+0x141], 0
        jne done
        cmp byte ptr [ebp+0x142], 0
        jne done
        cmp byte ptr [ebp+0x143], 0
        jne done
        cmp byte ptr [ebp+0x144], 0
        je done
        cmp dword ptr [ebp+0x134], 0
        jne done
        cmp dword ptr [ebp+0x40], 0
        jle done
        mov eax, ebp
        call {trigger}
        test al, al
        jz done
        push ebp
        call 0x4666a0
    done:
        popad
        popfd
        ret
    original:
        popad
        popfd
        push ecx
        push esi
        push edi
        mov edi, eax
        jmp 0x463155
    ''')
    patch(0x463150, asm(f'jmp {update}', 0x463150), 5)

    # Cherry/jalapeno Animate normally shakes their matrix every tick even
    # when the reanimation rate is zero. Armed cardboard bombs remain still;
    # continue at the native eaten-flash/damage/blink updates, not an early
    # return that would skip the plant's other visual bookkeeping.
    animate = emit('challenge_bomb_cardboard_animate', f'''
        pushfd
        pushad
        mov ebp, eax
        call {scope}
        test al, al
        jz original
        cmp dword ptr [ebp+0x24], 2
        je still
        cmp dword ptr [ebp+0x24], 20
        jne original
    still:
        mov dword ptr [ebp+0xc0], 0
        mov dword ptr [ebp+0xc4], 0
        popad
        popfd
        push edi
        mov edi, eax
        jmp 0x464e03
    original:
        popad
        popfd
        push edi
        mov edi, eax
        mov eax, dword ptr [edi+0x24]
        jmp 0x464db6
    ''')
    patch(0x464DB0, asm(f'jmp {animate}', 0x464DB0), 6)

    # Awake instant mushrooms normally cannot be chewed. Skip that native
    # immunity and the stock ice-shroom immediate-on-first-bite branch only
    # for the two challenge mushrooms; retain cadence/damage/sun code.
    edible = emit('challenge_mushroom_edible', f'''
        pushfd
        pushad
        mov eax, esi
        call {scope}
        test al, al
        jz original
        cmp dword ptr [esi+0x24], 14
        je chew
        cmp dword ptr [esi+0x24], 15
        jne original
    chew:
        popad
        popfd
        mov ebx, 1
        jmp 0x52fc7b
    original:
        popad
        popfd
        cmp byte ptr [esi+0x143], 0
        jmp 0x52fc2b
    ''')
    patch(0x52FC24, asm(f'jmp {edible}', 0x52FC24), 7)

    # This is exclusively the lethal-chew call site, not Plant::Die itself.
    # DoSpecial includes the original Die and crater logic, so tail-call it
    # instead of dying twice, and never detonate during stage cleanup.
    eaten = emit('challenge_mushroom_eaten', f'''
        pushfd
        pushad
        mov ebp, dword ptr [esp+40]
        mov eax, ebp
        call {scope}
        test al, al
        jz original
        cmp byte ptr [ebp+0x141], 0
        jne original
        cmp dword ptr [ebp+0x24], 14
        je detonate
        cmp dword ptr [ebp+0x24], 15
        jne original
    detonate:
        popad
        popfd
        jmp 0x4666a0
    original:
        popad
        popfd
        jmp 0x4679b0
    ''')
    patch(0x52FD55, asm(f'call {eaten}', 0x52FD55))
