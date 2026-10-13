"""Keep the traditional damage-based sun rules for challenge sun plants."""
from challenge_mode import CHALLENGE_FIELD, CHALLENGE_MAGIC


def emit_sun_family(emit):
    return emit('iz_challenge_sun_family', f'''
        # ESI=Plant*, EAX=predicate. Other registers remain unchanged.
        push ecx
        push edx
        cmp dword ptr [esi+0x24], 1
        je yes
        cmp dword ptr [esi+0x24], 9
        je candidate
        cmp dword ptr [esi+0x24], 41
        jne no
    candidate:
        mov ecx, dword ptr [esi]
        cmp dword ptr [ecx+0x7f8], 61
        jb no
        cmp dword ptr [ecx+0x7f8], 70
        ja no
        mov edx, dword ptr [esi+4]
        test edx, edx
        jz no
        mov edx, dword ptr [edx+0x160]
        test edx, edx
        jz no
        cmp dword ptr [edx+{CHALLENGE_FIELD}], {CHALLENGE_MAGIC}
        jne no
    yes:
        mov eax, 1
        jmp done
    no:
        xor eax, eax
    done:
        pop edx
        pop ecx
        ret
    ''')


def emit_double_sun_coin(emit, predicate):
    return emit('iz_challenge_sun_coin', f'''
        # Original AddCoin ABI: ECX=Board*, stack=(x,y,type,motion), ret16.
        # A challenge Twin Sunflower emits one extra identical 25-sun coin.
        # Restore the original arguments/registers before the normal call.
        pushfd
        pushad
        cmp dword ptr [esi+0x24], 41
        jne done
        call {predicate}
        test eax, eax
        jz done
        push dword ptr [esp+52]
        push dword ptr [esp+52]
        push dword ptr [esp+52]
        push dword ptr [esp+52]
        call 0x40cb10
    done:
        popad
        popfd
        jmp 0x40cb10
    ''')


def add_challenge_economy(emit, patch, asm, predicate, sun_coin):
    patch(0x42BA11, asm(f'call {sun_coin}', 0x42BA11))
    patch(0x52FCEB, asm(f'call {sun_coin}', 0x52FCEB))
    remaining = emit('iz_challenge_remaining_sun_family', f'''
        push eax
        call {predicate}
        cmp eax, 1
        pop eax
        push ebx
        push ebp
        jmp 0x42b9d6
    ''')
    patch(0x42B9D0, asm(f'jmp {remaining}', 0x42B9D0), 6)

    bite = emit('iz_challenge_bite_sun_family', f'''
        push eax
        call {predicate}
        test eax, eax
        pop eax
        jz 0x52fcf0
        mov edi, dword ptr [esi+0x40]
        jmp 0x52fcaf
    ''')
    patch(0x52FCA8, asm(f'jmp {bite}', 0x52FCA8), 7)
