"""Real x86: playable grace countdown, native boss visuals and vehicle decay."""
from test_machine_code import *
del PatchTests
import test_boss_survival
from v4_1_fixes import GRACE_MAGIC
from progression_fixes import WEAK_TYPES


def symbol(name):
    return int(MANIFEST['symbols'][name], 16)


class V41Tests(unittest.TestCase):
    def field(self, plants=(1,), zombies=(25,), mode=70):
        vm = VM(mode=mode)
        vm.w(CHALLENGE+0x60, 5)
        vm.w(BOARD+0xac, PLANT)
        vm.w(BOARD+0xb0, len(plants))
        vm.w(BOARD+0x90, ZOMBIE)
        vm.w(BOARD+0x94, len(zombies))
        for i, kind in enumerate(plants):
            p = PLANT+i*0x14c
            vm.w(p+0x24, kind)
            vm.w(p+0x40, 300)
            vm.w(p+0x148, 0x10000+i)
            vm.u.mem_write(p+0x144, b'\1')
        for i, kind in enumerate(zombies):
            p = ZOMBIE+i*0x15c
            vm.w(p+0x24, kind)
            vm.w(p+0xc8, 1)
            vm.w(p+0x158, 0x10000+i)
        def complete(v):
            self.assertEqual(v.reg(UC_X86_REG_ECX), CHALLENGE)
            self.assertEqual(v.reg(UC_X86_REG_EAX), 0)
            self.assertEqual(v.r(v.reg(UC_X86_REG_ESP)+4), 3)
            v.events.append('complete')
            v.ret(4)
        vm.stubs[0x429980] = complete
        # Isolate the grace state machine; reward integration is tested below.
        vm.stubs[symbol('completion_reward_once')] = lambda v: v.ret()
        return vm

    def start(self, vm):
        vm.reg(UC_X86_REG_ESP, STACK)
        vm.w(STACK, STOP)
        vm.w(STACK+4, 3)
        vm.reg(UC_X86_REG_ECX, CHALLENGE)
        vm.reg(UC_X86_REG_EAX, 0)
        before = [vm.reg(r) for r in REGS]
        vm.run(symbol('completion_grace_start'))
        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK+8)
        self.assertEqual([vm.reg(r) for r in REGS], before)

    def tick(self, vm):
        vm.reg(UC_X86_REG_ESP, STACK)
        vm.w(STACK+4, CHALLENGE)
        vm.run(0x42b340, 0x42b347)
        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK-12)
        self.assertEqual(vm.reg(UC_X86_REG_EBP), CHALLENGE)

    def test_either_live_type_suffices_and_mode_boundary(self):
        for plants, zombies, mode, expected in (
                ((1,), (25,), 70, True), ((0,1), (0,25,25), 70, True),
                ((), (25,), 70, True), ((1,), (), 70, True),
                ((0,), (25,), 70, True), ((1,), (0,), 70, True),
                ((0,), (0,), 70, False), ((), (), 70, False),
                ((1,), (25,), 61, False), ((1,), (25,), 71, False)):
            vm = self.field(plants, zombies, mode)
            self.start(vm)
            self.assertEqual(vm.r(CHALLENGE+0x90) == GRACE_MAGIC, expected)
            self.assertEqual('complete' in vm.events, not expected)

    def test_dead_squished_offboard_or_dying_do_not_trigger(self):
        for ptr, offset, value in ((PLANT,0x141,1), (PLANT,0x142,1),
                (PLANT,0x144,0), (PLANT,0x40,0), (ZOMBIE,0xec,1),
                (ZOMBIE,0x28,1), (ZOMBIE,0x28,2), (ZOMBIE,0x28,3)):
            vm = self.field(zombies=() if ptr == PLANT else (25,),
                            plants=(1,) if ptr == PLANT else ())
            if offset in (0x40,0x28): vm.w(ptr+offset, value)
            else: vm.u.mem_write(ptr+offset, bytes([value]))
            self.start(vm)
            self.assertEqual(vm.events, ['complete'])

    def test_2000_ticks_reentry_save_resume_and_next_stage(self):
        vm = self.field()
        self.start(vm)
        for _ in range(1000): self.tick(vm)
        self.start(vm)  # Never reset/extend the countdown.
        self.assertEqual(vm.r(CHALLENGE+0x94), 1000)
        loaded = self.field()
        loaded.u.mem_write(CHALLENGE, bytes(vm.u.mem_read(CHALLENGE, 0xbc)))
        for _ in range(999): self.tick(loaded)
        self.assertEqual(loaded.events, [])
        # Normal play: neither native transition nor award flag was set.
        self.assertEqual(loaded.r(BOARD+0x5604), 0)
        self.assertEqual(loaded.r(BOARD+0x560c), 0)
        self.tick(loaded)
        self.assertEqual(loaded.events, ['complete'])
        self.tick(loaded)
        self.assertEqual(loaded.events, ['complete'])
        loaded.reg(UC_X86_REG_EDI, BOARD)
        loaded.run(0x40c7df, 0x40c7e9)
        self.assertEqual(loaded.r(BOARD+0x5604), 1)
        loaded.w(CHALLENGE+0x60, 0)
        self.tick(loaded)
        self.assertEqual(loaded.r(CHALLENGE+0x90), 0)
        loaded.w(CHALLENGE+0x60, 5)
        self.start(loaded)
        self.assertEqual(loaded.r(CHALLENGE+0x94), 2000)

    def test_boss_penalty_runs_native_damage_images_and_smoke(self):
        helper = test_boss_survival.BossSurvivalTests()
        for hp in (500, 300, 100):
            vm = helper.boss()
            vm.w(ZOMBIE+0xc8, hp)
            vm.w(ZOMBIE+0x154, hp)
            helper.update(vm)
            self.assertEqual(vm.r(ZOMBIE+0xc8), 1)
            if hp >= 250:
                self.assertEqual(vm.events.count('damage_image'), 5)
            self.assertIn('smoke', vm.events)
            self.assertIn('damage_particle', vm.events)
            self.assertNotIn('death', vm.events)

    def test_jack_and_tallnut_have_weighted_roll(self):
        self.assertTrue({15,31}.issubset(WEAK_TYPES))
        # test_progression executes all 100 outcomes for each member.

    def test_rewards_stay_at_last_brain_not_after_grace(self):
        vm = self.field()
        del vm.stubs[symbol('completion_reward_once')]
        vm.w(CHALLENGE+0x6c, 29)
        vm.coin_stub()
        self.start(vm)
        suns = [e for e in vm.events if isinstance(e, tuple)]
        self.assertEqual(len(suns), 24)  # +600, sunflower prevents +75.
        vm.u.mem_write(PLANT+0x141, b'\1')
        vm.reg(UC_X86_REG_ESP, STACK)
        vm.w(STACK, STOP)
        vm.reg(UC_X86_REG_ECX, CHALLENGE)
        vm.run(symbol('completion_reward_once'))
        self.assertEqual(len(vm.events), 24)

    def test_completed_grace_cannot_become_low_money_defeat(self):
        vm = self.field()
        self.start(vm)
        vm.w(BOARD+0xa0, 0)
        vm.reg(UC_X86_REG_EBP, CHALLENGE)
        vm.run(0x42b4a1, 0x42b526)
        vm.w(CHALLENGE+0x60, 4)
        vm.run(0x42b4a1, 0x42b4aa)
        self.assertEqual(vm.reg(UC_X86_REG_EDX), BOARD)

    def test_new_hooks_overwrite_complete_instructions(self):
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        pe = pefile.PE(data=ORIGINAL)
        dis = Cs(CS_ARCH_X86, CS_MODE_32)
        for site in (0x42b90d,0x42b340,0x40c7df,0x42b4a1):
            hook = next(h for h in MANIFEST['hooks'] if int(h['va'],16)==site)
            self.assertEqual(sum(i.size for i in dis.disasm(
                pe.get_data(site-0x400000,hook['length']),site)),hook['length'])

    def test_native_vehicle_decay_boundary_and_probability_unchanged(self):
        for binary in (ORIGINAL, PATCHED):
            vm = VM(binary)
            for kind in (12,22):
                for hp in (200,199,1):
                    for roll in range(5):
                        vm.w(ZOMBIE+0x24, kind)
                        vm.w(ZOMBIE+0xc8, hp)
                        vm.w(ZOMBIE+0xcc, 850)
                        vm.reg(UC_X86_REG_EDI, ZOMBIE)
                        vm.reg(UC_X86_REG_ESP, STACK)
                        vm.events.clear()
                        vm.stub(0x5af400, 'rng', eax=roll)
                        def damage(v):
                            self.assertEqual(v.reg(UC_X86_REG_EAX), 9)
                            self.assertEqual(v.r(v.reg(UC_X86_REG_ESP)+4), 3)
                            v.events.append('decay')
                            v.ret(4)
                        vm.stubs[0x5317c0] = damage
                        vm.run(0x52b4d0, 0x52b551)
                        self.assertEqual('decay' in vm.events, hp < 200 and roll == 0)
                        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK)


if __name__ == '__main__':
    unittest.main()
