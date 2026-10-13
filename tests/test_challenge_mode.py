"""Execute selector, initialization and save isolation hooks at native ABIs."""
import unittest

from test_machine_code import (
    VM, MANIFEST, APP, BOARD, CHALLENGE, PROFILE, STACK, STOP, REGS,
    UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX,
    UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP,
)
from challenge_mode import (
    CHALLENGE_FIELD, CHALLENGE_MAGIC, CHALLENGE_STARTING_SUN,
    SELECTOR_DIALOG_ID, PROFILE_DELETE_SAVE_NAME_RETURN,
)


def symbol(name):
    return int(MANIFEST['symbols'][name], 16)


class ChallengeModeTests(unittest.TestCase):
    def vm(self, mode=70, challenge=False):
        vm = VM(mode=mode)
        vm.w(0x6A9EC0, APP)
        vm.w(0x6A9F38, APP)
        vm.w(BOARD + 0x8C, APP)
        vm.w(CHALLENGE + CHALLENGE_FIELD, CHALLENGE_MAGIC if challenge else 0)
        return vm

    def predicate(self, vm, board=BOARD):
        vm.reg(UC_X86_REG_ESP, STACK)
        vm.w(STACK, STOP)
        vm.reg(UC_X86_REG_EAX, board)
        vm.reg(UC_X86_REG_ECX, 0xAABBCCDD)
        vm.reg(UC_X86_REG_EDX, 0x11223344)
        vm.run(symbol('iz_challenge_mode_predicate'))
        self.assertEqual(vm.reg(UC_X86_REG_ECX), 0xAABBCCDD)
        self.assertEqual(vm.reg(UC_X86_REG_EDX), 0x11223344)
        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK + 4)
        return vm.reg(UC_X86_REG_EAX)

    def test_predicate_requires_iz_mode_and_exact_serialized_marker(self):
        for mode in (0, 60, 61, 69, 70, 71):
            for marker in (0, CHALLENGE_MAGIC ^ 1, CHALLENGE_MAGIC):
                vm = self.vm(mode)
                vm.w(CHALLENGE + CHALLENGE_FIELD, marker)
                self.assertEqual(self.predicate(vm),
                                 int(61 <= mode <= 70 and marker == CHALLENGE_MAGIC))
        for target in (0, BOARD + 0x8C, BOARD + 0x160):
            vm = self.vm(challenge=True)
            if target:
                vm.w(target, 0)
            self.assertEqual(self.predicate(vm, 0 if target == 0 else BOARD), 0)

    def test_native_selector_labels_scope_and_register_stack_abi(self):
        screen = APP + 0x9000
        for mode in (60, 61, 70, 71):
            for response in (1000, 1001):
                vm = self.vm()
                vm.w(screen + 0x138, APP)
                vm.reg(UC_X86_REG_EDI, screen)
                vm.reg(UC_X86_REG_EBX, mode - 1)
                vm.w(symbol('iz_challenge_selection_pending'), CHALLENGE_MAGIC)
                before = [vm.reg(r) for r in REGS]

                def dialog(v):
                    sp = v.reg(UC_X86_REG_ESP)
                    self.assertEqual(v.r(sp + 4), APP)
                    self.assertEqual(v.r(sp + 8), SELECTOR_DIALOG_ID)
                    self.assertEqual(v.r(sp + 28), 1)
                    for off, expected in ((20, '传统模式'), (24, '挑战模式')):
                        text = expected.encode('gbk') + b'\0'
                        self.assertEqual(bytes(v.u.mem_read(v.r(sp + off), len(text))), text)
                    v.events.append('mode_dialog')
                    # The dialog and its update loop can clobber volatile regs.
                    v.reg(UC_X86_REG_ECX, 0xABCDEF01)
                    v.reg(UC_X86_REG_EDX, 0xDEADBEEF)
                    v.ret(28, response)

                vm.stubs[0x4504B0] = dialog
                vm.run(0x42F7A0, 0x42F7A6)
                expected = CHALLENGE_MAGIC if 61 <= mode <= 70 and response == 1001 else 0
                self.assertEqual(vm.r(symbol('iz_challenge_selection_pending')), expected)
                self.assertEqual(vm.events, ['mode_dialog'] if 61 <= mode <= 70 else [])
                after = [vm.reg(r) for r in REGS]
                before[REGS.index(UC_X86_REG_ESI)] = APP  # Replayed original load.
                self.assertEqual(after, before)
                self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK)

    def test_closed_selector_does_not_kill_screen_or_change_pending_choice(self):
        vm = self.vm()
        vm.reg(UC_X86_REG_EDI, APP + 0x9000)
        vm.w(APP + 0x9138, APP)
        vm.reg(UC_X86_REG_EBX, 69)
        vm.w(symbol('iz_challenge_selection_pending'), CHALLENGE_MAGIC)
        vm.stub(0x4504B0, 'closed_dialog', pop=28, eax=0x7FFFFFFF)
        before = [vm.reg(r) for r in REGS]
        vm.run(0x42F7A0, 0x42F7D9)
        self.assertEqual(vm.r(symbol('iz_challenge_selection_pending')), CHALLENGE_MAGIC)
        self.assertEqual([vm.reg(r) for r in REGS], before)
        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK)

    def test_launch_scope_overrides_previous_board_and_cleans_original_arguments(self):
        for look_for_saved in (0, 1):
            vm = self.vm(challenge=False)
            vm.w(symbol('iz_challenge_selection_pending'), CHALLENGE_MAGIC)
            vm.reg(UC_X86_REG_ESI, APP)
            vm.w(STACK + 4, 70)
            vm.w(STACK + 8, look_for_saved)

            def launch(v):
                sp = v.reg(UC_X86_REG_ESP)
                self.assertEqual(v.r(sp + 4), 70)
                self.assertEqual(v.r(sp + 8), look_for_saved)
                self.assertEqual(v.reg(UC_X86_REG_ESI), APP)
                self.assertEqual(v.r(symbol('iz_challenge_selection_loading')), 1)
                v.events.append('pre_new_game')
                v.ret(8, 0x13572468)

            vm.stubs[0x44F560] = launch
            vm.run(symbol('iz_challenge_launch_selected'))
            self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK + 12)
            self.assertEqual(vm.reg(UC_X86_REG_EAX), 0x13572468)
            self.assertEqual(vm.r(symbol('iz_challenge_selection_loading')), 0)

    def test_actual_constructor_initializes_marker_only_for_selected_iz_mode(self):
        for mode in (60, 61, 70, 71):
            for selected in (False, True):
                vm = self.vm(mode, challenge=True)
                vm.w(symbol('iz_challenge_selection_pending'), CHALLENGE_MAGIC if selected else 0)
                vm.w(CHALLENGE + 0xB8, 1)
                vm.reg(UC_X86_REG_EDI, CHALLENGE)
                vm.run(0x41F1B0, 0x41F23D)
                expected = CHALLENGE_MAGIC if selected and 61 <= mode <= 70 else 0
                self.assertEqual(vm.r(CHALLENGE + CHALLENGE_FIELD), expected)
                self.assertEqual(vm.r(CHALLENGE + 0xB8), 0)

    def test_initial_sun_hook_preserves_registers_and_traditional_balance(self):
        for challenge in (False, True):
            vm = self.vm(challenge=challenge)
            vm.reg(UC_X86_REG_EBP, BOARD)
            before = [vm.reg(r) for r in REGS]
            vm.run(0x40B069, 0x40B073)
            self.assertEqual(vm.r(BOARD + 0x5560), CHALLENGE_STARTING_SUN if challenge else 150)
            self.assertEqual([vm.reg(r) for r in REGS], before)
            self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK)

    def save_mode(self, vm, mode):
        vm.reg(UC_X86_REG_ESP, STACK)
        vm.w(STACK + 0x4C, mode)
        vm.reg(UC_X86_REG_ECX, 4)
        vm.reg(UC_X86_REG_EDX, 0x12345678)
        vm.run(0x4568E8, 0x4568ED)
        self.assertEqual(vm.reg(UC_X86_REG_ECX), 4)
        self.assertEqual(vm.reg(UC_X86_REG_EDX), 0x12345678)
        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK)
        return vm.reg(UC_X86_REG_EAX)

    def test_save_names_follow_live_marker_or_loading_selection_without_changing_game_mode(self):
        for mode in (0, 60, 61, 70, 71):
            for live_challenge in (False, True):
                for loading in (False, True):
                    for pending in (False, True):
                        vm = self.vm(mode, challenge=live_challenge)
                        vm.w(symbol('iz_challenge_selection_loading'), int(loading))
                        vm.w(symbol('iz_challenge_selection_pending'), CHALLENGE_MAGIC if pending else 0)
                        active = pending if loading else live_challenge
                        expected = mode + (100 if active and 61 <= mode <= 70 else 0)
                        self.assertEqual(self.save_mode(vm, mode), expected)
                        self.assertEqual(vm.r(APP + 0x7F8), mode)
        vm = self.vm(challenge=True)
        self.assertEqual(self.save_mode(vm, 61), 61)  # unrelated mode query
        vm.w(APP + 0x768, 0)
        vm.w(symbol('iz_challenge_selection_pending'), CHALLENGE_MAGIC)
        self.assertEqual(self.save_mode(vm, 70), 170)

    def test_loaded_marker_retains_challenge_across_stages_independently_of_pending(self):
        source = self.vm(challenge=True)
        source.w(CHALLENGE + 0xB8, 1)  # Existing bungee purchase parity.
        loaded = self.vm()
        loaded.u.mem_write(CHALLENGE, bytes(source.u.mem_read(CHALLENGE, 0xBC)))
        loaded.w(CHALLENGE + 0x6C, 27)
        loaded.w(BOARD + 0x5560, 125)
        self.assertEqual(self.predicate(loaded), 1)
        self.assertEqual(self.save_mode(loaded, 70), 170)
        self.assertEqual(loaded.r(CHALLENGE + 0xB8), 1)
        self.assertEqual(loaded.r(BOARD + 0x5560), 125)

    def test_native_profile_delete_caller_keeps_its_original_save_filename(self):
        # Execute the real DeleteUserFiles caller and formatter SEH prologue.
        # A different profile's native saves must not follow the active ruleset.
        vm = self.vm(challenge=True)
        vm.u.mem_map(0, 0x1000)
        vm.w(symbol('iz_challenge_selection_pending'), CHALLENGE_MAGIC)
        vm.w(PROFILE + 0x20, 7)
        vm.reg(UC_X86_REG_EBP, PROFILE)
        vm.reg(UC_X86_REG_ESI, 70)
        vm.run(0x4698D0, 0x4568ED)
        self.assertEqual(vm.reg(UC_X86_REG_EAX), 70)
        self.assertEqual(vm.reg(UC_X86_REG_ECX), 7)
        self.assertEqual(vm.r(vm.reg(UC_X86_REG_ESP) + 0x44),
                         PROFILE_DELETE_SAVE_NAME_RETURN)


if __name__ == '__main__':
    unittest.main()
