"""Run the ball call site and native plant selection in Unicorn."""
import unittest

from test_machine_code import (
    VM, ORIGINAL, BOARD, ZOMBIE, PLANT, STACK,
    UC_X86_REG_EAX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_ESP,
)


class BossBallTests(unittest.TestCase):
    def crush(self, mode=70, kind=21, row=2, col=3, fire=0, original=False):
        vm = VM(ORIGINAL, mode) if original else VM(mode=mode)
        vm.w(PLANT+0x24, kind)
        vm.w(PLANT+0x1c, row)
        vm.w(PLANT+0x28, col)
        vm.w(ZOMBIE+0x14c, fire)
        vm.reg(UC_X86_REG_EDI, ZOMBIE)
        # At the CALL: column, row, ignoreSpikeweed are already pushed.
        vm.w(STACK, 3)
        vm.w(STACK+4, 2)
        vm.w(STACK+8, 1)

        def iterate(v):
            cursor = v.reg(UC_X86_REG_ESI)
            first = v.r(cursor) == 0
            if first:
                v.w(cursor, PLANT)
            v.ret(eax=int(first))

        def squish(v):
            self.assertEqual(v.r(v.reg(UC_X86_REG_ESP)+4), PLANT)
            v.events.append('squish')
            v.ret(4)

        vm.stubs[0x41c950] = iterate
        vm.stubs[0x462b80] = squish
        vm.run(0x535d43, 0x535d48)
        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK+12)
        self.assertEqual(vm.reg(UC_X86_REG_EDI), ZOMBIE)
        self.assertEqual(vm.r(BOARD+0x5798), len(vm.events))
        return vm.events

    def test_original_skips_spikeweed(self):
        self.assertEqual(self.crush(original=True), [])

    def test_both_balls_modes_and_plant_types(self):
        for fire in (0, 1):
            for mode in (0, 35, 60, 61, 70, 71):
                for kind in (0, 1, 21, 46):
                    with self.subTest(fire=fire, mode=mode, kind=kind):
                        expected = kind != 46 and (kind != 21 or 61 <= mode <= 70)
                        self.assertEqual(self.crush(mode, kind, fire=fire),
                                         ['squish'] if expected else [])

    def test_only_hit_square_is_crushed(self):
        for row, col in ((1, 3), (3, 3), (2, 2), (2, 4)):
            self.assertEqual(self.crush(row=row, col=col), [])


if __name__ == '__main__':
    unittest.main()
