"""Run the allocation hooks and weighted selectors as actual assembled x86."""
from collections import Counter
from test_machine_code import *
del PatchTests
from challenge_mode import CHALLENGE_FIELD, CHALLENGE_MAGIC
from challenge_generation import (EXCLUDED_SEEDS, PLANT_WEIGHTS, FAMILY_WEIGHTS,
                                  SEED_FAMILY, PUMPKIN_CHANCE, FAMILY_CHANCE,
                                  _tickets)


def symbol(name):
    return int(MANIFEST['symbols'][name], 16)


class ChallengeGenerationTests(unittest.TestCase):
    def field(self, mode=70, challenge=True):
        vm = VM(mode=mode)
        vm.w(CHALLENGE + CHALLENGE_FIELD, CHALLENGE_MAGIC if challenge else 0)
        return vm

    def rng(self, vm, tickets):
        remaining = iter(tickets)
        def pick(v):
            maximum = v.reg(UC_X86_REG_EAX)
            ticket = next(remaining)
            self.assertGreater(maximum, ticket)
            self.assertGreaterEqual(ticket, 0)
            # Volatile-register clobbers also exercise the saved table pointer.
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

    def allocation(self, vm, reject=False):
        vm.created = []
        vm.checked = []
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
            ptr = PLANT + len(v.created) * 0x14c
            v.created.append(args)
            v.w(ptr, APP)
            v.w(ptr + 4, BOARD)
            v.w(ptr + 0x24, args[2])
            v.w(ptr + 0x138, args[3])
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

    def test_global_tickets_include_every_allowed_plant_and_bias_upgrades(self):
        vm = self.field()
        results = []
        for ticket in range(sum(PLANT_WEIGHTS.values())):
            self.rng(vm, (ticket,))
            results.append(self.call(vm, 'iz_challenge_pick_plant'))
        self.assertEqual(Counter(results), Counter(PLANT_WEIGHTS))
        self.assertEqual(set(results) | {30}, set(range(49)) - EXCLUDED_SEEDS)
        self.assertGreater(PLANT_WEIGHTS[40], PLANT_WEIGHTS[0] + PLANT_WEIGHTS[7])
        self.assertGreater(PLANT_WEIGHTS[23], PLANT_WEIGHTS[3])
        self.assertGreater(PLANT_WEIGHTS[39] + PLANT_WEIGHTS[44],
                           PLANT_WEIGHTS[32] + PLANT_WEIGHTS[34])
        self.assertGreater(PLANT_WEIGHTS[2] + PLANT_WEIGHTS[20] + PLANT_WEIGHTS[15],
                           PLANT_WEIGHTS[4] + PLANT_WEIGHTS[17])

    def test_family_tickets_and_seventy_percent_boundary_execute(self):
        vm = self.field()
        global_ticket = _tickets(PLANT_WEIGHTS).index(37)
        for seed, family in SEED_FAMILY.items():
            weights = FAMILY_WEIGHTS[family]
            results = []
            for ticket in range(sum(weights.values())):
                self.rng(vm, (FAMILY_CHANCE - 1, ticket))
                results.append(self.call(vm, 'iz_challenge_pick_plant', seed))
            self.assertEqual(Counter(results), Counter(weights))
            self.rng(vm, (FAMILY_CHANCE, global_ticket))
            self.assertEqual(self.call(vm, 'iz_challenge_pick_plant', seed), 37)

    def test_sunflower_slot_retains_native_seed_without_selection_rng(self):
        vm = self.field()
        vm.stubs[0x5af400] = lambda v: self.fail('Sunflower selector rolled RNG')
        self.assertEqual(self.call(vm, 'iz_challenge_pick_plant', 1), 1)
        self.allocation(vm)
        self.rng(vm, (99,))  # Optional pumpkin remains independent.
        self.square(vm, seed=1)
        self.assertEqual(vm.created, [(2, 3, 1, 0xffffffff)])

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
            # The selected upgrade never goes through CanPlantAt.
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

    def test_imitater_has_every_real_allowed_target_and_never_recurses(self):
        vm = self.field()
        weights = {s: w for s, w in PLANT_WEIGHTS.items() if s != 48}
        results = []
        for ticket in range(sum(weights.values())):
            self.rng(vm, (ticket,))
            results.append(self.call(vm, 'iz_challenge_pick_imitater_target'))
        self.assertEqual(Counter(results), Counter(weights))
        vm = self.field()
        self.allocation(vm)
        self.rng(vm, (_tickets(PLANT_WEIGHTS).index(48),
                      _tickets(weights).index(44), 99))
        self.square(vm)
        self.assertEqual(vm.created, [(2, 3, 48, 44)])

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

    def batch(self, mode=70, seed=37, row=-1, count=30, blocked=()):
        vm = self.field(mode)
        self.allocation(vm)
        blocked = set(blocked)
        native_check = vm.stubs[0x40e020]
        def can_plant(v):
            sp = v.reg(UC_X86_REG_ESP)
            position = (v.r(sp + 8), v.reg(UC_X86_REG_EAX))
            self.assertEqual(v.r(sp + 12), seed)
            native_check(v)
            v.reg(UC_X86_REG_EAX, int(position in blocked))
        vm.stubs[0x40e020] = can_plant
        step = ['grid']
        def random(v):
            n = v.reg(UC_X86_REG_EAX)
            if step[0] == 'grid':
                step[0] = 'family' if seed in SEED_FAMILY else 'global'
                value = 0
            elif step[0] == 'family':
                self.assertEqual(n, 100)
                value = 0
                step[0] = 'family_ticket'
            elif step[0] == 'family_ticket':
                self.assertEqual(n, sum(FAMILY_WEIGHTS[SEED_FAMILY[seed]].values()))
                value = _tickets(FAMILY_WEIGHTS[SEED_FAMILY[seed]]).index(23)
                step[0] = 'overlay'
            elif step[0] == 'global':
                self.assertEqual(n, sum(PLANT_WEIGHTS.values()))
                value = _tickets(PLANT_WEIGHTS).index(40)
                step[0] = 'overlay'
            else:
                self.assertEqual(n, 100)
                value = 99
                step[0] = 'grid'
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
            self.assertTrue(all(p[2:] == (40, 0xffffffff) for p in vm.created))
        vm = self.batch(seed=3, count=20)
        self.assertEqual({p[:2] for p in vm.created},
                         {(c, r) for r in range(5) for c in (2, 3, 4)})
        self.assertTrue(all(p[2] == 23 for p in vm.created))
        vm = self.batch(count=7)
        self.assertEqual(len(vm.created), 7)


if __name__ == '__main__':
    unittest.main()
