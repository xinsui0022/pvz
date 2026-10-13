"""Execute challenge health hooks and native helmet/body damage together."""
import unittest

from test_machine_code import (
    VM, ORIGINAL, MANIFEST, APP, BOARD, ZOMBIE, PLANT, CHALLENGE, REANIM, STACK,
    STOP, REGS, UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX,
    UC_X86_REG_EDX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP,
    UC_X86_REG_ESP, UC_X86_REG_EIP, UC_X86_REG_FP0, UC_X86_REG_FPSW,
    UC_X86_REG_EFLAGS, asm,
)
from challenge_mode import CHALLENGE_MAGIC
from challenge_zombies import (
    NORMAL_BODY_HEALTH, CONE_HELMET_HEALTH, CHALLENGE_RANDOM_HELMET_HEALTH,
    CHALLENGE_BOSS_HEALTH,
)


class ChallengeZombieTests(unittest.TestCase):
    def vm(self, mode=70, challenge=True):
        v = VM(mode=mode)
        v.w(BOARD + 0x8C, APP)
        v.w(CHALLENGE + 0xB4, CHALLENGE_MAGIC if challenge else 0)
        return v

    def test_challenge_random_helmet_is_640_without_changing_body(self):
        self.assertEqual(NORMAL_BODY_HEALTH, 270)
        self.assertEqual(CONE_HELMET_HEALTH, 370)
        self.assertEqual(CHALLENGE_RANDOM_HELMET_HEALTH, 640)
        for mode, selected, expected in ((61, True, 640), (70, True, 640),
                (61, False, 370), (70, False, 370), (60, True, 370),
                (71, True, 370), (0, True, 370)):
            with self.subTest(mode=mode, selected=selected):
                v = self.vm(mode, selected)
                v.w(ZOMBIE + 0xC8, 270)
                v.w(ZOMBIE + 0xCC, 270)
                v.reg(UC_X86_REG_EDI, ZOMBIE)
                v.reg(UC_X86_REG_EAX, 0xAABBCCDD)
                v.run(0x52288C, 0x522896)
                self.assertEqual(v.r(ZOMBIE + 0xD0), expected)
                self.assertEqual(v.r(ZOMBIE + 0xC8), 270)
                self.assertEqual(v.r(ZOMBIE + 0xCC), 270)
                self.assertEqual(v.reg(UC_X86_REG_EAX), 0xAABBCCDD)
                self.assertEqual(v.reg(UC_X86_REG_ESP), STACK)
                v.run(0x523FA3, 0x523FDC)
                self.assertEqual(v.r(ZOMBIE + 0xD4), expected)
                self.assertEqual(v.r(ZOMBIE + 0xCC), 270)

    def test_imp_body_is_270_only_in_challenge(self):
        for mode, selected, expected in ((61, True, 270), (70, True, 270),
                (61, False, 70), (70, False, 70), (60, True, 70),
                (71, True, 70), (0, True, 70)):
            with self.subTest(mode=mode, selected=selected):
                v = self.vm(mode, selected)
                v.reg(UC_X86_REG_EDI, ZOMBIE)
                v.reg(UC_X86_REG_EAX, 0xAABBCCDD)
                v.run(0x5235A6, 0x5235B0)
                self.assertEqual(v.r(ZOMBIE + 0xC8), expected)
                self.assertEqual(v.reg(UC_X86_REG_EAX), 0xAABBCCDD)
                self.assertEqual(v.reg(UC_X86_REG_ESP), STACK)
                # Native common initialization copies the new body maximum.
                v.run(0x523FA3, 0x523FDC)
                self.assertEqual(v.r(ZOMBIE + 0xCC), expected)

    def test_boss_initializer_mode_matrix_and_maximum(self):
        self.assertEqual(CHALLENGE_BOSS_HEALTH, 10000)
        for mode, selected, expected in ((61, True, 10000), (70, True, 10000),
                (61, False, 500), (70, False, 500), (60, True, 60000),
                (71, True, 60000), (0, True, 40000)):
            with self.subTest(mode=mode, selected=selected):
                v = self.vm(mode, selected)
                v.reg(UC_X86_REG_ECX, APP)
                v.reg(UC_X86_REG_EDI, ZOMBIE)
                def unexpected_rng(vm):
                    self.fail('Boss initialization must not consume a health roll')
                v.stubs[0x5AF400] = unexpected_rng
                v.run(0x523612, 0x523638)
                self.assertEqual(v.r(ZOMBIE + 0xC8), expected)
                self.assertEqual(v.reg(UC_X86_REG_EAX), ZOMBIE)
                self.assertEqual(v.reg(UC_X86_REG_ESP), STACK)
                v.run(0x523FA3, 0x523FDC)
                self.assertEqual(v.r(ZOMBIE + 0xCC), expected)

    def test_random_boss_rolls_once_and_preserves_native_abi(self):
        for mode, selected in ((61, True), (70, True), (61, False),
                               (70, False), (0, True), (60, True), (71, True)):
            for roll in (0, 1):
                with self.subTest(mode=mode, selected=selected, roll=roll):
                    v = self.vm(mode, selected)
                    active = selected and 61 <= mode <= 70
                    for index, reg in enumerate(REGS):
                        v.reg(reg, 0x12345000 + index)
                    v.reg(UC_X86_REG_EAX, ZOMBIE)
                    v.reg(UC_X86_REG_EFLAGS, 0x246)
                    v.u.mem_write(STOP, asm('fld1; nop', STOP))
                    v.run(STOP, STOP + 2)
                    before = {reg: v.reg(reg) for reg in REGS}
                    flags = v.reg(UC_X86_REG_EFLAGS)
                    fp = v.reg(UC_X86_REG_FP0), v.reg(UC_X86_REG_FPSW)
                    def rng(vm):
                        self.assertTrue(active, 'Traditional boss must not reroll HP')
                        self.assertEqual(vm.reg(UC_X86_REG_EAX), 2)
                        vm.events.append('boss_health_rng')
                        # Native Rand clobbers its integer volatile registers.
                        vm.reg(UC_X86_REG_ECX, 0xAABBCCDD)
                        vm.reg(UC_X86_REG_EDX, 0x55667788)
                        vm.reg(UC_X86_REG_EFLAGS, 0x202)
                        vm.ret(eax=roll)
                    v.stubs[0x5AF400] = rng
                    v.run(0x651143, 0x651157)
                    expected = (10000 if roll == 0 else 5000) if active else 500
                    self.assertEqual(v.r(ZOMBIE + 0xC8), expected)
                    self.assertEqual(v.r(ZOMBIE + 0xCC), 10000 if active else 500)
                    self.assertEqual(v.events, ['boss_health_rng'] if active else [])
                    self.assertEqual({reg: v.reg(reg) for reg in REGS}, before)
                    self.assertEqual(v.reg(UC_X86_REG_EFLAGS), flags)
                    self.assertEqual((v.reg(UC_X86_REG_FP0),
                                      v.reg(UC_X86_REG_FPSW)), fp)
                    self.assertEqual(v.reg(UC_X86_REG_ESP), STACK)

    def test_every_random_type_keeps_full_body_helmet_and_shield(self):
        for kind in range(33):
            if kind == 25:  # Boss takes the separate override branch above.
                continue
            for mode in (61, 70):
                with self.subTest(kind=kind, mode=mode):
                    v = self.vm(mode)
                    v.w(ZOMBIE + 0x24, kind)
                    for current, maximum, hp in ((0xC8, 0xCC, 1350),
                            (0xD0, 0xD4, 370), (0xDC, 0xE0, 1100)):
                        v.w(ZOMBIE + current, hp)
                        v.w(ZOMBIE + maximum, hp)
                    v.w(PLANT + 0x24, 2)
                    v.w(PLANT + 0xC8, 123)
                    v.reg(UC_X86_REG_EAX, ZOMBIE)
                    v.reg(UC_X86_REG_EBX, PLANT)
                    def unexpected_rng(vm):
                        self.fail('Challenge random HP must not roll a fraction')
                    v.stubs[0x5AF400] = unexpected_rng
                    v.run(0x651177, 0x6511CD)
                    for current, maximum, hp in ((0xC8, 0xCC, 1350),
                            (0xD0, 0xD4, 370), (0xDC, 0xE0, 1100)):
                        self.assertEqual(v.r(ZOMBIE + current), hp)
                        self.assertEqual(v.r(ZOMBIE + maximum), hp)
                    self.assertEqual(v.r(PLANT + 0xC8), 123)
                    self.assertEqual(v.reg(UC_X86_REG_EBX), PLANT)
                    self.assertEqual(v.reg(UC_X86_REG_ESP), STACK)

    def test_traditional_random_fractions_and_outside_mode_marker(self):
        for mode, selected in ((61, False), (70, False), (0, True),
                               (60, True), (71, True)):
            with self.subTest(mode=mode, selected=selected):
                v = self.vm(mode, selected)
                v.w(ZOMBIE + 0x24, 0)
                for off in (0xC8, 0xD0, 0xDC):
                    v.w(ZOMBIE + off, 300)
                v.reg(UC_X86_REG_EAX, ZOMBIE)
                v.reg(UC_X86_REG_EBX, PLANT)
                v.stub(0x5AF400, 'health_rng', eax=99 if 61 <= mode <= 70 else 4)
                v.run(0x651177, 0x6511CD)
                self.assertEqual(v.events, ['health_rng'])
                self.assertEqual([v.r(ZOMBIE + off) for off in
                                  (0xC8, 0xCC, 0xD0, 0xD4, 0xDC, 0xE0)],
                                 [60] * 6)

    def carrier(self, mode=70, challenge=True, result=0, boss_roll=0):
        v = self.vm(mode, challenge)
        v.w(ZOMBIE + 0x24, 2)
        v.w(ZOMBIE + 0x1C, 2)
        v.w(ZOMBIE + 0xC4, 1)
        v.w(ZOMBIE + 0xC8, 270)
        v.w(ZOMBIE + 0xCC, 270)
        helmet_hp = 640 if challenge and 61 <= mode <= 70 else 370
        v.w(ZOMBIE + 0xD0, helmet_hp)
        v.w(ZOMBIE + 0xD4, helmet_hp)
        v.w(APP + 0x820, REANIM)
        v.w(REANIM, REANIM)

        # Skip only renderer-dependent DropHelm operations. Native helmet
        # subtraction, the actual final conversion gate, and its epilogue run.
        def drop_helmet(vm):
            p = vm.reg(UC_X86_REG_EAX)
            sp = vm.reg(UC_X86_REG_ESP)
            vm.w(sp - 40, vm.reg(UC_X86_REG_EBX))
            vm.w(sp - 44, vm.reg(UC_X86_REG_ESI))
            vm.w(sp - 48, vm.reg(UC_X86_REG_EDI))
            vm.reg(UC_X86_REG_ESP, sp - 48)
            vm.reg(UC_X86_REG_EBX, p)
            vm.reg(UC_X86_REG_EIP, 0x6510CD)
        v.stubs[0x530E30] = drop_helmet
        v.stub(0x52A470, 'damage_visuals')
        v.stub(0x533240, 'native_death', pop=4)
        v.stub(0x530170, 'loot')
        v.stub(int(MANIFEST['symbols']['v5_single_boss_random'], 16),
               'choose_result', eax=result)

        def create(vm):
            sp = vm.reg(UC_X86_REG_ESP)
            self.assertEqual(vm.reg(UC_X86_REG_EAX), BOARD)
            self.assertEqual(vm.r(sp + 4), result)
            self.assertEqual(vm.r(sp + 8), 2)
            vm.w(PLANT, APP)
            vm.w(PLANT + 4, BOARD)
            vm.w(PLANT + 0x24, result)
            vm.w(PLANT + 0xC8, 10000 if result == 25 else 270)
            vm.w(PLANT + 0xCC, 10000 if result == 25 else 270)
            vm.w(PLANT + 0xD0, helmet_hp if result == 2 else 0)
            vm.w(PLANT + 0xD4, helmet_hp if result == 2 else 0)
            vm.events.append('new_zombie')
            vm.ret(8, PLANT)
        v.stubs[0x40DDC0] = create
        v.stub(0x518A70, 'conversion_particle', pop=16)
        # Boss conversion skips the generic fraction branch, and only the
        # challenge boss override may consume its single two-outcome roll.
        if result == 25:
            def boss_rng(vm):
                self.assertTrue(challenge and 61 <= mode <= 70)
                self.assertEqual(vm.reg(UC_X86_REG_EAX), 2)
                vm.events.append('boss_health_rng')
                vm.ret(eax=boss_roll)
            v.stubs[0x5AF400] = boss_rng
        else:
            # Traditional health still uses its fraction RNG after creation.
            v.stub(0x5AF400, 'health_rng', eax=0)
        return v

    def damage(self, v, amount):
        v.reg(UC_X86_REG_ESP, STACK)
        v.w(STACK, STOP)
        v.w(STACK + 4, amount)
        v.reg(UC_X86_REG_ESI, ZOMBIE)
        v.reg(UC_X86_REG_EAX, 8)
        v.run(0x5317C0)
        self.assertEqual(v.reg(UC_X86_REG_ESP), STACK + 8)

    def test_challenge_carrier_converts_immediately_after_640_helmet_damage(self):
        for mode in (61, 70):
            with self.subTest(mode=mode):
                v = self.carrier(mode)
                self.damage(v, 370)
                self.assertEqual(v.r(ZOMBIE + 0xC4), 1)
                self.assertEqual(v.r(ZOMBIE + 0xD0), 270)
                self.assertEqual(v.r(ZOMBIE + 0xC8), 270)
                self.assertEqual(v.r(ZOMBIE + 0xEC) & 255, 0)
                self.assertNotIn('new_zombie', v.events)
                self.damage(v, 269)
                self.assertEqual(v.r(ZOMBIE + 0xD0), 1)
                self.assertEqual(v.r(ZOMBIE + 0xC8), 270)
                self.assertNotIn('new_zombie', v.events)
                self.damage(v, 1)
                self.assertEqual(v.r(ZOMBIE + 0xD0), 0)
                # Body never received damage: only the strengthened helmet
                # needs to disappear for the unchanged conversion to occur.
                self.assertEqual(v.r(ZOMBIE + 0xC8), 270)
                self.assertEqual(v.r(ZOMBIE + 0xEC) & 255, 1)
                self.assertEqual(v.events.count('new_zombie'), 1)
                self.assertNotIn('native_death', v.events)
                self.assertNotIn('health_rng', v.events)
                self.damage(v, 1000)
                self.assertEqual(v.events.count('new_zombie'), 1)

    def test_lethal_overflow_converts_full_cone_or_boss_with_clean_abi(self):
        for result in (0, 2, 24, 25):
            for amount in (640, 1800):
                with self.subTest(result=result, damage=amount):
                    v = self.carrier(result=result)
                    # A live x87 value must survive the conversion's particles.
                    v.u.mem_write(STOP, asm('fld1; nop', STOP))
                    v.run(STOP, STOP + 2)
                    fp = v.reg(UC_X86_REG_FP0), v.reg(UC_X86_REG_FPSW)
                    self.damage(v, amount)
                    self.assertEqual((v.reg(UC_X86_REG_FP0),
                                      v.reg(UC_X86_REG_FPSW)), fp)
                    if amount == 640:
                        self.assertEqual(v.r(ZOMBIE + 0xC8), 270)
                    self.assertEqual(v.r(ZOMBIE + 0xEC) & 255, 1)
                    self.assertEqual(v.events.count('new_zombie'), 1)
                    body = CHALLENGE_BOSS_HEALTH if result == 25 else 270
                    self.assertEqual(v.r(PLANT + 0xC8), body)
                    self.assertEqual(v.r(PLANT + 0xCC), body)
                    if result == 2:
                        self.assertEqual(v.r(PLANT + 0xD0), 640)
                        self.assertEqual(v.r(PLANT + 0xD4), 640)
                    self.assertNotIn('health_rng', v.events)
                    self.assertEqual(v.events.count('boss_health_rng'),
                                     1 if result == 25 else 0)

    def test_native_conversion_keeps_both_boss_rolls_without_second_fraction(self):
        for mode in (61, 70):
            for roll, expected in ((0, 10000), (1, 5000)):
                with self.subTest(mode=mode, roll=roll):
                    v = self.carrier(mode, result=25, boss_roll=roll)
                    self.damage(v, 640)
                    self.assertEqual(v.r(PLANT + 0xC8), expected)
                    self.assertEqual(v.r(PLANT + 0xCC), 10000)
                    self.assertEqual(v.events.count('new_zombie'), 1)
                    self.assertEqual(v.events.count('boss_health_rng'), 1)
                    self.assertNotIn('health_rng', v.events)

        for mode, selected in ((61, False), (70, False), (60, True), (71, True)):
            with self.subTest(mode=mode, selected=selected):
                v = self.carrier(mode, selected, result=25)
                self.damage(v, 370)
                self.assertEqual(v.r(PLANT + 0xC8), 500)
                self.assertEqual(v.r(PLANT + 0xCC), 500)
                self.assertEqual(v.events.count('new_zombie'), 1)
                self.assertNotIn('boss_health_rng', v.events)

    def test_traditional_carrier_still_converts_on_370_helmet_damage(self):
        for mode, selected in ((61, False), (70, False), (60, True),
                               (71, True)):
            with self.subTest(mode=mode, selected=selected):
                v = self.carrier(mode, selected)
                self.damage(v, 370)
                self.assertEqual(v.r(ZOMBIE + 0xEC) & 255, 1)
                self.assertEqual(v.events.count('new_zombie'), 1)
                self.assertIn('health_rng', v.events)

    def test_health_hooks_do_not_heal_existing_damaged_zombies(self):
        # Health changes are initialization-only; native body damage remains
        # unchanged and must not restore damage after save loading.
        for kind, current, maximum in ((24, 173, 270), (25, 1300, 2000)):
            v = self.vm()
            v.w(ZOMBIE + 0x24, kind)
            v.w(ZOMBIE + 0xC8, current)
            v.w(ZOMBIE + 0xCC, maximum)
            v.reg(UC_X86_REG_EBP, ZOMBIE)
            v.run(0x531783, 0x53178A)
            self.assertEqual(v.r(ZOMBIE + 0xC8), current)
            self.assertEqual(v.r(ZOMBIE + 0xCC), maximum)
            self.assertEqual(v.reg(UC_X86_REG_ESP), STACK)

    def test_original_conversion_gate_and_body_death_bytes_unchanged(self):
        old = VM(ORIGINAL)
        v = self.vm()
        for address, size in ((0x6510CD, 10), (0x531783, 7)):
            self.assertEqual(bytes(v.u.mem_read(address, size)),
                             bytes(old.u.mem_read(address, size)), hex(address))

    def test_direct_helmet_removal_still_triggers_original_conversion(self):
        # Magnet removal enters DropHelm directly, independently of HP. The
        # renderer stub transfers into the exact unchanged native final gate.
        v = self.carrier()
        v.reg(UC_X86_REG_EAX, ZOMBIE)
        v.w(STACK, STOP)
        v.w(STACK + 4, 0)
        v.stubs[0x530E30](v)
        v.run(0x6510CD)
        self.assertEqual(v.r(ZOMBIE + 0xC8), 270)
        self.assertEqual(v.r(ZOMBIE + 0xEC) & 255, 1)
        self.assertEqual(v.events.count('new_zombie'), 1)
        self.assertEqual(v.reg(UC_X86_REG_ESP), STACK + 8)

    def test_challenge_boss_keeps_full_or_half_hp_through_undamaged_head_cycle(self):
        from test_boss_survival import BossSurvivalTests
        suite = BossSurvivalTests()
        for mode in (61, 70):
            for health in (10000, 5000):
                with self.subTest(mode=mode, health=health):
                    v = suite.boss(mode=mode)
                    v.w(BOARD + 0x8C, APP)
                    v.w(CHALLENGE + 0xB4, CHALLENGE_MAGIC)
                    v.w(ZOMBIE + 0xC8, health)
                    v.w(ZOMBIE + 0xCC, 10000)
                    v.w(ZOMBIE + 0x154, health)
                    for ticks in range(51, -1, -1):
                        v.w(ZOMBIE + 0x68, ticks)
                        suite.update(v)
                        self.assertEqual(v.r(ZOMBIE + 0xC8), health)
                        self.assertEqual(v.r(ZOMBIE + 0xCC), 10000)
                        self.assertEqual(v.r(ZOMBIE + 0xEC) & 255, 0)
                        self.assertNotIn('death', v.events)
                    self.assertEqual(v.r(ZOMBIE + 0x28), 0x5A)
                    self.assertNotIn('damage_image', v.events)

    def test_challenge_lethal_damage_still_dies_in_every_native_boss_phase(self):
        from test_boss_survival import BossSurvivalTests
        suite = BossSurvivalTests()
        for health in (10000, 5000):
            for phase in (0x4F, 0x57, 0x58):
                with self.subTest(health=health, phase=phase):
                    v = suite.boss()
                    v.w(BOARD + 0x8C, APP)
                    v.w(CHALLENGE + 0xB4, CHALLENGE_MAGIC)
                    v.w(ZOMBIE + 0xC8, health)
                    v.w(ZOMBIE + 0xCC, 10000)
                    v.w(ZOMBIE + 0x154, health)
                    v.w(ZOMBIE + 0x28, phase)
                    suite.damage(v, health)
                    self.assertEqual(v.r(ZOMBIE + 0xC8), 1)
                    suite.update(v)
                    self.assertEqual(v.r(ZOMBIE + 0xEC) & 255, 1)
                    self.assertIn('death', v.events)

    def test_challenge_old_last_stand_marker_no_longer_grants_death_immunity(self):
        from test_boss_survival import BossSurvivalTests
        from v3_fixes import BOSS_LAST_STAND
        suite = BossSurvivalTests()
        for phase in (0x4F, 0x57, 0x58):
            for mode, selected in ((61, True), (70, True), (61, False),
                                   (70, False), (60, True), (71, True)):
                with self.subTest(phase=phase, mode=mode, selected=selected):
                    v = suite.boss(mode=mode)
                    v.w(BOARD + 0x8C, APP)
                    v.w(CHALLENGE + 0xB4, CHALLENGE_MAGIC if selected else 0)
                    v.w(ZOMBIE + 0xC8, 1)
                    v.w(ZOMBIE + 0x154, BOSS_LAST_STAND)
                    v.w(ZOMBIE + 0x28, phase)
                    suite.update(v)
                    classic_last_stand = 61 <= mode <= 70 and not selected
                    self.assertEqual('death' in v.events, not classic_last_stand)

    def test_traditional_boss_still_receives_undamaged_last_stand_penalty(self):
        from test_boss_survival import BossSurvivalTests
        from v3_fixes import BOSS_LAST_STAND
        suite = BossSurvivalTests()
        for mode in (61, 70):
            with self.subTest(mode=mode):
                v = suite.boss(mode=mode)
                v.w(BOARD + 0x8C, APP)
                v.w(CHALLENGE + 0xB4, 0)
                suite.update(v)
                self.assertEqual(v.r(ZOMBIE + 0xC8), 1)
                self.assertEqual(v.r(ZOMBIE + 0x154), BOSS_LAST_STAND)
                self.assertEqual(v.r(ZOMBIE + 0xEC) & 255, 0)
                self.assertNotIn('death', v.events)


if __name__ == '__main__':
    unittest.main()
