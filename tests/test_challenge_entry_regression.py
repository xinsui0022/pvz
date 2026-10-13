"""Execute native button, wait, launch and filename lifecycles past hook exits.

Rendering, the OS message pump, allocation and filesystem I/O are stubbed;
the original selector callbacks, SEH frames and save formatter epilogue run.
"""
import struct
import unittest

from test_machine_code import (
    VM, PATCHED, MANIFEST, APP, BOARD, CHALLENGE, PROFILE, STACK, STOP,
    UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX,
    UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP,
    pefile,
)
from challenge_mode import CHALLENGE_MAGIC, SELECTOR_DIALOG_ID


def symbol(name):
    return int(MANIFEST['symbols'][name], 16)


class ChallengeEntryRegressionTests(unittest.TestCase):
    def vm(self, mode=70, challenge=False, binary=PATCHED):
        vm = VM(mode=mode, binary=binary)
        vm.u.mem_map(0, 0x1000)
        vm.w(0, 0x123400)
        vm.w(0x6A9EC0, APP)
        vm.w(0x6A9F38, APP)
        vm.w(APP, 0x667BA0)
        vm.w(APP + 4, 0x667D50)
        vm.w(PROFILE + 0x20, 4)
        vm.w(CHALLENGE + 0xB4, CHALLENGE_MAGIC if challenge else 0)
        vm.names = []
        vm.string_count = 0
        return vm

    def string(self, vm, address, value):
        raw = value.encode('ascii')
        vm.u.mem_write(address, b'\0' * 28)
        if len(raw) < 16:
            vm.u.mem_write(address + 4, raw + b'\0')
            capacity = 15
        else:
            buffer = APP + 0xC000 + vm.string_count * 0x100
            vm.string_count += 1
            vm.u.mem_write(buffer, raw + b'\0')
            vm.w(address + 4, buffer)
            capacity = len(raw)
        vm.w(address + 20, len(raw))
        vm.w(address + 24, capacity)

    def read_string(self, vm, address):
        start = vm.r(address + 4) if vm.r(address + 24) >= 16 else address + 4
        return bytes(vm.u.mem_read(start, vm.r(address + 20))).decode('ascii')

    def filename_dependencies(self, vm):
        def format_name(v):
            sp = v.reg(UC_X86_REG_ESP)
            self.assertEqual(v.r(sp + 4), 0x667D58)
            name = 'userdata\\game%d_%d.dat' % (v.r(sp + 8), v.r(sp + 12))
            v.names.append(name)
            output = v.reg(UC_X86_REG_ESI)
            self.string(v, output, name)
            v.ret(eax=output)

        def app_data(v):
            output = v.reg(UC_X86_REG_ESI)
            self.string(v, output, 'C:\\')
            v.ret(eax=output)

        def concat(v):
            sp = v.reg(UC_X86_REG_ESP)
            output = v.reg(UC_X86_REG_ESI)
            self.assertGreater(output, 0x1000000, 'mode was misread as an output string pointer')
            text = self.read_string(v, v.r(sp + 4)) + self.read_string(v, v.r(sp + 8))
            self.string(v, output, text)
            v.ret(eax=output)

        vm.stubs[0x5B0CA0] = format_name
        vm.stubs[0x5AF590] = app_data
        vm.stubs[0x41E340] = concat
        vm.stub(0x61C19A, 'free')

    def test_full_native_formatter_preserves_destination_frame_and_return(self):
        for mode in (0, 61, 70, 71):
            for challenge in (False, True):
                with self.subTest(mode=mode, challenge=challenge):
                    vm = self.vm(mode, challenge)
                    self.filename_dependencies(vm)
                    output = APP + 0xA000
                    vm.w(STACK + 4, output)
                    vm.w(STACK + 8, mode)
                    vm.reg(UC_X86_REG_ECX, 4)
                    registers = (UC_X86_REG_EBX, UC_X86_REG_EBP, UC_X86_REG_ESI, UC_X86_REG_EDI)
                    for index, register in enumerate(registers):
                        vm.reg(register, 0x11223300 + index)
                    before = [vm.reg(register) for register in registers]
                    vm.run(0x4568D0)
                    effective_mode = mode + (100 if challenge and 61 <= mode <= 70 else 0)
                    self.assertEqual(self.read_string(vm, output), 'C:\\userdata\\game4_%d.dat' % effective_mode)
                    self.assertEqual(vm.reg(UC_X86_REG_EAX), output)
                    self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK + 4)
                    self.assertEqual([vm.reg(register) for register in registers], before)
                    self.assertEqual(vm.r(0), 0x123400)

    def test_missing_native_push_reproduces_the_invalid_destination(self):
        pe = pefile.PE(data=PATCHED)
        start = pe.get_offset_from_rva(symbol('iz_challenge_save_name') - 0x400000)
        tail = bytes(PATCHED[start:start + 256]).index(b'\x5a\x59\x9d\x53')
        broken = bytearray(PATCHED)
        broken[start + tail + 3] = 0x90  # Reproduce the omitted prologue push.
        for challenge in (False, True):
            vm = self.vm(70, challenge, bytes(broken))
            vm.w(STACK + 4, APP + 0xA000)
            vm.w(STACK + 8, 70)
            vm.reg(UC_X86_REG_ECX, 4)
            vm.run(0x4568D0, 0x4568F2)
            self.assertEqual(vm.reg(UC_X86_REG_EBP), 70)
            self.assertNotEqual(vm.reg(UC_X86_REG_EBP), APP + 0xA000)

    def dialog_dependencies(self, vm, response):
        dialog = APP + 0x9000
        vm.w(dialog, 0x667ED0)
        vm.w(dialog + 0x8C, APP + 4)
        vm.w(dialog + 0x10, APP + 0xB000)
        vm.w(dialog + 0x13C, SELECTOR_DIALOG_ID)
        vm.w(dialog + 0x144, 0x7FFFFFFF)
        vm.w(dialog + 0x28, 1)
        vm.w(dialog + 0x154, 0xFFFFFFFF)
        pump_thunk = STOP + 0x100
        # The fake message pump delivers a click into the real native listener.
        vm.u.mem_write(pump_thunk, b'\x68' + struct.pack('<I', response) +
                       b'\xb9' + struct.pack('<I', dialog + 0x88) +
                       b'\xe8' + struct.pack('<i', 0x457300 - (pump_thunk + 15)) +
                       b'\xb8\x01\x00\x00\x00\xc2\x04\x00')
        vm.w(0x667BA0 + 0x17C, pump_thunk)

        def kill(v):
            self.assertEqual(v.reg(UC_X86_REG_ECX), APP)
            self.assertEqual(v.r(v.reg(UC_X86_REG_ESP) + 4), SELECTOR_DIALOG_ID)
            v.events.append('kill_dialog')
            v.w(dialog + 0x10, 0)
            v.ret(4)

        vm.stubs[0x451800] = kill
        return dialog

    def test_actual_native_buttons_close_the_wait_loop_for_both_choices(self):
        for response in (1000, 1001):
            vm = self.vm()
            dialog = self.dialog_dependencies(vm, response)
            vm.reg(UC_X86_REG_ECX, dialog)
            vm.w(STACK + 4, 1)
            vm.run(0x540FB0)
            self.assertEqual(vm.reg(UC_X86_REG_EAX), response)
            self.assertEqual(vm.r(dialog + 0x144), response)
            self.assertEqual(vm.events, ['kill_dialog', 'kill_dialog'])
            self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK + 8)

    def test_both_selector_choices_execute_native_launch_and_full_save_formatting(self):
        for response in (1000, 1001):
            for mode in (61, 70):
                for has_save in (False, True):
                    with self.subTest(response=response, mode=mode, has_save=has_save):
                        vm = self.vm(mode)
                        self.filename_dependencies(vm)
                        screen = APP + 0x8000
                        vm.w(screen + 0x138, APP)
                        vm.reg(UC_X86_REG_ECX, screen)
                        vm.w(STACK + 4, mode + 199)
                        vm.stub(0x4504B0, 'selector', pop=28, eax=response)
                        vm.stub(0x44FD00, 'close_screen')
                        vm.stub(0x45ABB0, 'stop_music')
                        vm.stub(0x54B1C0, 'file_exists', eax=int(has_save))
                        vm.stub(0x54B260, 'erase_new_save')
                        vm.stub(0x44F890, 'new_game')
                        vm.stub(0x44F5F0, 'make_board')
                        vm.stub(0x408DE0, 'load_game', eax=1)
                        vm.stub(0x450220, 'continue_dialog')
                        vm.run(0x42F740)
                        effective_mode = mode + (100 if response == 1001 else 0)
                        self.assertEqual(vm.names, ['userdata\\game4_%d.dat' % effective_mode] * (1 if has_save else 2))
                        self.assertEqual(vm.r(APP + 0x7F8), mode)
                        self.assertEqual(vm.r(symbol('iz_challenge_selection_loading')), 0)
                        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK + 8)
                        self.assertEqual(vm.r(0), 0x123400)
                        self.assertIn('continue_dialog' if has_save else 'new_game', vm.events)


if __name__ == '__main__':
    unittest.main()
