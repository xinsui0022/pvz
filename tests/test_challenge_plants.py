"""Execute challenge hooks, native iterators and exact collision boundaries."""
import unittest
from test_machine_code import (
    VM, APP, BOARD, PLANT, ZOMBIE, CHALLENGE, STACK, STOP, BRAIN, PROFILE,
    REANIM, REGS, asm, UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX,
    UC_X86_REG_EDX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP,
    UC_X86_REG_ESP, UC_X86_REG_EFLAGS,
)
from challenge_mode import CHALLENGE_MAGIC
from challenge_plants import add_challenge_plants, COSMETIC_PREDICATE_SITES


class ChallengePlantTests(unittest.TestCase):
    def vm(self, mode=70, challenge=True, seed=15):
        v = VM(mode=mode)
        symbols = {}
        cursor = 0x7D0000

        def emit(name, source):
            nonlocal cursor
            cursor = (cursor + 15) & ~15
            address = cursor
            blob = asm(source, address)
            v.u.mem_write(address, blob)
            cursor += len(blob)
            symbols[name] = address
            return address

        def patch(address, replacement, size=None):
            if size is not None:
                replacement += b'\x90' * (size - len(replacement))
            v.u.mem_write(address, replacement)

        add_challenge_plants(emit, patch, asm, symbols)
        v.symbols = symbols
        v.w(CHALLENGE + 0xB4, CHALLENGE_MAGIC if challenge else 0)
        v.w(PLANT + 0x24, seed)
        v.w(PLANT + 0x10, 80)
        v.w(PLANT + 0x14, 80)
        v.w(PLANT + 0x1C, 2)
        v.u.mem_write(PLANT + 0x144, b'\1')
        return v

    def zombies(self, v, specs):
        """Specs are world rectangle x/y and optional native zombie fields."""
        v.w(BOARD + 0x90, ZOMBIE)
        v.w(BOARD + 0x94, len(specs))
        for i, spec in enumerate(specs):
            p = ZOMBIE + i * 0x15C
            v.w(p, APP)
            v.w(p + 4, BOARD)
            v.w(p + 0x158, 0x10000 + i)
            v.w(p + 0x24, spec.get('kind', 0))
            v.w(p + 0x28, spec.get('phase', 0))
            v.w(p + 0x1C, spec.get('row', 2))
            v.w(p + 0xC8, spec.get('health', 100))
            v.w(p + 0x6C, spec.get('wave', 0))
            v.w(p + 8, spec.get('x', 140))
            v.w(p + 12, spec.get('y', 240))
            v.w(p + 0x150, int(spec.get('eligible', True)))
            v.u.mem_write(p + 0xB8, bytes([spec.get('friendly', 0)]))
            v.u.mem_write(p + 0xEC, bytes([spec.get('dead', 0)]))

        def eligibility(vm):
            p = vm.reg(UC_X86_REG_ESI)
            self.assertEqual(vm.r(vm.reg(UC_X86_REG_ESP) + 4), 127)
            # Rendering-dependent boss eligibility is external to the hook.
            vm.ret(4, vm.r(p + 0x150))

        def rectangle(vm):
            p = vm.reg(UC_X86_REG_EBX)
            dest = vm.reg(UC_X86_REG_EDI)
            for off, value in [(0, vm.r(p + 8)), (4, vm.r(p + 12)),
                               (8, 40), (12, 80)]:
                vm.w(dest + off, value)
            vm.ret()

        v.stubs[0x531A80] = eligibility
        v.stubs[0x5320B0] = rectangle

    def reanimations(self, v, loops=(0, 0, 0, 0)):
        """Real native DataArray IDs for body and all three attached heads."""
        v.w(APP + 0x820, PROFILE)
        v.w(PROFILE + 8, PROFILE + 0x200)
        v.w(PROFILE + 0x200, REANIM)
        v.w(PROFILE + 0x208, len(loops))
        for i, loop in enumerate(loops):
            p = REANIM + i * 0xA0
            v.w(p + 0x9C, 0x10000 + i)
            v.w(p + 4, 0x3F000000)
            v.w(p + 8, 0x41900000)
            v.w(p + 0x10, loop)
            v.w(PLANT + 0x94 + i * 4, 0x10000 + i)

    def trigger(self, v):
        v.reg(UC_X86_REG_ESP, STACK)
        v.w(STACK, STOP)
        v.reg(UC_X86_REG_EAX, PLANT)
        before = [v.reg(r) for r in REGS[1:]]
        v.run(v.symbols['challenge_explosive_trigger'])
        self.assertEqual([v.reg(r) for r in REGS[1:]], before)
        self.assertEqual(v.reg(UC_X86_REG_ESP), STACK + 4)
        return v.reg(UC_X86_REG_EAX)

    def special_stub(self, v):
        def effect(vm):
            self.assertEqual(vm.r(vm.reg(UC_X86_REG_ESP) + 4), PLANT)
            vm.events.append('special')
            vm.u.mem_write(PLANT + 0x141, b'\1')
            # Adversarial native-call volatile registers.
            vm.reg(UC_X86_REG_EAX, 0xAA)
            vm.reg(UC_X86_REG_ECX, 0xBB)
            vm.reg(UC_X86_REG_EDX, 0xCC)
            vm.ret(4)
        v.stubs[0x4666A0] = effect

    def test_scope_serialized_marker_modes_and_nulls(self):
        for mode in (0, 60, 61, 70, 71):
            for marked in (False, True):
                v = self.vm(mode, marked)
                v.reg(UC_X86_REG_EAX, PLANT)
                v.run(v.symbols['challenge_plant_scope'])
                self.assertEqual(v.reg(UC_X86_REG_EAX), int(marked and 61 <= mode <= 70))
        for missing in ('plant', 'app', 'board', 'challenge'):
            v = self.vm()
            if missing == 'app': v.w(PLANT, 0)
            if missing == 'board': v.w(PLANT + 4, 0)
            if missing == 'challenge': v.w(BOARD + 0x160, 0)
            v.reg(UC_X86_REG_EAX, 0 if missing == 'plant' else PLANT)
            v.run(v.symbols['challenge_plant_scope'])
            self.assertEqual(v.reg(UC_X86_REG_EAX), 0)

    def test_cherry_native_circle_rect_inclusive_boundary_and_rows(self):
        cases = [({'x': 255}, 1), ({'x': 256}, 0),
                 ({'x': 240, 'y': 340}, 0),
                 ({'y': 350, 'row': 3}, 1), ({'row': 4}, 0),
                 ({'eligible': False}, 0)]
        for spec, expected in cases:
            with self.subTest(spec=spec):
                v = self.vm(seed=2)
                self.zombies(v, [spec])
                self.assertEqual(self.trigger(v), expected)

    def test_doom_requires_three_in_exact_250_radius_not_nearby_cells(self):
        for count in range(5):
            v = self.vm(seed=15)
            self.zombies(v, [{}] * count)
            self.assertEqual(self.trigger(v), int(count >= 3))
        for spec, expected in [({'x': 390}, 1), ({'x': 391}, 0),
                               ({'row': 5}, 1), ({'row': 6}, 0),
                               ({'row': 6, 'kind': 25}, 1)]:
            v = self.vm(seed=15)
            self.zombies(v, [{}, {}, spec])
            self.assertEqual(self.trigger(v), expected, spec)

    def test_jalapeno_full_row_and_native_boss_row_exception(self):
        for spec, expected in [({'x': 750}, 1), ({'row': 3}, 0),
                               ({'row': 4, 'kind': 25}, 1)]:
            v = self.vm(seed=20)
            self.zombies(v, [spec])
            self.assertEqual(self.trigger(v), expected)

    def test_ice_whole_map_count_excludes_dead_dying_ui_and_friendly(self):
        v = self.vm(seed=14)
        self.zombies(v, [{'x': 700, 'y': 50, 'row': 0},
                         {'x': 40, 'y': 500, 'row': 4}, {}])
        self.assertEqual(self.trigger(v), 1)
        for disqualified in ({'dead': 1}, {'phase': 1}, {'phase': 2},
                             {'phase': 3}, {'health': 0}, {'wave': -2},
                             {'wave': -3}, {'friendly': 1}):
            v = self.vm(seed=14)
            self.zombies(v, [{}, {}, disqualified])
            self.assertEqual(self.trigger(v), 0, disqualified)

    def test_update_waits_then_triggers_immediately_once_preserving_registers(self):
        for seed, threshold in ((2, 1), (20, 1), (14, 3), (15, 3)):
            v = self.vm(seed=seed)
            self.special_stub(v)
            v.w(PLANT + 0x50, 1)
            self.zombies(v, [{}] * (threshold - 1))
            for count in (threshold - 1, threshold, threshold):
                self.zombies(v, [{}] * count)
                v.reg(UC_X86_REG_ESP, STACK)
                v.w(STACK, STOP)
                v.reg(UC_X86_REG_EAX, PLANT)
                before = [v.reg(r) for r in REGS]
                flags = v.reg(UC_X86_REG_EFLAGS)
                v.run(0x463150)
                self.assertEqual([v.reg(r) for r in REGS], before)
                self.assertEqual(v.reg(UC_X86_REG_EFLAGS), flags)
                self.assertEqual(v.reg(UC_X86_REG_ESP), STACK + 4)
                self.assertEqual(v.r(PLANT + 0x50), 0)
            self.assertEqual(v.events, ['special'])

    def test_update_does_not_trigger_asleep_squished_bungee_or_dead(self):
        for off, value in ((0x141, 1), (0x142, 1), (0x143, 1), (0x144, 0)):
            v = self.vm(seed=15)
            v.u.mem_write(PLANT + off, bytes([value]))
            self.zombies(v, [{}] * 3)
            self.special_stub(v)
            v.reg(UC_X86_REG_EAX, PLANT)
            v.run(0x463150)
            self.assertEqual(v.events, [])
        v = self.vm(seed=15)
        v.w(PLANT + 0x134, 1)
        self.zombies(v, [{}] * 3)
        self.special_stub(v)
        v.reg(UC_X86_REG_EAX, PLANT)
        v.run(0x463150)
        self.assertEqual(v.events, [])

    def test_traditional_and_other_plants_enter_original_update_prologue(self):
        for challenge, mode, seed in ((False, 70, 15), (True, 0, 15), (True, 70, 40)):
            v = self.vm(mode, challenge, seed)
            v.reg(UC_X86_REG_EAX, PLANT)
            v.run(0x463150, 0x463155)
            self.assertEqual(v.reg(UC_X86_REG_EDI), PLANT)
            self.assertEqual(v.reg(UC_X86_REG_ESP), STACK - 12)

    def test_setup_wakes_and_freezes_all_native_layers_preserving_weapons(self):
        for seed in (2, 14, 15, 20, 4, 40, 42, 44, 46, 30):
            v = self.vm(seed=seed)
            self.reanimations(v)
            v.w(PLANT + 0x50, 100)
            v.w(PLANT + 0xB0, 500)
            v.w(PLANT + 0x58, 37)
            v.w(PLANT + 0x5C, 80)
            v.u.mem_write(PLANT + 0x143, b'\1')
            def wake(vm):
                self.assertEqual(vm.reg(UC_X86_REG_EAX), PLANT)
                self.assertEqual(vm.r(vm.reg(UC_X86_REG_ESP) + 4), 0)
                vm.u.mem_write(PLANT + 0x143, b'\0')
                vm.ret(4)
            def armed(vm):
                sp = vm.reg(UC_X86_REG_ESP)
                self.assertEqual(vm.reg(UC_X86_REG_EAX), PLANT)
                expected = ([0x657230, 0, 0] if seed == 4
                            else [0x6580D4, 0, 0])
                self.assertEqual([vm.r(sp + i) for i in (4, 8, 12)], expected)
                vm.events.append('armed' if seed == 4 else 'idle')
                vm.ret(12)
            v.stubs[0x45E860] = wake
            v.stubs[0x45FD90] = armed
            v.stub(0x463920, 'refresh')
            v.w(STACK + 4, PLANT)
            v.reg(UC_X86_REG_EAX, CHALLENGE)
            v.run(0x42A530)
            self.assertEqual(v.reg(UC_X86_REG_ESP), STACK + 8)
            self.assertEqual([v.r(REANIM + i * 0xA0 + 8) for i in range(4)], [0] * 4)
            self.assertEqual(v.r(PLANT + 0xB0), 0)
            self.assertEqual(v.r(PLANT + 0x58), 37)
            self.assertEqual(v.r(PLANT + 0x5C), 80)
            self.assertEqual(v.u.mem_read(PLANT + 0x143, 1), b'\0')
            self.assertEqual(v.r(PLANT + 0x50), 0 if seed in (2, 14, 15, 20) else 100)
            if seed == 4:
                self.assertEqual(v.r(PLANT + 0x3C), 16)
                self.assertEqual(v.events, ['armed', 'refresh'])

    def test_waiting_bombs_reset_native_anim_idle_to_visible_first_frame(self):
        for seed in (2, 20):
            v = self.vm(seed=seed)
            v.w(APP + 0x820, PROFILE)
            v.w(PROFILE + 8, PROFILE + 0x200)
            v.w(PROFILE + 0x200, REANIM)
            v.w(PROFILE + 0x208, 1)
            v.w(PLANT + 0x94, 0x10000)
            v.w(REANIM + 0x9C, 0x10000)
            v.w(REANIM + 4, 0x3F800000)
            v.w(REANIM + 8, 0x41900000)
            v.w(REANIM + 0x5C, 1)
            def frames(vm):
                self.assertEqual(vm.reg(UC_X86_REG_EAX), REANIM)
                self.assertEqual(vm.reg(UC_X86_REG_EDX), 0x6580D4)
                vm.events.append('native_idle_frames')
                vm.ret(8)
            v.stubs[0x4731D0] = frames
            v.stub(0x45E860, 'awake', pop=4)
            v.stub(0x463920, 'refresh')
            v.w(STACK + 4, PLANT)
            v.reg(UC_X86_REG_EAX, CHALLENGE)
            v.run(0x42A530)
            self.assertEqual(v.r(REANIM + 4), 0)
            self.assertEqual(v.r(REANIM + 8), 0)
            self.assertEqual(v.r(REANIM + 0x5C), 0)
            self.assertEqual(v.events, ['awake', 'native_idle_frames', 'refresh'])

    def test_traditional_setup_prologue_and_cosmetic_predicates(self):
        v = self.vm(challenge=False)
        v.reg(UC_X86_REG_EAX, CHALLENGE)
        v.w(APP + 0x820, PROFILE)
        v.run(0x42A530, 0x42A538)
        self.assertEqual(v.reg(UC_X86_REG_ECX), APP)
        self.assertEqual(v.reg(UC_X86_REG_EDX), PROFILE)
        for mode, challenge, expected in ((70, False, 1), (70, True, 1),
                                           (0, True, 0), (61, True, 1)):
            v = self.vm(mode, challenge)
            v.reg(UC_X86_REG_EAX, APP)
            v.run(0x4537D0)
            self.assertEqual(v.reg(UC_X86_REG_EAX) & 255, expected)
        for site in COSMETIC_PREDICATE_SITES:
            self.assertEqual(bytes(v.u.mem_read(site, 5)), asm('call 0x4537d0', site))
        self.assertEqual(bytes(v.u.mem_read(0x461EB9, 6)), asm('mov esi, dword ptr [ebx+0x94]', 0x461EB9))

    def test_old_save_idle_layers_freeze_without_resetting_active_combat_state(self):
        for seed in (6, 14, 15, 23, 27, 30, 40, 42, 44, 48):
            v = self.vm(seed=seed)
            self.reanimations(v, (0, 3, 0, 3))
            fields = {0x3C: 26, 0x50: 0, 0x54: 140, 0x58: 80,
                      0x90: 19, 0xD8: 12, 0x12C: 0x10001}
            for off, value in fields.items(): v.w(PLANT + off, value)
            v.w(PLANT + 0xB0, 500)
            v.reg(UC_X86_REG_EAX, PLANT)
            before = [v.reg(r) for r in REGS]
            flags = v.reg(UC_X86_REG_EFLAGS)
            v.run(v.symbols['challenge_cardboard_idle'])
            self.assertEqual([v.reg(r) for r in REGS], before)
            self.assertEqual(v.reg(UC_X86_REG_EFLAGS), flags)
            self.assertEqual(v.reg(UC_X86_REG_ESP), STACK + 4)
            self.assertEqual([v.r(REANIM + i * 0xA0 + 8) for i in range(4)],
                             [0, 0x41900000, 0, 0x41900000])
            self.assertEqual({off: v.r(PLANT + off) for off in fields}, fields)
            self.assertEqual(v.r(PLANT + 0xB0), 0)

    def test_upgrade_shooting_retains_native_gatling_and_gloom_burst_cadence(self):
        for seed, counters in ((40, (19, 36, 52, 69)), (42, (127, 99, 71, 43))):
            for count in counters:
                v = self.vm(seed=seed)
                self.reanimations(v, (0, 3, 0, 0))
                v.w(PLANT + 0x90, count)
                def fire(vm):
                    sp = vm.reg(UC_X86_REG_ESP)
                    self.assertEqual([vm.r(sp + i) for i in (4, 8, 12, 16)],
                                     [PLANT, 0, 2, 0])
                    vm.events.append('fire')
                    vm.ret(16)
                v.stubs[0x466E00] = fire
                v.reg(UC_X86_REG_EAX, PLANT)
                # Execute the challenge idle treatment and real native
                # UpdateAbilities -> UpdateShooting, stopping after the call.
                v.run(0x463150, 0x463245)
                self.assertEqual(v.r(PLANT + 0x90), count - 1)
                self.assertEqual(v.r(REANIM + 8), 0)
                self.assertEqual(v.r(REANIM + 0xA0 + 8), 0x41900000)
                self.assertEqual(v.events, ['fire'])

    def test_bombs_stay_still_and_retain_native_flash_bookkeeping(self):
        for seed in (2, 20):
            v = self.vm(seed=seed)
            v.w(PLANT + 0xC0, 0x3F800000)
            v.w(PLANT + 0xC4, 0x3F800000)
            v.w(PLANT + 0xB4, 8)
            v.w(PLANT + 0xB8, 7)
            v.w(PLANT + 0xBC, 6)
            v.reg(UC_X86_REG_EAX, PLANT)
            v.run(0x464DB0, 0x464E3C)
            self.assertEqual(v.r(PLANT + 0xC0), 0)
            self.assertEqual(v.r(PLANT + 0xC4), 0)
            self.assertEqual([v.r(PLANT + off) for off in (0xB4, 0xB8, 0xBC)], [7, 6, 5])
        for challenge, mode, seed in ((False, 70, 2), (True, 0, 20), (True, 70, 40)):
            v = self.vm(mode, challenge, seed)
            v.reg(UC_X86_REG_EAX, PLANT)
            v.run(0x464DB0, 0x464DB6)
            self.assertEqual(v.reg(UC_X86_REG_ESP), STACK - 4)
            self.assertEqual(v.reg(UC_X86_REG_EDI), PLANT)
            self.assertEqual(v.reg(UC_X86_REG_EAX), seed)

    def test_imitater_target_gets_setup_before_gray_filter(self):
        for challenge in (False, True):
            v = self.vm(challenge=challenge, seed=15)
            old = PLANT + 0x200
            v.w(old + 0x138, 15)
            def setup(vm):
                self.assertEqual(vm.reg(UC_X86_REG_EAX), CHALLENGE)
                self.assertEqual(vm.r(vm.reg(UC_X86_REG_ESP) + 4), PLANT)
                vm.events.append('setup')
                vm.ret(4)
            v.stubs[0x42A530] = setup
            v.reg(UC_X86_REG_EAX, PLANT)
            v.reg(UC_X86_REG_ESI, old)
            v.run(0x466BA2, 0x466BA8)
            self.assertEqual(v.reg(UC_X86_REG_EAX), PLANT)
            self.assertEqual(v.reg(UC_X86_REG_ECX), 15)
            self.assertEqual(v.reg(UC_X86_REG_ESI), old)
            self.assertEqual(v.events, ['setup'] if challenge else [])

    def test_ice_and_doom_are_chewable_and_only_lethal_bite_detonates(self):
        for seed in (14, 15):
            v = self.vm(seed=seed)
            self.special_stub(v)
            v.w(PLANT + 0x40, 8)
            v.w(APP, PROFILE)
            v.w(PROFILE + 0xD8, 0x800100)
            v.stub(0x800100, 'gulp', pop=4)
            v.reg(UC_X86_REG_ESI, PLANT)
            v.reg(UC_X86_REG_EBP, ZOMBIE)
            v.reg(UC_X86_REG_ECX, seed)
            v.reg(UC_X86_REG_EBX, 17)
            v.run(0x52FC24, 0x52FDEE)
            self.assertEqual(v.r(PLANT + 0x40), 4)
            self.assertEqual(v.events, [])
            v.reg(UC_X86_REG_ESI, PLANT)
            v.reg(UC_X86_REG_EBP, ZOMBIE)
            v.reg(UC_X86_REG_ECX, seed)
            v.reg(UC_X86_REG_EBX, 17)
            v.run(0x52FC24, 0x52FD5A)
            self.assertEqual(v.r(PLANT + 0x40), 0)
            self.assertEqual(v.events, ['gulp', 'special'])
            self.assertEqual(v.reg(UC_X86_REG_EBX), 1)
            self.assertEqual(v.r(BOARD + 0x5798), 1)

    def test_eaten_wrapper_never_changes_traditional_or_nonmushroom_death(self):
        for challenge, mode, seed, dead, expected in (
            (True, 70, 14, 0, 'special'), (True, 70, 15, 0, 'special'),
            (False, 70, 14, 0, 'die'), (True, 0, 14, 0, 'die'),
            (True, 70, 2, 0, 'die'), (True, 70, 15, 1, 'die'),
        ):
            v = self.vm(mode, challenge, seed)
            v.u.mem_write(PLANT + 0x141, bytes([dead]))
            self.special_stub(v)
            v.stub(0x4679B0, 'die', pop=4)
            v.w(STACK + 4, PLANT)
            v.run(v.symbols['challenge_mushroom_eaten'])
            self.assertEqual(v.events, [expected])
            self.assertEqual(v.reg(UC_X86_REG_ESP), STACK + 8)

    def test_native_next_stage_clear_removes_crater_and_brains_before_stage(self):
        v = self.vm()
        v.w(APP + 0x820, PROFILE)
        v.w(PROFILE, REANIM)
        v.w(PROFILE + 8, REANIM)
        v.w(BOARD + 0x11C, BRAIN)
        v.w(BOARD + 0x120, 2)
        for i, kind in enumerate((2, 12)):
            p = BRAIN + i * 0xEC
            v.w(p, APP)
            v.w(p + 4, BOARD)
            v.w(p + 8, kind)
            v.w(p + 0xE8, 0x10000 + i)
        v.w(CHALLENGE + 0x6C, 7)
        v.reg(UC_X86_REG_EDI, CHALLENGE)
        v.reg(UC_X86_REG_EBX, 0)
        v.run(0x429FC8, 0x42A000)
        for i in range(2):
            self.assertEqual(v.u.mem_read(BRAIN + i * 0xEC + 0x20, 1), b'\1')
        self.assertEqual(v.r(CHALLENGE + 0x6C), 8)


if __name__ == '__main__':
    unittest.main()
