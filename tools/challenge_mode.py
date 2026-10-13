"""Select I, Zombie rules before launch and keep each ruleset's save separate.

Only the challenge's unused, serialized rain counter is repurposed. Existing
traditional saves contain zero there and therefore retain traditional rules.
The mutable launch globals are emitted into a separate writable PE section by
the builder; strings and machine code remain in the executable read-only one.
"""

CHALLENGE_FIELD = 0xB4
CHALLENGE_MAGIC = 0x365A4349
CHALLENGE_STARTING_SUN = 150
CHALLENGE_BUNGEE_COST = 125
CHALLENGE_SAVE_MODE_OFFSET = 100
SELECTOR_DIALOG_ID = 100
PROFILE_DELETE_SAVE_NAME_RETURN = 0x4698DE


def add_challenge_mode(emit, patch, asm, symbols):
    pending = emit('iz_challenge_selection_pending', '.long 0')
    loading = emit('iz_challenge_selection_loading', '.long 0')

    def label(name, text):
        return emit(name, '.byte ' + ','.join(map(str, text.encode('gbk') + b'\0')))

    header = label('iz_challenge_selector_header', '选择我是僵尸模式')
    body = label('iz_challenge_selector_body',
                 '传统模式：沿用当前规则。\n挑战模式：开局150阳光，随机高级植物。\n两种模式的存档分别保存。')
    traditional = label('iz_challenge_selector_traditional', '传统模式')
    challenge = label('iz_challenge_selector_challenge', '挑战模式')

    predicate = emit('iz_challenge_mode_predicate', f'''
        # EAX=Board*. Return EAX=0/1; preserve ECX and EDX.
        push ecx
        push edx
        test eax, eax
        jz no
        mov ecx, dword ptr [eax+0x8c]
        test ecx, ecx
        jz no
        cmp dword ptr [ecx+0x7f8], 61
        jb no
        cmp dword ptr [ecx+0x7f8], 70
        ja no
        mov edx, dword ptr [eax+0x160]
        test edx, edx
        jz no
        cmp dword ptr [edx+{CHALLENGE_FIELD}], {CHALLENGE_MAGIC}
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

    selector = emit('iz_challenge_selector', f'''
        # ButtonDepress has EBX=mode-1 and EDI=ChallengeScreen*. Show the
        # modal game dialog while its original screen and focus still exist.
        pushfd
        pushad
        cmp ebx, 60
        jb other_mode
        cmp ebx, 69
        ja other_mode
        mov ebp, esp
        sub esp, 528
        and esp, -16
        fxsave [esp]
        fninit
        push 1
        push {challenge}
        push {traditional}
        push {body}
        push {header}
        push {SELECTOR_DIALOG_ID}
        push dword ptr [edi+0x138]
        call 0x4504b0
        cmp eax, 1000
        je choose_traditional
        cmp eax, 1001
        jne cancel
        mov dword ptr [{pending}], {CHALLENGE_MAGIC}
        jmp selected
    choose_traditional:
        mov dword ptr [{pending}], 0
    selected:
        fxrstor [esp]
        mov esp, ebp
        jmp resume
    cancel:
        # WaitForResult can end when the window closes, without a choice.
        fxrstor [esp]
        mov esp, ebp
        popad
        popfd
        jmp 0x42f7d9
    other_mode:
        mov dword ptr [{pending}], 0
    resume:
        popad
        popfd
        mov esi, dword ptr [edi+0x138]
        jmp 0x42f7a6
    ''')
    patch(0x42F7A0, asm(f'jmp {selector}', 0x42F7A0), 6)

    launch = emit('iz_challenge_launch_selected', f'''
        # Original stack: return address, mode, lookForSavedGame. Mark the
        # whole launch so a surviving old Board cannot choose its save name.
        mov dword ptr [{loading}], 1
        push dword ptr [esp+8]
        push dword ptr [esp+8]
        call 0x44f560
        mov dword ptr [{loading}], 0
        ret 8
    ''')
    patch(0x42F7B7, asm(f'call {launch}', 0x42F7B7), 5)

    initialize = emit('iz_challenge_mode_init', f'''
        # Challenge constructor: EDI=this, EBX=0. Keep the existing rescue
        # initialization at 0x41f218 and the bungee parity at +0xb8 intact.
        pushfd
        push eax
        mov dword ptr [edi+{CHALLENGE_FIELD}], ebx
        mov eax, dword ptr [edi]
        cmp dword ptr [eax+0x7f8], 61
        jb done
        cmp dword ptr [eax+0x7f8], 70
        ja done
        cmp dword ptr [{pending}], {CHALLENGE_MAGIC}
        jne done
        mov dword ptr [edi+{CHALLENGE_FIELD}], {CHALLENGE_MAGIC}
    done:
        pop eax
        popfd
        jmp 0x41f212
    ''')
    patch(0x41F20C, asm(f'jmp {initialize}', 0x41F20C), 6)

    starting_sun = emit('iz_challenge_starting_sun', f'''
        pushfd
        pushad
        mov eax, ebp
        call {predicate}
        test eax, eax
        jz traditional
        mov dword ptr [ebp+0x5560], {CHALLENGE_STARTING_SUN}
        jmp done
    traditional:
        mov dword ptr [ebp+0x5560], 150
    done:
        popad
        popfd
        jmp 0x40b073
    ''')
    # This assignment runs only for a new board's IZ initial balance. Loading
    # or advancing an endless stage does not execute Board::InitLevel again.
    patch(0x40B069, asm(f'jmp {starting_sun}', 0x40B069), 10)

    save_name = emit('iz_challenge_save_name', f'''
        # GetSavedGameName is a filename formatter. Change only its local
        # mode value; LawnApp::mGameMode and serialized board fields stay native.
        mov eax, dword ptr [esp+0x4c]
        pushfd
        push ecx
        push edx
        # DeleteUserFiles enumerates all native modes for its target profile;
        # it must not inherit whichever ruleset the current player selected.
        # The formatter's verified prologue leaves its return address at
        # original ESP+0x44, now +0x50 after the three pushes above.
        cmp dword ptr [esp+0x50], {PROFILE_DELETE_SAVE_NAME_RETURN}
        je done
        cmp eax, 61
        jb done
        cmp eax, 70
        ja done
        cmp dword ptr [{loading}], 0
        jne use_selection
        mov edx, dword ptr [0x6a9ec0]
        test edx, edx
        jz use_selection
        # Do not reinterpret generic requests for an unrelated game mode.
        cmp dword ptr [edx+0x7f8], eax
        jne done
        mov edx, dword ptr [edx+0x768]
        test edx, edx
        jz use_selection
        mov edx, dword ptr [edx+0x160]
        test edx, edx
        jz use_selection
        cmp dword ptr [edx+{CHALLENGE_FIELD}], {CHALLENGE_MAGIC}
        jne done
        jmp challenge
    use_selection:
        cmp dword ptr [{pending}], {CHALLENGE_MAGIC}
        jne done
    challenge:
        add eax, {CHALLENGE_SAVE_MODE_OFFSET}
    done:
        pop edx
        pop ecx
        popfd
        # The five overwritten bytes also include the native prologue's
        # push EBX. Replay it before the following output-string load, whose
        # stack offset assumes this saved register is already present.
        push ebx
        jmp 0x4568ed
    ''')
    patch(0x4568E8, asm(f'jmp {save_name}', 0x4568E8), 5)

    return predicate
