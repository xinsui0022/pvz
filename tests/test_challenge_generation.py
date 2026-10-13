"""Run challenge placement, native enumeration and live-board limits as x86."""
from collections import Counter
import random
from test_machine_code import *
del PatchTests
from challenge_mode import CHALLENGE_FIELD, CHALLENGE_MAGIC
from challenge_generation import (EXCLUDED_SEEDS, PLANT_WEIGHTS, FAMILY_WEIGHTS,
    SEED_FAMILY, PUMPKIN_CHANCE, FAMILY_CHANCE, _tickets, ONE_SHOT_SEEDS,
    INSTANT_NATIVE_SEEDS, INSTANT_GLOBAL_WEIGHTS, ATTACK_WEIGHTS,
    PUMPKIN_BLOCKED_SEEDS, STAGE_PROFILE_FIELD, MAGNET_LIMIT_FIELD,
    PROFILE_NORMAL, PROFILE_INSTANT, PROFILE_STAR)

PLANTS_BASE = 0x3000000


def symbol(name):
    return int(MANIFEST['symbols'][name], 16)


class ChallengeGenerationTests(unittest.TestCase):
    def field(self, mode=70, challenge=True):
        vm = VM(mode=mode)
        vm.w(CHALLENGE + CHALLENGE_FIELD, CHALLENGE_MAGIC if challenge else 0)
        vm.w(CHALLENGE + MAGNET_LIMIT_FIELD, 1)
        return vm

    def rng(self, vm, tickets):
        remaining = iter(tickets)
        def pick(v):
            maximum = v.reg(UC_X86_REG_EAX)
            ticket = next(remaining)
            self.assertGreater(maximum, ticket)
            self.assertGreaterEqual(ticket, 0)
            v.reg(UC_X86_REG_ECX, 0xaaaa)
            v.reg(UC_X86_REG_EDX, 0xbbbb)
            v.ret(eax=ticket)
        vm.stubs[0x5af400] = pick

    def call(self, vm, name, seed=37):
        vm.reg(UC_X86_REG_ESP, STACK)
        vm.w(STACK, STOP)
        vm.reg(UC_X86_REG_EAX, seed)
        vm.run(symbol(name))
        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK + 4)
        return vm.reg(UC_X86_REG_EAX)

    def existing(self, vm, seed, row=4, imitate=-1, dead=False, active=True):
        ptr = PLANTS_BASE + vm.array_count * 0x14c
        vm.array_count += 1
        vm.w(BOARD + 0xb0, vm.array_count)
        vm.w(ptr, APP)
        vm.w(ptr + 4, BOARD)
        vm.w(ptr + 0x1c, row)
        vm.w(ptr + 0x24, seed)
        vm.w(ptr + 0x138, imitate)
        vm.w(ptr + 0x148, 0x10000 | vm.array_count if active else vm.array_count)
        vm.u.mem_write(ptr + 0x141, bytes([dead]))
        return ptr

    def allocation(self, vm, reject=False, magnet=True):
        vm.u.mem_map(PLANTS_BASE, 0x10000)
        vm.w(BOARD + 0xac, PLANTS_BASE)
        vm.w(BOARD + 0xb0, 0)
        vm.array_count = 0
        vm.created, vm.checked = [], []
        if magnet:
            self.existing(vm, 31)
        def can_plant(v):
            sp = v.reg(UC_X86_REG_ESP)
            self.assertEqual(v.r(sp + 4), BOARD)
            position = (v.r(sp + 8), v.reg(UC_X86_REG_EAX))
            seed = v.r(sp + 12)
            v.checked.append((position, seed))
            v.reg(UC_X86_REG_ECX, 0xcccc)
            v.reg(UC_X86_REG_EDX, 0xdddd)
            v.ret(12, 1 if reject else 0)
        def new_plant(v):
            sp = v.reg(UC_X86_REG_ESP)
            self.assertEqual(v.reg(UC_X86_REG_EAX), BOARD)
            args = tuple(v.r(sp + i) for i in (4, 8, 12, 16))
            v.created.append(args)
            ptr = self.existing(v, args[2], args[1], args[3])
            v.reg(UC_X86_REG_ECX, 0xcccc)
            v.reg(UC_X86_REG_EDX, 0xdddd)
            v.ret(16, ptr)
        def setup(v):
            self.assertEqual(v.reg(UC_X86_REG_EAX), CHALLENGE)
            ptr = v.r(v.reg(UC_X86_REG_ESP) + 4)
            self.assertEqual(v.r(ptr + 4), BOARD)
            v.events.append(('setup', v.r(ptr + 0x24)))
            v.reg(UC_X86_REG_ECX, 0xeeee)
            v.reg(UC_X86_REG_EDX, 0xffff)
            v.ret(4)
        vm.stubs[0x40e020] = can_plant
        vm.stubs[0x40ce20] = new_plant
        vm.stubs[0x42a530] = setup

    def square(self, vm, seed=37, col=2, row=3):
        vm.reg(UC_X86_REG_ESP, STACK)
        vm.w(STACK, STOP)
        vm.w(STACK + 4, col)
        vm.w(STACK + 8, row)
        vm.reg(UC_X86_REG_EBX, seed)
        vm.reg(UC_X86_REG_EDI, CHALLENGE)
        before = [vm.reg(r) for r in REGS]
        vm.run(0x42a660)
        self.assertEqual([vm.reg(r) for r in REGS], before)
        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK + 12)

    def force_selection(self, vm, seed, imitate=None, pumpkin=99):
        # Override only randomness results; counts, caps, fallback selection,
        # allocation, hook prologues and native row enumeration still execute.
        vm.stubs[symbol('iz_challenge_pick_plant')] = lambda v: v.ret(eax=seed)
        if imitate is not None:
            vm.stubs[symbol('iz_challenge_pick_imitater_target')] = lambda v: v.ret(eax=imitate)
        def rng(v):
            size = v.reg(UC_X86_REG_EAX)
            ticket = pumpkin if size == 100 else _tickets(ATTACK_WEIGHTS).index(44)
            self.assertLess(ticket, size)
            v.ret(eax=ticket)
        vm.stubs[0x5af400] = rng

    def test_role_pools_exclude_sun_shroom_and_bombs_from_persistent_slots(self):
        vm = self.field()
        results = []
        for ticket in range(sum(PLANT_WEIGHTS.values())):
            self.rng(vm, (ticket,))
            results.append(self.call(vm, 'iz_challenge_pick_plant'))
        self.assertEqual(Counter(results), Counter(PLANT_WEIGHTS))
        self.assertFalse(set(results) & (EXCLUDED_SEEDS | ONE_SHOT_SEEDS))
        allowed = set(PLANT_WEIGHTS) | set(INSTANT_GLOBAL_WEIGHTS) | {30}
        self.assertEqual(allowed, set(range(49)) - EXCLUDED_SEEDS - {1})
        self.assertNotIn(1, PLANT_WEIGHTS)
        self.assertEqual(PLANT_WEIGHTS[41], 5)
        self.assertGreater(PLANT_WEIGHTS[40], PLANT_WEIGHTS[0] + PLANT_WEIGHTS[7])
        self.assertGreater(PLANT_WEIGHTS[23], PLANT_WEIGHTS[3])
        self.assertGreater(PLANT_WEIGHTS[39] + PLANT_WEIGHTS[44],
                           PLANT_WEIGHTS[32] + PLANT_WEIGHTS[34])
        self.assertGreater(INSTANT_GLOBAL_WEIGHTS[2] + INSTANT_GLOBAL_WEIGHTS[20]
                           + INSTANT_GLOBAL_WEIGHTS[15],
                           INSTANT_GLOBAL_WEIGHTS[4] + INSTANT_GLOBAL_WEIGHTS[17])
        for weights in FAMILY_WEIGHTS.values():
            self.assertFalse(set(weights) & EXCLUDED_SEEDS)

    def test_family_tickets_and_seventy_percent_boundary_execute(self):
        vm = self.field()
        for seed, family in SEED_FAMILY.items():
            weights = FAMILY_WEIGHTS[family]
            results = []
            for ticket in range(sum(weights.values())):
                self.rng(vm, (FAMILY_CHANCE - 1, ticket))
                results.append(self.call(vm, 'iz_challenge_pick_plant', seed))
            self.assertEqual(Counter(results), Counter(weights))
            global_weights = INSTANT_GLOBAL_WEIGHTS if seed in INSTANT_NATIVE_SEEDS else PLANT_WEIGHTS
            self.rng(vm, (FAMILY_CHANCE, _tickets(global_weights).index(37)))
            self.assertEqual(self.call(vm, 'iz_challenge_pick_plant', seed), 37)

    def test_native_sunflower_slots_upgrade_without_moving_or_adding_income(self):
        vm = self.field()
        vm.stubs[0x5af400] = lambda v: self.fail('Preserved native selector rolled RNG')
        self.assertEqual(self.call(vm, 'iz_challenge_pick_plant', 1), 41)
        for seed in (41, 29, 31):
            self.assertEqual(self.call(vm, 'iz_challenge_pick_plant', seed), seed)
        self.allocation(vm)
        self.rng(vm, (99,))
        self.square(vm, seed=1)
        self.assertEqual(vm.created, [(2, 3, 41, 0xffffffff)])

    def test_direct_upgrade_allocation_and_pumpkin_are_separate_layers(self):
        for seed in (23, 39, 40, 41, 42, 44, 46):
            vm = self.field()
            self.allocation(vm)
            tickets = (_tickets(PLANT_WEIGHTS).index(seed),)
            if seed != 46:
                tickets += (PUMPKIN_CHANCE - 1,)
            self.rng(vm, tickets)
            self.square(vm)
            expected = [(2, 3, seed, 0xffffffff)]
            if seed != 46:
                expected.append((2, 3, 30, 0xffffffff))
            self.assertEqual(vm.created, expected)
            self.assertEqual([s for _, s in vm.checked],
                             [37] if seed == 46 else [37, 30])
            self.assertEqual(vm.events, [('setup', p[2]) for p in expected])

    def test_pumpkin_twenty_percent_boundary_and_invalid_square(self):
        ticket = _tickets(PLANT_WEIGHTS).index(40)
        for roll, count in ((0, 2), (19, 2), (20, 1), (99, 1)):
            vm = self.field()
            self.allocation(vm)
            self.rng(vm, (ticket, roll))
            self.square(vm)
            self.assertEqual(len(vm.created), count)
        vm = self.field()
        self.allocation(vm, reject=True)
        vm.stubs[0x5af400] = lambda v: self.fail('Invalid square selected a plant')
        self.square(vm)
        self.assertEqual(vm.created, [])

    def test_pumpkin_never_covers_disposable_actual_or_imitater_targets(self):
        for seed in PUMPKIN_BLOCKED_SEEDS:
            for mimic in (False, True):
                vm = self.field()
                self.allocation(vm)
                self.force_selection(vm, 48 if mimic else seed,
                                     imitate=seed if mimic else None, pumpkin=0)
                self.square(vm, seed=4)
                self.assertEqual(vm.created, [(2, 3, 48 if mimic else seed,
                                              seed if mimic else 0xffffffff)])
        vm = self.field()
        self.allocation(vm)
        self.force_selection(vm, 6, pumpkin=0)
        self.square(vm, seed=6)
        self.assertEqual([p[2] for p in vm.created], [6, 30])

    def test_imitater_pool_obeys_source_role_and_never_recurses(self):
        vm = self.field()
        for native, pool in ((37, PLANT_WEIGHTS), (4, INSTANT_GLOBAL_WEIGHTS)):
            weights = {s: w for s, w in pool.items() if s != 48}
            results = []
            for ticket in range(sum(weights.values())):
                self.rng(vm, (ticket,))
                results.append(self.call(vm, 'iz_challenge_pick_imitater_target', native))
            self.assertEqual(Counter(results), Counter(weights))
            self.assertNotIn(9, results)
            self.assertNotIn(1, results)
            self.assertNotIn(48, results)
            if native == 37:
                self.assertFalse(set(results) & ONE_SHOT_SEEDS)
        vm = self.field()
        self.allocation(vm)
        self.rng(vm, (_tickets(PLANT_WEIGHTS).index(48),
                      _tickets({s: w for s, w in PLANT_WEIGHTS.items() if s != 48}).index(44), 99))
        self.square(vm)
        self.assertEqual(vm.created, [(2, 3, 48, 44)])

    def test_scanner_matches_native_active_dead_and_imitater_fields(self):
        vm = self.field()
        self.allocation(vm, magnet=False)
        for seed, row, imitate, dead, active in ((48, 2, 14, False, True),
                (15, 2, -1, False, True), (48, 1, 31, False, True),
                (14, 2, -1, True, True), (14, 2, -1, False, False),
                (14, 0, -1, False, True), (30, 2, -1, False, True)):
            self.existing(vm, seed, row, imitate, dead, active)
        out = BOARD + 0x400
        vm.reg(UC_X86_REG_EAX, BOARD)
        vm.reg(UC_X86_REG_EDX, 2)
        vm.reg(UC_X86_REG_ECX, out)
        before = [vm.reg(r) for r in REGS]
        vm.run(symbol('iz_challenge_count_plants'))
        self.assertEqual([vm.r(out + n) for n in (0, 4, 8, 12)], [3, 2, 2, 1])
        self.assertEqual([vm.reg(r) for r in REGS], before)
        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK + 4)

    def test_scanner_counts_match_real_native_iterator_on_random_data_arrays(self):
        rnd = random.Random(1310)
        for _ in range(48):
            vm = self.field()
            self.allocation(vm, magnet=False)
            row = rnd.randrange(5)
            for _ in range(rnd.randrange(1, 35)):
                self.existing(vm, rnd.choice((1, 2, 4, 14, 15, 17, 20, 31, 40, 48)),
                              row=rnd.randrange(5), imitate=rnd.choice((14, 15, 31, 40)),
                              dead=rnd.randrange(5) == 0, active=rnd.randrange(4) != 0)
            out, iterator = BOARD + 0x400, PROFILE + 0x200
            vm.reg(UC_X86_REG_EAX, BOARD)
            vm.reg(UC_X86_REG_EDX, row)
            vm.reg(UC_X86_REG_ECX, out)
            vm.run(symbol('iz_challenge_count_plants'))
            actual = [vm.r(out + n) for n in (0, 4, 8, 12)]
            vm.w(iterator, 0)
            expected = [0] * 4
            while True:
                vm.reg(UC_X86_REG_ESP, STACK)
                vm.w(STACK, STOP)
                vm.reg(UC_X86_REG_EDX, BOARD)
                vm.reg(UC_X86_REG_ESI, iterator)
                vm.run(0x41c950)  # The unmodified game's real PlantIterator.
                if not vm.reg(UC_X86_REG_EAX) & 255:
                    self.assertEqual(vm.r(iterator), 0xffffffff)
                    break
                plant = vm.r(iterator)
                seed = vm.r(plant + 0x24)
                if seed == 48:
                    seed = vm.r(plant + 0x138)
                if seed in ONE_SHOT_SEEDS:
                    expected[0] += 1
                    expected[1] += vm.r(plant + 0x1c) == row
                expected[2] += seed == 14
                expected[3] += seed == 31
            self.assertEqual(actual, expected)

    def test_normal_instant_total_and_row_caps_use_bounded_attack_fallback(self):
        for seed in ONE_SHOT_SEEDS:
            vm = self.field()
            self.allocation(vm)
            self.force_selection(vm, seed)
            for row in (0, 0, 1, 2, 3, 4):
                self.square(vm, seed=4, row=row)
            actual = [p[2] for p in vm.created]
            expected = [seed, 44, seed, seed, 44, 44]
            if seed == 14:
                expected = [seed, 44, seed, 44, 44, 44]
            self.assertEqual(actual, expected)
        vm = self.field()
        self.allocation(vm)
        self.force_selection(vm, 48, imitate=15)
        for row in range(5):
            self.square(vm, seed=4, row=row)
        self.assertEqual([p[2:] for p in vm.created],
                         [(48, 15)] * 3 + [(44, 0xffffffff)] * 2)

    def test_special_instants_allow_many_bombs_but_only_two_ice_including_mimics(self):
        for mimic in (False, True):
            vm = self.field()
            self.allocation(vm)
            vm.w(CHALLENGE + STAGE_PROFILE_FIELD, PROFILE_INSTANT)
            self.force_selection(vm, 48 if mimic else 14, imitate=14 if mimic else None)
            for _ in range(7):
                self.square(vm, seed=4)
            self.assertEqual([p[2:] for p in vm.created],
                             [(48, 14) if mimic else (14, 0xffffffff)] * 2
                             + [(44, 0xffffffff)] * 5)
        vm = self.field()
        self.allocation(vm)
        vm.w(CHALLENGE + STAGE_PROFILE_FIELD, PROFILE_INSTANT)
        self.force_selection(vm, 15)
        for _ in range(7):
            self.square(vm, seed=4)
        self.assertEqual([p[2] for p in vm.created], [15] * 7)

    def test_every_board_gets_magnet_and_normal_surplus_becomes_attacker(self):
        vm = self.field()
        self.allocation(vm, magnet=False)
        self.rng(vm, (99,))
        self.square(vm, seed=1)
        self.assertEqual(vm.created[0][2], 41)
        self.force_selection(vm, 40)
        self.square(vm, seed=37)
        self.assertEqual(vm.created[1][2], 31)
        self.force_selection(vm, 31)
        self.square(vm, seed=37)
        self.assertEqual(vm.created[2][2], 44)
        vm.w(CHALLENGE + MAGNET_LIMIT_FIELD, 2)
        self.square(vm, seed=31)
        self.square(vm, seed=31)
        self.assertEqual([p[2] for p in vm.created[-2:]], [31, 44])
        self.existing(vm, 48, imitate=31)
        vm.w(CHALLENGE + MAGNET_LIMIT_FIELD, 3)
        self.square(vm, seed=31)
        self.assertEqual(vm.created[-1][2], 44)

    def test_native_magnet_batch_counts_existing_guaranteed_magnet(self):
        for requested in (1, 2, 8):
            vm = self.field()
            self.allocation(vm, magnet=False)
            self.force_selection(vm, 40)
            self.square(vm)
            self.assertEqual(vm.created[0][2], 31)
            del vm.stubs[symbol('iz_challenge_pick_plant')]
            def rng(v):
                n = v.reg(UC_X86_REG_EAX)
                ticket = 99 if n == 100 else (
                    _tickets(ATTACK_WEIGHTS).index(44)
                    if n == sum(ATTACK_WEIGHTS.values()) else 0)
                v.ret(eax=ticket)
            vm.stubs[0x5af400] = rng
            vm.reg(UC_X86_REG_ESP, STACK)
            vm.w(STACK, STOP)
            vm.w(STACK + 4, CHALLENGE)
            vm.w(STACK + 8, 31)
            vm.w(STACK + 12, requested)
            vm.reg(UC_X86_REG_EAX, 0xffffffff)
            vm.run(0x42a6c0)
            self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK + 16)
            self.assertEqual(Counter(p[2] for p in vm.created),
                             Counter({31: requested, 44: 1}))

    def test_traditional_and_other_modes_replay_original_hook_bytes(self):
        for mode, marker in ((61, False), (70, False), (60, True), (71, True)):
            vm = self.field(mode, marker)
            vm.reg(UC_X86_REG_EDI, CHALLENGE)
            vm.reg(UC_X86_REG_ECX, 0x1234)
            vm.w(STACK + 4, 2)
            vm.run(0x42a660, 0x42a665)
            self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK - 4)
            self.assertEqual(vm.r(STACK - 4), 0x1234)
            self.assertEqual(vm.reg(UC_X86_REG_EAX), 2)
            vm = self.field(mode, marker)
            vm.reg(UC_X86_REG_ECX, CHALLENGE)
            vm.reg(UC_X86_REG_EAX, BOARD)
            def allocate(v):
                self.assertEqual(v.reg(UC_X86_REG_ESI), BOARD + 0xac)
                v.ret(eax=PLANT)
            vm.stubs[0x41de80] = allocate
            vm.run(0x42a838, 0x42a843)
            self.assertEqual(vm.reg(UC_X86_REG_EAX), PLANT)
            self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK)

    def formation_entry(self, vm, seed, count, row=-1):
        vm.reg(UC_X86_REG_ESP, STACK)
        vm.w(STACK, STOP)
        vm.w(STACK + 4, CHALLENGE)
        vm.w(STACK + 8, seed)
        vm.w(STACK + 12, count)
        vm.reg(UC_X86_REG_EAX, row & 0xffffffff)
        before = [vm.reg(r) for r in REGS]
        vm.run(0x42a6c0, 0x42a6c6)
        self.assertEqual([vm.reg(r) for r in REGS], before)
        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK - 0x298)

    def test_formation_profile_only_marks_native_special_batches_and_magnet_limits(self):
        cases = ((4, 9, -1, PROFILE_INSTANT, 1),
                 (4, 4, -1, PROFILE_INSTANT, 1),
                 (4, 3, -1, PROFILE_NORMAL, 1),
                 (4, 9, 0, PROFILE_NORMAL, 1),
                 (29, 4, -1, PROFILE_STAR, 1),
                 (21, 9, -1, PROFILE_STAR, 1),
                 (31, 2, -1, PROFILE_NORMAL, 2),
                 (31, 8, -1, PROFILE_NORMAL, 8))
        for seed, count, row, profile, limit in cases:
            vm = self.field()
            self.formation_entry(vm, seed, count, row)
            self.assertEqual(vm.r(CHALLENGE + STAGE_PROFILE_FIELD), profile)
            self.assertEqual(vm.r(CHALLENGE + MAGNET_LIMIT_FIELD), limit)
        for mode, marker in ((70, False), (60, True), (71, True)):
            vm = self.field(mode, marker)
            self.formation_entry(vm, 4, 9)
            self.assertEqual(vm.r(CHALLENGE + STAGE_PROFILE_FIELD), 0)
            self.assertEqual(vm.r(CHALLENGE + MAGNET_LIMIT_FIELD), 1)

    def test_stage_init_resets_only_challenge_and_replays_native_registers_flags(self):
        for mode, marker, resets in ((70, True, True), (61, True, True),
                                     (70, False, False), (60, True, False), (71, True, False)):
            vm = self.field(mode, marker)
            vm.w(CHALLENGE + STAGE_PROFILE_FIELD, 2)
            vm.w(CHALLENGE + MAGNET_LIMIT_FIELD, 8)
            vm.reg(UC_X86_REG_EBP, STACK)
            vm.w(STACK + 8, CHALLENGE)
            vm.reg(UC_X86_REG_EBX, 123)
            vm.run(0x42a89c, 0x42a8a1)
            self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK)
            self.assertEqual(vm.reg(UC_X86_REG_EDI), CHALLENGE)
            self.assertEqual(vm.reg(UC_X86_REG_EBX), 0)
            self.assertTrue(vm.reg(UC_X86_REG_EFLAGS) & 0x40)
            self.assertEqual(vm.r(CHALLENGE + STAGE_PROFILE_FIELD), 0 if resets else 2)
            self.assertEqual(vm.r(CHALLENGE + MAGNET_LIMIT_FIELD), 1 if resets else 8)

    def batch(self, mode=70, seed=37, row=-1, count=30, blocked=(), selected=None, mimic=None):
        vm = self.field(mode)
        self.allocation(vm, magnet=False)
        blocked = set(blocked)
        native_check = vm.stubs[0x40e020]
        def can_plant(v):
            sp = v.reg(UC_X86_REG_ESP)
            position = (v.r(sp + 8), v.reg(UC_X86_REG_EAX))
            self.assertEqual(v.r(sp + 12), seed)
            native_check(v)
            v.reg(UC_X86_REG_EAX, int(position in blocked))
        vm.stubs[0x40e020] = can_plant
        if selected is not None:
            self.force_selection(vm, selected, imitate=mimic)
        def random(v):
            n = v.reg(UC_X86_REG_EAX)
            if n == 100:
                value = 99
            elif n == sum(PLANT_WEIGHTS.values()):
                value = _tickets(PLANT_WEIGHTS).index(40)
            elif n == sum(ATTACK_WEIGHTS.values()):
                value = _tickets(ATTACK_WEIGHTS).index(44)
            elif n == sum(INSTANT_GLOBAL_WEIGHTS.values()):
                value = _tickets(INSTANT_GLOBAL_WEIGHTS).index(15)
            else:
                value = 0  # Native weighted grid draw.
            self.assertLess(value, n)
            v.ret(eax=value)
        vm.stubs[0x5af400] = random
        vm.reg(UC_X86_REG_EAX, row & 0xffffffff)
        vm.w(STACK + 4, CHALLENGE)
        vm.w(STACK + 8, seed)
        vm.w(STACK + 12, count)
        vm.run(0x42a6c0)
        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK + 16)
        return vm

    def test_native_batch_keeps_column_row_count_and_empty_cell_restrictions(self):
        for mode, columns, row in ((61, 4, -1), (69, 6, -1), (70, 5, 2)):
            blocked = {(0, 0), (2, 2)}
            vm = self.batch(mode=mode, row=row, blocked=blocked)
            rows = range(5) if row == -1 else (row,)
            expected = {(c, r) for r in rows for c in range(columns)} - blocked
            self.assertEqual({p[:2] for p in vm.created}, expected)
            self.assertEqual(len(vm.created), len(expected))
            self.assertEqual(Counter(p[2] for p in vm.created), Counter({31: 1, 40: len(expected) - 1}))
        vm = self.batch(seed=3, count=20)
        self.assertEqual({p[:2] for p in vm.created},
                         {(c, r) for r in range(5) for c in (2, 3, 4)})
        self.assertEqual(Counter(p[2] for p in vm.created), Counter({31: 1, 40: 14}))
        vm = self.batch(count=7)
        self.assertEqual(len(vm.created), 7)

    def test_native_batch_special_ice_and_magnet_limits_survive_adversarial_picks(self):
        vm = self.batch(seed=4, count=9, selected=15)
        self.assertEqual(vm.r(CHALLENGE + STAGE_PROFILE_FIELD), PROFILE_INSTANT)
        self.assertEqual(Counter(p[2] for p in vm.created), Counter({31: 1, 15: 8}))
        for mimic in (None, 14):
            vm = self.batch(seed=4, count=9, selected=14 if mimic is None else 48, mimic=mimic)
            actual = Counter(p[3] if p[2] == 48 else p[2] for p in vm.created)
            self.assertEqual(actual, Counter({31: 1, 14: 2, 44: 6}))
        for requested in (2, 8):
            vm = self.batch(seed=31, count=requested)
            self.assertEqual(Counter(p[2] for p in vm.created), Counter({31: requested}))
        vm = self.batch(seed=31, count=8, selected=48, mimic=31)
        self.assertEqual(Counter(p[3] if p[2] == 48 else p[2] for p in vm.created), Counter({31: 8}))
        vm = self.batch(seed=29, count=8)
        self.assertEqual(Counter(p[2] for p in vm.created), Counter({31: 1, 29: 7}))


if __name__ == '__main__':
    unittest.main()
