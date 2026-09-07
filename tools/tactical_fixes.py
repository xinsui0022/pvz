"""Rear-emerging digger protection and persistent alternating bungee cost."""
def add_tactical(emit, patch, asm):
    digger = emit('chomper_rear_digger', '''
        pushad
        cmp dword ptr [edi+0x28], 0
        jne original
        cmp dword ptr [esi+0x24], 17
        jne original
        mov eax, dword ptr [esi+0x28]
        cmp eax, 32
        jb original
        cmp eax, 38
        ja original
        mov eax, dword ptr [edi+8]
        add eax, 40
        cmp dword ptr [esi+8], eax
        jg original
        mov eax, dword ptr [edi]
        call 0x4537d0
        test al, al
        jz original
        popad
        jmp 0x467884
    original:
        popad
        mov eax, dword ptr [esi+0x28]
        cmp eax, 37
        jmp 0x4676f0
    ''')
    # Inside FindTargetZombie's chomper branch, used both to start and finish
    # a bite. EDI=plant; ESI=zombie; all original targeting outside this gate.
    patch(0x4676ea, asm(f'jmp {digger}', 0x4676ea), 6)

    price = emit('bungee_alternating_price', '''
        mov ecx, dword ptr [0x6a9ec0]
        cmp eax, 66
        jne original
        cmp dword ptr [ecx+0x7f8], 61
        jl original
        cmp dword ptr [ecx+0x7f8], 70
        jg original
        mov ecx, dword ptr [ecx+0x768]
        test ecx, ecx
        jz fallback
        mov ecx, dword ptr [ecx+0x160]
        test ecx, ecx
        jz fallback
        mov eax, dword ptr [ecx+0xb8]
        and eax, 1
        imul eax, eax, 25
        add eax, 75
        ret
    fallback:
        mov ecx, dword ptr [0x6a9ec0]
    original:
        jmp 0x467b06
    ''')
    # Plant::GetCost feeds card text, affordability and actual deduction.
    patch(0x467b00, asm(f'jmp {price}', 0x467b00), 6)

    purchase = emit('bungee_purchase_complete', '''
        pushfd
        pushad
        mov eax, dword ptr [ebp]
        call 0x4537d0
        test al, al
        jz done
        mov eax, dword ptr [ebp+4]
        mov eax, dword ptr [eax+0x138]
        cmp dword ptr [eax+0x28], 66
        jne done
        xor dword ptr [ebp+0xb8], 1
    done:
        popad
        popfd
        mov eax, dword ptr [ebp+4]
        mov ecx, dword ptr [eax+0x138]
        jmp 0x42a433
    ''')
    # This point is reached only after legal placement, successful payment
    # (or the built-in free-placement cheat), and IZombiePlaceZombie returns.
    # +0xb8: tree dialogue index, unused in IZ, initialized to zero by the
    # Challenge constructor and serialized; stage changes never reset it.
    patch(0x42a42a, asm(f'jmp {purchase}', 0x42a42a), 9)
