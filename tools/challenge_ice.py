"""Challenge-only, serialized real ice trails across the next stage.

Board's native ice timers and extents remain the only persistent state. 8000
means ice laid during the current stage; 1..200 counts playing logic ticks in
the following stage. The small sentinel is safe for native alpha arithmetic.
Private bobsled travel ice is a separate zombie field and is never promoted.
"""

ICE_CURRENT_STAGE = 8000
ICE_NEXT_STAGE_TICKS = 200
ICE_MIN_X = 0x60C
ICE_TIMER = 0x624
ICE_START = 800


def add_challenge_ice(emit, patch, asm, symbols):
    predicate = symbols['iz_challenge_mode_predicate']
    trail = emit('iz_challenge_ice_trail', f'''
        # Native Zamboni writer: EAX=Board*, EDX=row, ESI=Zombie*.
        pushfd
        pushad
        mov ebp, eax
        call {predicate}
        test eax, eax
        jz original
        mov dword ptr [ebp+edx*4+{ICE_TIMER}], {ICE_CURRENT_STAGE}
        popad
        popfd
        jmp 0x52a8ba
    original:
        popad
        popfd
        jmp {symbols['izombie_ice_trail']}
    ''')
    patch(0x52A8AF, asm(f'jmp {trail}', 0x52A8AF), 11)

    tick = emit('iz_challenge_ice_tick', f'''
        # Native UpdateIce loop: EBX=Board*, EBP=&rowTimer, EDI=timer.
        pushfd
        push eax
        mov eax, ebx
        call {predicate}
        test eax, eax
        jz decrement
        cmp edi, {ICE_CURRENT_STAGE}
        je hold
        # Normalize active pre-v6.0.3 challenge saves without inventing ice.
        cmp edi, {ICE_NEXT_STAGE_TICKS}
        jle countdown
        mov edi, {ICE_CURRENT_STAGE}
        jmp hold
    countdown:
        cmp byte ptr [ebx+0x164], 0
        jne hold
        mov eax, dword ptr [ebx+0x8c]
        cmp dword ptr [eax+0x7fc], 3
        jne hold
    decrement:
        add edi, -1
    hold:
        pop eax
        popfd
        mov ecx, dword ptr [ebp+0x18]
        # Native resumes with test ecx, then stores EDI and performs the full
        # sparkle/fade/extent cleanup, including the zero timer case.
        jmp 0x414132
    ''')
    patch(0x41412C, asm(f'jmp {tick}', 0x41412C), 6)

    native_init = emit('iz_challenge_ice_native_init', '''
        # Separate callable prologue; keep the existing generation-init hook.
        push ebp
        mov ebp, esp
        and esp, -8
        jmp 0x42a896
    ''')
    initialize = emit('iz_challenge_ice_stage_init', f'''
        # Native IZombieInitLevel takes one callee-popped Challenge* argument.
        # Snapshot all six real lanes on this call's stack. Temporarily hide
        # inherited ice so native CanPlantAt can populate a complete board.
        pushfd
        pushad
        mov edi, dword ptr [esp+40]
        mov eax, dword ptr [edi+4]
        call {predicate}
        test eax, eax
        jz original
        sub esp, 52
        mov edx, dword ptr [edi+4]
        mov dword ptr [esp+48], edx
        xor ecx, ecx
    snapshot:
        mov eax, dword ptr [edx+ecx*4+{ICE_MIN_X}]
        mov dword ptr [esp+ecx*4], eax
        mov eax, dword ptr [edx+ecx*4+{ICE_TIMER}]
        cmp eax, {ICE_NEXT_STAGE_TICKS}
        jle save_timer
        mov eax, {ICE_NEXT_STAGE_TICKS}
    save_timer:
        mov dword ptr [esp+ecx*4+24], eax
        mov dword ptr [edx+ecx*4+{ICE_TIMER}], 0
        mov dword ptr [edx+ecx*4+{ICE_MIN_X}], {ICE_START}
        inc ecx
        cmp ecx, 6
        jb snapshot
        push edi
        call {native_init}
        mov edx, dword ptr [esp+48]
        xor ecx, ecx
    restore:
        mov eax, dword ptr [esp+ecx*4]
        mov dword ptr [edx+ecx*4+{ICE_MIN_X}], eax
        mov eax, dword ptr [esp+ecx*4+24]
        mov dword ptr [edx+ecx*4+{ICE_TIMER}], eax
        inc ecx
        cmp ecx, 6
        jb restore
        add esp, 52
        popad
        popfd
        ret 4
    original:
        popad
        popfd
        jmp {native_init}
    ''')
    patch(0x42A890, asm(f'jmp {initialize}', 0x42A890), 6)

    fire = emit('iz_challenge_ice_jalapeno', f'''
        # Native Jalapeno's completed attack has already pushed Plant*.
        # Preserve an existing trail; do not create map ice in an empty lane.
        pushfd
        pushad
        mov ebp, eax
        call {predicate}
        test eax, eax
        jz original
        jmp done
    original:
        mov dword ptr [ebp+edx*4+{ICE_TIMER}], 20
    done:
        popad
        popfd
        jmp 0x466990
    ''')
    patch(0x466985, asm(f'jmp {fire}', 0x466985), 11)
