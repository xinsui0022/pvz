"""Execute real challenge ice hooks, native expiry and stage placement ABI."""
import unittest
from test_machine_code import (
    VM, MANIFEST, ORIGINAL, asm, APP, BOARD, ZOMBIE, CHALLENGE, PLANT,
    PROFILE, STACK, STOP, REGS, UC_X86_REG_EAX, UC_X86_REG_EBX,
    UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESI, UC_X86_REG_EDI,
    UC_X86_REG_EBP, UC_X86_REG_ESP, UC_X86_REG_EFLAGS, UC_X86_REG_EIP,
)
from challenge_mode import CHALLENGE_MAGIC, CHALLENGE_FIELD
from challenge_ice import (ICE_CURRENT_STAGE,
                           ICE_NEXT_STAGE_TICKS, ICE_MIN_X, ICE_TIMER, ICE_START)


class ChallengeIceTests(unittest.TestCase):
    def field(self, challenge=True, mode=70):
        vm = VM(mode=mode)
        vm.w(BOARD + 0x8C, APP)
        vm.w(APP + 0x7FC, 3)
        vm.w(CHALLENGE + CHALLENGE_FIELD, CHALLENGE_MAGIC if challenge else 0)
        symbols = {name: int(address, 16) for name, address in MANIFEST['symbols'].items()}
        vm.symbols = symbols
        for row in range(6):
            vm.w(BOARD + ICE_MIN_X + 4 * row, ICE_START)
        return vm

    def set_lane(self, vm, row, timer, extent):
        vm.w(BOARD + ICE_TIMER + 4 * row, timer)
        vm.w(BOARD + ICE_MIN_X + 4 * row, extent)

    def native_timer_step(self, vm, row=2):
        vm.reg(UC_X86_REG_ESP, STACK)
        vm.reg(UC_X86_REG_EBX, BOARD)
        vm.reg(UC_X86_REG_EBP, BOARD + ICE_TIMER + 4 * row)
        vm.reg(UC_X86_REG_EDI, vm.r(BOARD + ICE_TIMER + 4 * row))
        vm.run(0x41412C, 0x414137)
        return vm.r(BOARD + ICE_TIMER + 4 * row)

    def test_zamboni_ice_and_native_traditional_duration_are_scoped(self):
        for mode, challenge, expected in ((70, True, ICE_CURRENT_STAGE),
                (61, True, ICE_CURRENT_STAGE), (70, False, 4500),
                (60, True, 3000), (71, True, 3000), (28, True, 3000)):
            vm = self.field(challenge, mode)
            vm.reg(UC_X86_REG_EAX, BOARD)
            vm.reg(UC_X86_REG_EDX, 2)
            vm.reg(UC_X86_REG_ESI, ZOMBIE)
            before = [vm.reg(r) for r in REGS]
            flags = vm.reg(UC_X86_REG_EFLAGS)
            vm.run(0x52A8AF, 0x52A8BA)
            self.assertEqual(vm.r(BOARD + ICE_TIMER + 8), expected)
            self.assertEqual([vm.reg(r) for r in REGS], before)
            if challenge and 61 <= mode <= 70:
                self.assertEqual(vm.reg(UC_X86_REG_EFLAGS), flags)
            self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK)

    def test_current_stage_never_melts_and_older_challenge_save_migrates(self):
        for timer in (ICE_CURRENT_STAGE, 4500, 450, 201):
            vm = self.field()
            self.set_lane(vm, 2, timer, 25)
            for _ in range(100):
                self.assertEqual(self.native_timer_step(vm), ICE_CURRENT_STAGE)
                self.assertEqual(vm.r(BOARD + ICE_MIN_X + 8), 25)
        vm = self.field(False)
        self.set_lane(vm, 2, 4500, 100)
        self.assertEqual(self.native_timer_step(vm), 4499)

    def test_next_stage_only_counts_playing_unpaused_ticks_and_serializes(self):
        vm = self.field()
        self.set_lane(vm, 2, ICE_NEXT_STAGE_TICKS, 80)
        for scene, paused in ((2, 0), (1, 0), (3, 1), (4, 0)):
            vm.w(APP + 0x7FC, scene)
            vm.u.mem_write(BOARD + 0x164, bytes([paused]))
            self.assertEqual(self.native_timer_step(vm), ICE_NEXT_STAGE_TICKS)
        vm.w(APP + 0x7FC, 3)
        vm.u.mem_write(BOARD + 0x164, b'\0')
        for remaining in range(199, 100, -1):
            self.assertEqual(self.native_timer_step(vm), remaining)
        loaded = self.field()
        loaded.u.mem_write(BOARD + ICE_MIN_X, bytes(vm.u.mem_read(BOARD + ICE_MIN_X, 48)))
        for remaining in range(100, 0, -1):
            self.assertEqual(self.native_timer_step(loaded), remaining)
        self.assertEqual(loaded.r(BOARD + ICE_MIN_X + 8), 80)
        # Execute the entire native zero-timer path: it must clear the true
        # minX extent and return with the original ret-4 calling convention.
        loaded.w(APP + 0x820, PROFILE)
        loaded.w(PROFILE, PROFILE)
        loaded.reg(UC_X86_REG_ESP, STACK)
        loaded.w(STACK, STOP)
        loaded.w(STACK + 4, BOARD)
        loaded.run(0x414100)
        self.assertEqual(loaded.r(BOARD + ICE_TIMER + 8), 0)
        self.assertEqual(loaded.r(BOARD + ICE_MIN_X + 8), ICE_START)
        self.assertEqual(loaded.reg(UC_X86_REG_ESP), STACK + 8)

    def test_stage_init_temporarily_hides_actual_ice_and_restores_exact_extents(self):
        vm = self.field()
        lanes = ((0, 0, 800), (1, ICE_CURRENT_STAGE, 25), (2, 4500, 420),
                 (3, 199, 150), (4, 0, 800), (5, ICE_CURRENT_STAGE, 640))
        for row, timer, extent in lanes:
            self.set_lane(vm, row, timer, extent)
        def generation(v):
            self.assertEqual(v.r(v.reg(UC_X86_REG_ESP) + 4), CHALLENGE)
            self.assertEqual([v.r(BOARD + ICE_TIMER + row * 4) for row in range(6)], [0] * 6)
            self.assertEqual([v.r(BOARD + ICE_MIN_X + row * 4) for row in range(6)], [800] * 6)
            v.w(CHALLENGE + 0x60, 0)
            v.w(CHALLENGE + 0xA8, 2)
            v.w(CHALLENGE + 0xAC, 1)
            for reg in REGS:
                v.reg(reg, 0xABCDEF)
            v.ret(4)
        vm.stubs[vm.symbols['iz_challenge_ice_native_init']] = generation
        vm.w(STACK + 4, CHALLENGE)
        before = [vm.reg(r) for r in REGS]
        flags = vm.reg(UC_X86_REG_EFLAGS)
        vm.run(0x42A890)
        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK + 8)
        self.assertEqual([vm.reg(r) for r in REGS], before)
        self.assertEqual(vm.reg(UC_X86_REG_EFLAGS), flags)
        self.assertEqual(vm.r(CHALLENGE + 0xA8), 2)
        for row, timer, extent in lanes:
            self.assertEqual(vm.r(BOARD + ICE_MIN_X + row * 4), extent)
            self.assertEqual(vm.r(BOARD + ICE_TIMER + row * 4), min(timer, 200))

    def test_traditional_and_other_modes_keep_native_init_fields_prologue(self):
        for mode, challenge in ((70, False), (60, True), (71, True)):
            vm = self.field(challenge, mode)
            self.set_lane(vm, 2, 4500, 25)
            vm.w(STACK + 4, CHALLENGE)
            vm.run(0x42A890, 0x42A896)
            self.assertEqual(vm.r(BOARD + ICE_TIMER + 8), 4500)
            self.assertEqual(vm.r(BOARD + ICE_MIN_X + 8), 25)
            self.assertEqual(vm.reg(UC_X86_REG_EBP), STACK - 4)
            self.assertEqual(vm.reg(UC_X86_REG_ESP), (STACK - 4) & ~7)

    def test_real_stage_generation_is_not_blocked_by_inherited_full_ice_lanes(self):
        from test_challenge_generation import ChallengeGenerationTests
        from collections import Counter
        vm = self.field(mode=70)
        generation = ChallengeGenerationTests()
        generation.allocation(vm, magnet=False)
        vm.u.mem_map(0x3800000, 0x10000)
        vm.brains = 0
        def brain(v):
            self.assertEqual(v.reg(UC_X86_REG_ESI), BOARD + 0x11C)
            ptr = 0x3800000 + vm.brains * 0x100
            vm.brains += 1
            v.ret(eax=ptr)
        vm.stubs[0x41E1C0] = brain
        original_check = vm.stubs[0x40E020]
        def frozen_reject(v):
            row = v.reg(UC_X86_REG_EAX)
            column = v.r(v.reg(UC_X86_REG_ESP) + 8)
            timer = v.r(BOARD + ICE_TIMER + row * 4)
            self.assertEqual(timer, 0)
            self.assertEqual(v.r(BOARD + ICE_MIN_X + row * 4), ICE_START)
            original_check(v)
            if timer or any(p[:2] == (column, row) for p in vm.created):
                v.reg(UC_X86_REG_EAX, 1)
        vm.stubs[0x40E020] = frozen_reject
        vm.stubs[vm.symbols['iz_challenge_pick_plant']] = lambda v: v.ret(eax=40)
        # Native formation/grid draws select first available cells. Cosmetic
        # pumpkin chance is forced off, so the main placement count is exact.
        vm.stubs[0x5AF400] = lambda v: v.ret(eax=99 if v.reg(UC_X86_REG_EAX) == 100 else 0)
        vm.w(CHALLENGE + 0x6C, 0)
        for row in range(5):
            self.set_lane(vm, row, ICE_CURRENT_STAGE, 25 + row * 20)
        vm.w(STACK + 4, CHALLENGE)
        # Run native init, brain allocation, the native formation batches,
        # challenge placement, and the real wrapper restoration end to end.
        vm.u.emu_start(0x42A890, STOP, count=200000)
        self.assertEqual(vm.reg(UC_X86_REG_EIP), STOP)
        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK + 8)
        self.assertEqual(vm.brains, 5)
        self.assertEqual(len(vm.created), 25)
        self.assertEqual(len({p[:2] for p in vm.created}), 25)
        self.assertEqual(Counter(p[2] for p in vm.created)[31], 1)
        for row in range(5):
            self.assertEqual(vm.r(BOARD + ICE_TIMER + row * 4), 200)
            self.assertEqual(vm.r(BOARD + ICE_MIN_X + row * 4), 25 + row * 20)

    def test_new_ice_overrides_inherited_expiry_without_other_lane_changes(self):
        vm = self.field()
        self.set_lane(vm, 2, 2, 25)
        self.set_lane(vm, 3, 150, 150)
        vm.reg(UC_X86_REG_EAX, BOARD)
        vm.reg(UC_X86_REG_EDX, 2)
        vm.reg(UC_X86_REG_ESI, ZOMBIE)
        vm.run(0x52A8AF, 0x52A8BA)
        self.assertEqual(self.native_timer_step(vm, 2), ICE_CURRENT_STAGE)
        self.assertEqual(self.native_timer_step(vm, 3), 149)
        self.assertEqual(vm.r(BOARD + ICE_MIN_X + 8), 25)

    def test_jalapeno_keeps_challenge_ice_and_empty_rows_do_not_acquire_ice(self):
        for challenge, mode, timer, expected in (
                (True, 70, ICE_CURRENT_STAGE, ICE_CURRENT_STAGE),
                (True, 61, 150, 150), (True, 70, 0, 0),
                (False, 70, ICE_CURRENT_STAGE, 20), (True, 60, 4500, 20)):
            vm = self.field(challenge, mode)
            self.set_lane(vm, 2, timer, 25 if timer else ICE_START)
            vm.reg(UC_X86_REG_EAX, BOARD)
            vm.reg(UC_X86_REG_EDX, 2)
            vm.reg(UC_X86_REG_EDI, PLANT)
            vm.reg(UC_X86_REG_ESP, STACK - 4)
            vm.w(STACK - 4, PLANT)
            before = [vm.reg(r) for r in REGS]
            vm.run(0x466985, 0x466990)
            self.assertEqual(vm.r(BOARD + ICE_TIMER + 8), expected)
            self.assertEqual([vm.reg(r) for r in REGS], before)
            self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK - 4)
            self.assertEqual(vm.r(STACK - 4), PLANT)

    def test_hook_sites_cover_whole_original_instructions(self):
        import pefile
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        pe = pefile.PE(data=ORIGINAL)
        dis = Cs(CS_ARCH_X86, CS_MODE_32)
        for address, size in ((0x52A8AF, 11), (0x41412C, 6),
                              (0x42A890, 6), (0x466985, 11)):
            instructions = list(dis.disasm(pe.get_data(address - 0x400000, size), address))
            self.assertEqual(sum(i.size for i in instructions), size)


if __name__ == '__main__':
    unittest.main()
