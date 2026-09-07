"""Exercise full boss updates, including the branches after the HP penalty."""
import unittest

from test_machine_code import (
    VM, ROOT, PATCHED, APP, BOARD, ZOMBIE, REANIM, STACK, STOP,
    UC_X86_REG_EAX, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP,
)
from v3_fixes import BOSS_LAST_STAND


class BossSurvivalTests(unittest.TestCase):
    def boss(self, binary=PATCHED, mode=70):
        vm = VM(binary, mode)
        vm.w(APP+0x7fc, 3)
        vm.u.mem_write(APP+0x8c5, b'\1')
        vm.w(APP+0x820, REANIM)
        vm.w(REANIM+8, REANIM+0x100)
        vm.w(REANIM+0x100, REANIM+0x200)
        vm.w(REANIM+0x108, 2)
        vm.w(REANIM+0x29c, 0x10000)
        vm.w(REANIM+0x33c, 0x10001)
        vm.w(ZOMBIE+0x118, 0x10000)
        vm.w(ZOMBIE+0x144, 0x10001)
        vm.w(ZOMBIE+0x28, 0x58)
        vm.w(ZOMBIE+0x68, 50)
        vm.w(ZOMBIE+0xc8, 500)
        vm.w(ZOMBIE+0xcc, 500)
        vm.w(ZOMBIE+0x154, 500)
        vm.stub(0x535c60, 'fireball')
        vm.stub(0x473b70, 'timed_event', pop=4, eax=0)
        vm.stub(0x528b00, 'animation', pop=16)
        vm.stub(0x536b00, 'smoke', pop=4)
        vm.stub(0x5af400, 'rng', eax=0)
        vm.stub(0x52d710, 'damage_index', eax=2)
        vm.stub(0x535440, 'spit')
        for address, pop in ((0x535fb0, 0), (0x533240, 4)):
            def die(v, pop=pop):
                v.u.mem_write(v.reg(UC_X86_REG_EAX)+0xec, b'\1')
                v.events.append('death')
                v.ret(pop)
            vm.stubs[address] = die
        return vm

    def update(self, vm, zombie=ZOMBIE):
        vm.reg(UC_X86_REG_ESP, STACK)
        vm.w(STACK, STOP)
        vm.reg(UC_X86_REG_EAX, zombie)
        vm.run(0x536080)
        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK+4)

    def damage(self, vm, amount):
        vm.reg(UC_X86_REG_ESP, STACK)
        vm.w(STACK, STOP)
        vm.w(STACK+4, ZOMBIE)
        vm.w(STACK+8, amount)
        vm.w(STACK+12, 8)
        vm.run(0x5312d0)
        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK+16)

    def test_previous_v3_penalty_enters_death_in_same_update(self):
        old = ROOT/'backups/PlantsVsZombies.v3.0.0.exe'
        if not old.exists():
            self.skipTest('Local previous V3 executable is not distributed')
        vm = self.boss(old.read_bytes())
        self.update(vm)
        self.assertEqual(vm.r(ZOMBIE+0xc8), 1)
        self.assertEqual(vm.r(ZOMBIE+0xec)&255, 1)
        self.assertIn('death', vm.events)

    def test_penalty_survives_raise_idle_and_next_head_cycle(self):
        vm = self.boss()
        vm.w(ZOMBIE+0x68, 51)
        self.update(vm)
        self.assertEqual(vm.r(ZOMBIE+0xc8), 500)
        # PhaseCounter is decremented by Zombie::Update outside UpdateBoss.
        for ticks in range(50, -1, -1):
            vm.w(ZOMBIE+0x68, ticks)
            self.update(vm)
            self.assertEqual(vm.r(ZOMBIE+0xc8), 1)
            self.assertEqual(vm.r(ZOMBIE+0xec)&255, 0)
        self.assertEqual(vm.r(ZOMBIE+0x28), 0x5a)
        vm.w(REANIM+0x25c, 1)
        self.update(vm)  # Finish the raise animation, enter native idle.
        self.assertEqual(vm.r(ZOMBIE+0x28), 0x4f)
        self.update(vm)
        vm.reg(UC_X86_REG_ESP, STACK)
        vm.w(STACK, STOP)
        vm.reg(UC_X86_REG_EAX, ZOMBIE)
        vm.run(0x5353a0)  # Start the next head cycle through the real hook.
        self.assertEqual(vm.r(ZOMBIE+0x154), BOSS_LAST_STAND)
        self.update(vm)
        self.assertEqual(vm.r(ZOMBIE+0x28), 0x57)
        self.update(vm)
        vm.w(ZOMBIE+0x68, 0)
        self.update(vm)
        self.assertIn('spit', vm.events)
        vm.w(ZOMBIE+0x28, 0x58)
        vm.w(ZOMBIE+0x68, 50)
        self.update(vm)
        self.assertEqual(vm.r(ZOMBIE+0xc8), 1)
        self.assertNotIn('death', vm.events)

    def test_real_positive_body_damage_kills_penalized_boss_but_zero_does_not(self):
        for amount in (0, 1, 20, 1800):
            with self.subTest(damage=amount):
                vm = self.boss()
                self.update(vm)
                self.damage(vm, amount)
                # The native lethal-damage clamp still leaves 1 in HP.
                self.assertEqual(vm.r(ZOMBIE+0xc8), 1)
                self.assertEqual(vm.r(ZOMBIE+0x154), 0 if amount else BOSS_LAST_STAND)
                self.update(vm)
                self.assertEqual('death' in vm.events, amount > 0)

    def test_any_positive_damage_cancels_this_cycles_penalty(self):
        vm = self.boss()
        self.damage(vm, 1)
        self.assertEqual(vm.r(ZOMBIE+0xc8), 499)
        self.update(vm)
        self.assertEqual(vm.r(ZOMBIE+0xc8), 499)
        vm.w(ZOMBIE+0xc8, 500)
        self.update(vm)
        self.assertEqual(vm.r(ZOMBIE+0xc8), 500)
        self.assertNotIn('death', vm.events)

    def test_all_death_phases_preserve_lethal_damage_and_other_modes(self):
        for mode in (0, 35, 60, 61, 70, 71):
            for phase in (0x4f, 0x57, 0x58):
                for mark in (0, BOSS_LAST_STAND):
                    with self.subTest(mode=mode, phase=phase, mark=mark):
                        vm = self.boss(mode=mode)
                        vm.w(ZOMBIE+0xc8, 1)
                        vm.w(ZOMBIE+0x154, mark)
                        vm.w(ZOMBIE+0x28, phase)
                        self.update(vm)
                        self.assertEqual('death' in vm.events,
                                         not (61 <= mode <= 70 and mark == BOSS_LAST_STAND))

    def test_penalty_marker_is_per_boss_and_survives_serialization(self):
        vm = self.boss()
        self.update(vm)
        loaded = self.boss()
        loaded.u.mem_write(ZOMBIE, bytes(vm.u.mem_read(ZOMBIE, 0x15c)))
        loaded.w(ZOMBIE+0x28, 0x4f)
        self.update(loaded)
        other = ZOMBIE+0x15c
        loaded.u.mem_write(other, bytes(loaded.u.mem_read(ZOMBIE, 0x15c)))
        loaded.w(other+0x154, 0)
        self.update(loaded, other)
        self.assertEqual(loaded.r(other+0xec)&255, 1)
        self.assertEqual(loaded.r(ZOMBIE+0xec)&255, 0)

    def test_shared_damage_hook_does_not_change_non_boss_or_other_mode_state(self):
        for mode, kind in ((70, 0), (70, 12), (0, 25), (60, 25), (71, 25)):
            vm = self.boss(mode=mode)
            vm.w(ZOMBIE+0x24, kind)
            vm.w(ZOMBIE+0x154, BOSS_LAST_STAND)
            vm.reg(UC_X86_REG_EBP, ZOMBIE)
            vm.reg(UC_X86_REG_EDI, 10)
            vm.w(STACK+0x20, 1)
            vm.run(0x53130f, 0x53131f)
            self.assertEqual(vm.r(ZOMBIE+0xc8), 9)
            self.assertEqual(vm.r(ZOMBIE+0x154), BOSS_LAST_STAND)


if __name__ == '__main__':
    unittest.main()
