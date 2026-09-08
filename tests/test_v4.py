"""Execute real V4 hooks, native movement/lookup and explosion geometry."""
from test_machine_code import *
del PatchTests
from capstone import Cs, CS_ARCH_X86, CS_MODE_32


def symbol(name):
    return int(MANIFEST['symbols'][name], 16)


def wf(vm, address, value):
    vm.u.mem_write(address, struct.pack('<f', value))


def rf(vm, address):
    return struct.unpack('<f', vm.u.mem_read(address, 4))[0]


class V4Tests(unittest.TestCase):
    def test_new_hooks_overwrite_complete_instructions(self):
        pe = pefile.PE(data=ORIGINAL)
        dis = Cs(CS_ARCH_X86, CS_MODE_32)
        for site in (0x522fe8, 0x526c7f, 0x52aa40, 0x528a17):
            hook = next(h for h in MANIFEST['hooks'] if int(h['va'], 16) == site)
            self.assertEqual(sum(i.size for i in dis.disasm(
                pe.get_data(site-0x400000, hook['length']), site)), hook['length'])

    def test_early_explosion_probability_and_native_timer(self):
        for mode in (0, 60, 61, 70, 71):
            vm = VM(mode=mode)
            bound = 5 if 61 <= mode <= 70 else 20
            early = 0
            for roll in range(bound):
                vm.reg(UC_X86_REG_ESP, STACK)
                vm.reg(UC_X86_REG_EDI, ZOMBIE)
                vm.reg(UC_X86_REG_ESI, 600)
                wf(vm, ZOMBIE+0x34, 0.5)
                vm.w(STACK+0x18, 600)
                def rng(v, roll=roll):
                    self.assertEqual(v.reg(UC_X86_REG_EAX), bound)
                    v.ret(eax=roll)
                vm.stubs[0x5af400] = rng
                vm.run(0x522fe8, 0x523014)
                self.assertEqual(vm.r(ZOMBIE+0x68), 800 if roll == 0 else 2400)
                early += vm.r(ZOMBIE+0x68) == 800
                self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK)
            self.assertEqual(early, 1)

    def blast(self, vm, x, y):
        vm.reg(UC_X86_REG_ESP, STACK)
        vm.w(STACK, STOP)
        vm.w(STACK+4, x)
        vm.reg(UC_X86_REG_ESI, ZOMBIE)
        vm.reg(UC_X86_REG_EDI, BOARD)
        vm.reg(UC_X86_REG_EBX, y)
        before = [vm.reg(r) for r in REGS]
        def plants(v):
            self.assertEqual(v.r(v.reg(UC_X86_REG_ESP)+4), x)
            self.assertEqual(v.reg(UC_X86_REG_EBX), y)
            self.assertEqual(v.reg(UC_X86_REG_EDI), BOARD)
            v.events.append('plants')
            v.ret(4)
        vm.stubs[0x41cbf0] = plants
        vm.run(symbol('jack_blast_brains'))
        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK+8)
        self.assertEqual([vm.reg(r) for r in REGS], before)

    def brain_vm(self, mode=70):
        vm = VM(mode=mode)
        for row in range(5):
            ptr = BRAIN+row*0xec
            wf(vm, ptr+0x24, 40)
            wf(vm, ptr+0x28, 100+row*100)
        def get(v):
            self.assertEqual(v.reg(UC_X86_REG_EDX), BOARD)
            self.assertEqual(v.reg(UC_X86_REG_EBX), 0)
            self.assertEqual(v.r(v.reg(UC_X86_REG_ESP)+4), 12)
            v.ret(4, BRAIN+v.reg(UC_X86_REG_EDI)*0xec)
        def squish(v):
            brain = v.reg(UC_X86_REG_EAX)
            self.assertEqual(v.r(v.reg(UC_X86_REG_ESP)+4), CHALLENGE)
            vm.events.append(('brain', (brain-BRAIN)//0xec))
            vm.w(brain+0xc, 29)
            v.ret(4)
        vm.stubs[0x408e40] = get
        vm.stubs[0x42ba30] = squish
        return vm

    def test_brain_blast_radius_edges_adjacent_rows_and_single_score(self):
        for mode in (60, 61, 70, 71):
            for x, y, rows in [(162, 115, [0]), (163, 115, []),
                               (72, 190, [0, 1]), (40, 390, [2, 3]),
                               (126, 172, [0, 1]), (500, 115, [])]:
                with self.subTest(mode=mode, x=x, y=y):
                    vm = self.brain_vm(mode)
                    self.blast(vm, x, y)
                    self.blast(vm, x, y)
                    expected = rows if 61 <= mode <= 70 else []
                    self.assertEqual([e[1] for e in vm.events if isinstance(e, tuple)], expected)
                    self.assertEqual(vm.events.count('plants'), 2)

    def test_dead_or_missing_brains(self):
        vm = self.brain_vm()
        vm.u.mem_write(BRAIN+0x20, b'\1')
        self.blast(vm, 50, 100)
        self.assertFalse(any(isinstance(e, tuple) for e in vm.events))
        vm.stubs[0x408e40] = lambda v: v.ret(4, 0)
        self.blast(vm, 50, 115)

    def test_hypnotized_blast_keeps_original_branch(self):
        for mind in (0, 1):
            vm = self.brain_vm()
            vm.w(ZOMBIE+0xb8, mind)
            vm.reg(UC_X86_REG_ESI, ZOMBIE)
            vm.reg(UC_X86_REG_EDI, 50)
            vm.reg(UC_X86_REG_EBX, 100)
            vm.stub(0x41d8a0, 'zombies', 32)
            vm.stub(0x41cbf0, 'plants', 4)
            vm.run(0x526c37, 0x526c84)
            self.assertEqual(('brain', 0) in vm.events, not mind)
            self.assertEqual('plants' in vm.events, not mind)
            self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK)

    def team(self, binary=PATCHED, mode=70):
        vm = VM(binary=binary, mode=mode)
        vm.w(BOARD+0x90, ZOMBIE)
        vm.w(BOARD+0x98, 10)
        vm.w(APP+0x820, REANIM)
        vm.w(REANIM+8, REANIM+0x200)
        vm.w(REANIM+0x200, REANIM+0x400)
        vm.w(REANIM+0x208, 10)
        ptrs = [ZOMBIE+i*0x15c for i in range(5)]
        for i, ptr in enumerate(ptrs):
            vm.w(ptr, APP)
            vm.w(ptr+4, BOARD)
            vm.w(ptr+0x24, 8 if i == 0 else 9)
            vm.w(ptr+0x28, 44)
            vm.w(ptr+0x158, 0x10000+i)
            vm.w(ptr+0x118, 0x10000+i)
            vm.w(REANIM+0x400+i*0xa0+0x9c, 0x10000+i)
            vm.w(ptr+0xf0, 0 if i == 0 else 0x10000)
            wf(vm, ptr+0x11c, 1)
            wf(vm, ptr+0x34, 0.45)
            offset = (0, 0, 0, -100, 100)[i]
            wf(vm, ptr+0x2c, 400.75+offset)
            vm.w(ptr+8, int(400.75+offset))
            if i:
                vm.w(ZOMBIE+0xf4+(i-1)*4, 0x10000+i)
        # Rendering stubs expose deliberately different _ground velocities;
        # all movement, stop predicates, direction, IDs and transforms are real.
        vm.stub(0x4732c0, 'ground', 4, 1)
        # Use a separate trampoline: STOP is the test's return address.
        def velocity(v):
            i = (v.reg(UC_X86_REG_EAX)-(REANIM+0x400))//0xa0
            wf(v, APP+0xe000, (0.45, 0.52, 0.61, 0.50, 0.72)[i])
            v.u.mem_write(STOP+0x100, asm(f'fld dword ptr [{APP+0xe000}]; ret', STOP+0x100))
            v.reg(UC_X86_REG_EIP, STOP+0x100)
        vm.stubs[0x4738d0] = velocity
        return vm, ptrs

    def walk(self, vm, ptr):
        vm.reg(UC_X86_REG_ESP, STACK)
        vm.w(STACK, STOP)
        vm.reg(UC_X86_REG_ESI, ptr)
        vm.run(0x52aa40)
        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK+4)

    def test_original_drift_reproduced_and_fixed_with_different_update_orders(self):
        for binary in (ORIGINAL, PATCHED):
            vm, ptrs = self.team(binary)
            initial = [rf(vm, p+0x2c) for p in ptrs]
            # The native 50-tick gap between follower rise and leader hold.
            vm.w(ZOMBIE+0x28, 43)
            for _ in range(50):
                for p in ptrs:
                    self.walk(vm, p)
            if binary == ORIGINAL:
                self.assertLess(rf(vm, ptrs[4]+0x2c), initial[4]-30)
                self.assertNotAlmostEqual(rf(vm, ptrs[1]+0x2c), rf(vm, ptrs[2]+0x2c))
            else:
                self.assertEqual([rf(vm, p+0x2c) for p in ptrs], initial)
                vm.w(ZOMBIE+0x28, 44)
                for tick in range(1000):
                    for p in ptrs if tick % 2 else list(reversed(ptrs)):
                        self.walk(vm, p)
                leader_x = rf(vm, ZOMBIE+0x2c)
                self.assertLess(leader_x, 0)
                for p, offset in zip(ptrs, (0, 0, 0, -100, 100)):
                    self.assertAlmostEqual(rf(vm, p+0x2c)-leader_x, offset, delta=0.025)

    def test_team_stops_for_eating_ice_butter_and_leader_phases(self):
        for i in range(5):
            for off in (0x51, 0xb0, 0xb4):
                vm, ptrs = self.team()
                initial = [rf(vm, p+0x2c) for p in ptrs]
                vm.w(ptrs[i]+off, 1)
                for p in reversed(ptrs):
                    self.walk(vm, p)
                self.assertEqual([rf(vm, p+0x2c) for p in ptrs], initial)
        for phase in (41, 42, 43, 45, 46, 47, 48, 49):
            vm, ptrs = self.team()
            vm.w(ZOMBIE+0x28, phase)
            initial = [rf(vm, p+0x2c) for p in ptrs]
            for p in ptrs:
                self.walk(vm, p)
            self.assertEqual([rf(vm, p+0x2c) for p in ptrs], initial)

    def test_existing_save_drift_repairs_gradually_without_moving_when_stopped(self):
        vm, ptrs = self.team()
        for ptr, offset in zip(ptrs, (0, 12, -16, -80, 65)):
            wf(vm, ptr+0x2c, 400.75+offset)
        vm.w(ZOMBIE+0x51, 1)
        old = [rf(vm, p+0x2c) for p in ptrs]
        self.walk(vm, ZOMBIE)
        self.assertEqual([rf(vm, p+0x2c) for p in ptrs], old)
        vm.w(ZOMBIE+0x51, 0)
        for _ in range(180):
            old = [rf(vm, p+0x2c) for p in ptrs]
            for p in reversed(ptrs): self.walk(vm, p)
            for p, prev in zip(ptrs, old):
                step = prev-rf(vm, p+0x2c)
                self.assertGreaterEqual(step, 0.224)
                self.assertLessEqual(step, 0.676)
        for p, offset in zip(ptrs, (0, 0, 0, -100, 100)):
            self.assertAlmostEqual(rf(vm, p+0x2c)-rf(vm, ZOMBIE+0x2c), offset, delta=0.001)

    def test_chill_and_hypnotized_direction_are_shared(self):
        for mind in (0, 1):
            for chilled_member in range(5):
                vm, ptrs = self.team()
                vm.stub(0x4732c0, 'no_ground', 4, 0)
                vm.w(ptrs[chilled_member]+0xac, 100)
                for ptr in ptrs: vm.w(ptr+0xb8, mind)
                before = [rf(vm, p+0x2c) for p in ptrs]
                for ptr in ptrs: self.walk(vm, ptr)
                for ptr, old in zip(ptrs, before):
                    self.assertAlmostEqual(rf(vm, ptr+0x2c)-old,
                                           0.18 if mind else -0.18, delta=0.0001)

    def test_dying_reused_or_detached_followers_are_not_moved_by_leader(self):
        for case in ('dead', 'dying', 'stale', 'detached', 'wrong_type', 'mind'):
            vm, ptrs = self.team()
            ptr = ptrs[1]
            if case == 'dead': vm.w(ptr+0xec, 1)
            if case == 'dying': vm.w(ptr+0x28, 1)
            if case == 'stale': vm.w(ptr+0x158, 0x20001)
            if case == 'detached': vm.w(ptr+0xf0, 0x20000)
            if case == 'wrong_type': vm.w(ptr+0x24, 0)
            if case == 'mind': vm.w(ptr+0xb8, 1)
            before = rf(vm, ptr+0x2c)
            self.walk(vm, ZOMBIE)
            self.assertEqual(rf(vm, ptr+0x2c), before)

    def test_orphan_stale_id_hypnotized_detached_and_other_modes_walk_normally(self):
        for case in ('dead', 'dying', 'stale', 'wrong_type', 'detached', 'hypnotized', 'other_mode'):
            vm, ptrs = self.team(mode=0 if case == 'other_mode' else 70)
            if case == 'dead': vm.w(ZOMBIE+0xec, 1)
            if case == 'dying': vm.w(ZOMBIE+0x28, 1)
            if case == 'stale': vm.w(ZOMBIE+0x158, 0x20000)
            if case == 'wrong_type': vm.w(ZOMBIE+0x24, 0)
            if case == 'detached': vm.w(ZOMBIE+0xf4, 0)
            if case == 'hypnotized': vm.w(ZOMBIE+0xb8, 1)
            before = rf(vm, ptrs[1]+0x2c)
            self.walk(vm, ptrs[1])
            self.assertLess(rf(vm, ptrs[1]+0x2c), before)

    def test_spawn_fractional_alignment_all_slots_modes_and_failure(self):
        for mode in (60, 61, 70, 71):
            for slot in range(4):
                for success in (False, True):
                    vm, ptrs = self.team(mode=mode)
                    ptr = ptrs[slot+1]
                    offset = (0, 0, -100, 100)[slot]
                    wf(vm, ptr+0x2c, 400+offset)
                    vm.reg(UC_X86_REG_ESI, ZOMBIE)
                    vm.reg(UC_X86_REG_EAX, ZOMBIE)
                    vm.reg(UC_X86_REG_EBP, slot)
                    vm.w(STACK+4, 2)
                    vm.w(STACK+8, 400+offset)
                    def summon(v):
                        sp = v.reg(UC_X86_REG_ESP)
                        self.assertEqual(v.r(sp+4), 2)
                        self.assertEqual(v.r(sp+8), 400+offset)
                        self.assertEqual(v.reg(UC_X86_REG_EAX), ZOMBIE)
                        v.ret(8, 0x10001+slot if success else 0)
                    vm.stubs[0x528760] = summon
                    vm.run(symbol('dancer_spawn_alignment'))
                    self.assertEqual(vm.reg(UC_X86_REG_EAX), 0x10001+slot if success else 0)
                    expected = (400.75 if success and 61 <= mode <= 70 else 400)+offset
                    self.assertEqual(rf(vm, ptr+0x2c), expected)
                    self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK+12)

    def test_two_teams_move_independently(self):
        vm, first = self.team()
        second = []
        for i, src in enumerate(first):
            dst = src+5*0x15c
            second.append(dst)
            vm.u.mem_write(dst, bytes(vm.u.mem_read(src, 0x15c)))
            vm.w(dst+0x158, 0x10005+i)
            vm.w(dst+0xf0, 0 if i == 0 else 0x10005)
            wf(vm, dst+0x2c, rf(vm, src+0x2c)+50)
        for i in range(4): vm.w(second[0]+0xf4+i*4, 0x10006+i)
        before = [rf(vm, p+0x2c) for p in second]
        self.walk(vm, first[0])
        self.assertEqual([rf(vm, p+0x2c) for p in second], before)
        first_after = [rf(vm, p+0x2c) for p in first]
        self.walk(vm, second[0])
        self.assertEqual([rf(vm, p+0x2c) for p in first], first_after)
        for p, x in zip(second, before):
            self.assertAlmostEqual(x-rf(vm, p+0x2c), 0.45, delta=0.0001)

    def test_floating_point_state_and_registers_survive_new_helpers(self):
        for kind in ('walk', 'blast'):
            vm, ptrs = self.team() if kind == 'walk' else (self.brain_vm(), [])
            vm.u.mem_write(STOP+0x300, asm('fninit; fld1; fldpi; ret', STOP+0x300))
            vm.run(STOP+0x300)
            snapshot = asm(f'fxsave [{APP+0xd000}]; ret', STOP+0x400)
            vm.u.mem_write(STOP+0x400, snapshot)
            vm.reg(UC_X86_REG_ESP, STACK)
            vm.run(STOP+0x400)
            before = bytes(vm.u.mem_read(APP+0xd000, 512))
            if kind == 'walk':
                vm.reg(UC_X86_REG_ESI, ZOMBIE)
                regs = [vm.reg(r) for r in REGS]
                self.walk(vm, ZOMBIE)
                self.assertEqual([vm.reg(r) for r in REGS], regs)
            else:
                self.blast(vm, 50, 100)
            vm.reg(UC_X86_REG_ESP, STACK)
            vm.w(STACK, STOP)
            vm.run(STOP+0x400)
            after = bytes(vm.u.mem_read(APP+0xd000, 512))
            # Unicorn 2.1.4 leaves the last x87 instruction pointer (FIP)
            # unchanged on FXRSTOR, also in a bare save/fldpi/restore probe.
            # Compare control/status/tags, all FP/MMX/XMM values and MXCSR.
            self.assertEqual(after[:8]+after[12:], before[:8]+before[12:])


if __name__ == '__main__':
    unittest.main()
