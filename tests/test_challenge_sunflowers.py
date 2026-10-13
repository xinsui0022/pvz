"""Execute native sunflower initialization arguments and damage payouts as x86."""
import unittest
from test_machine_code import (VM, MANIFEST, APP, BOARD, CHALLENGE, PLANT,
                               ZOMBIE, STACK, STOP, REGS)
from unicorn.x86_const import *
from challenge_mode import CHALLENGE_FIELD, CHALLENGE_MAGIC
from v4_1_fixes import GRACE_MAGIC
import test_v4_1


def symbol(name):
    return int(MANIFEST['symbols'][name], 16)


class ChallengeSunflowerTests(unittest.TestCase):
    def field(self, mode=70, challenge=True):
        vm = VM(mode=mode)
        vm.w(CHALLENGE + CHALLENGE_FIELD,
             CHALLENGE_MAGIC if challenge else 0)
        vm.w(BOARD + 0x8c, APP)
        vm.coin_stub()
        return vm

    def initialize_args(self, vm, seed=1, imitate=-1):
        vm.w(STACK + 4, PLANT)
        vm.w(STACK + 8, seed)
        vm.w(STACK + 12, imitate)
        vm.reg(UC_X86_REG_EAX, 2)
        vm.reg(UC_X86_REG_ECX, 3)

    def test_native_init_arguments_upgrade_only_challenge_and_replay_prologue(self):
        for mode, marker, upgrades in ((61, True, True), (70, True, True),
                                      (61, False, False), (70, False, False),
                                      (60, True, False), (71, True, False)):
            for seed, imitate in ((1, -1), (48, 1), (48, 41), (48, 44),
                                  (41, -1), (0, -1)):
                with self.subTest(mode=mode, marker=marker,
                                  seed=seed, imitate=imitate):
                    vm = self.field(mode, marker)
                    self.initialize_args(vm, seed, imitate)
                    before = [vm.reg(r) for r in REGS]
                    vm.run(0x45db60, 0x45db66)
                    expected = 41 if upgrades and seed == 1 else seed
                    target = 41 if upgrades and seed == 48 and imitate == 1 else imitate
                    self.assertEqual(vm.r(STACK + 8), expected)
                    self.assertEqual(vm.r(STACK + 12), target & 0xffffffff)
                    self.assertEqual(vm.r(STACK + 4), PLANT)
                    self.assertEqual(vm.reg(UC_X86_REG_ESP), (STACK - 4) & ~7)
                    self.assertEqual(vm.reg(UC_X86_REG_EBP), STACK - 4)
                    after = [vm.reg(r) for r in REGS[:-1]]
                    self.assertEqual(after, before[:-1])

    def test_invalid_scope_never_dereferences_missing_app_board_or_challenge(self):
        for field in (PLANT, PLANT + 4, BOARD + 0x160):
            vm = self.field()
            vm.w(field, 0)
            self.initialize_args(vm)
            vm.run(0x45db60, 0x45db66)
            self.assertEqual(vm.r(STACK + 8), 1)

    def test_fixed_native_sunflower_init_selects_real_twin_resource_and_300_health(self):
        for marker, seed, resource in ((True, 41, 89), (False, 1, 7)):
            vm = self.field(challenge=marker)
            self.initialize_args(vm)
            vm.stubs[0x41c740] = lambda v: v.ret(eax=230)
            vm.stubs[0x5af400] = lambda v: v.ret(eax=0)
            vm.stubs[0x626020] = lambda v: v.ret()  # Native memset ABI.
            vm.stubs[0x45e7c0] = lambda v: v.ret(eax=10000)
            vm.run(0x45db60, 0x45dd14)
            self.assertEqual(vm.r(PLANT + 0x24), seed)
            self.assertEqual(vm.r(PLANT + 0x40), 300)
            self.assertEqual(vm.r(PLANT + 0x1c), 2)
            self.assertEqual(vm.r(PLANT + 0x28), 3)
            definition = vm.reg(UC_X86_REG_ECX)
            self.assertEqual(definition, 0x69f2b0 + seed * 36)
            self.assertEqual(vm.r(definition + 8), resource)

    def damage(self, vm, amount):
        vm.reg(UC_X86_REG_ESP, STACK)
        vm.w(STACK, STOP)
        vm.reg(UC_X86_REG_ESI, PLANT)
        vm.reg(UC_X86_REG_ECX, amount)
        vm.run(symbol('projectile_damage'))
        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK + 4)

    def bite(self, vm, seed):
        vm.reg(UC_X86_REG_ESP, STACK)
        vm.reg(UC_X86_REG_ESI, PLANT)
        vm.reg(UC_X86_REG_EBP, ZOMBIE)
        vm.reg(UC_X86_REG_ECX, seed)
        vm.reg(UC_X86_REG_EBX, 1)
        vm.run(0x52fc9c, 0x52fcf4)
        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK)

    def test_complete_biting_keeps_300_health_and_totals_400_challenge_sun(self):
        for seed, marker, total in ((41, True, 16), (1, False, 8)):
            vm = self.field(challenge=marker)
            vm.w(PLANT + 0x24, seed)
            vm.w(PLANT + 0x40, 300)
            for _ in range(75):
                self.bite(vm, seed)
            self.assertEqual(vm.r(PLANT + 0x40), 0)
            self.assertEqual(len(vm.events), total)
            self.assertEqual(total * 25, 400 if marker else 200)

    def test_mixed_projectile_bites_and_explosion_pay_400_once(self):
        vm = self.field()
        vm.w(PLANT + 0x24, 41)
        vm.w(PLANT + 0x40, 300)
        self.damage(vm, 40)
        self.assertEqual(vm.r(PLANT + 0x40), 260)
        self.assertEqual(len(vm.events), 2)
        for _ in range(32):
            self.bite(vm, 41)
        self.assertEqual(vm.r(PLANT + 0x40), 132)
        self.assertEqual(len(vm.events), 8)
        def die(v):
            v.u.mem_write(PLANT + 0x141, b'\1')
            v.ret(4)
        vm.stubs[0x4679b0] = die
        for _ in range(2):
            vm.reg(UC_X86_REG_ESP, STACK)
            vm.w(STACK, STOP)
            vm.w(STACK + 4, PLANT)
            vm.reg(UC_X86_REG_ESI, PLANT)
            vm.run(symbol('jack_sun'))
            self.assertEqual(len(vm.events), 16)
            self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK + 8)

    def test_twin_income_preserves_endless_20_second_completion_grace(self):
        helper = test_v4_1.V41Tests()
        for marker, expected in ((True, 2000), (False, 0)):
            vm = helper.field(plants=(41,), zombies=())
            vm.w(CHALLENGE + CHALLENGE_FIELD,
                 CHALLENGE_MAGIC if marker else 0)
            helper.start(vm)
            self.assertEqual(vm.r(CHALLENGE + 0x94), expected)
            self.assertEqual(vm.r(CHALLENGE + 0x90) == GRACE_MAGIC, marker)
            self.assertEqual('complete' in vm.events, not marker)


if __name__ == '__main__':
    unittest.main()
