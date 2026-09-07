import struct
import unittest

from test_machine_code import (
    VM, ROOT, ORIGINAL, PATCHED, MANIFEST, APP, BOARD, ZOMBIE, PLANT,
    CHALLENGE, BRAIN, STACK, STOP, pefile, asm, UcError,
    UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDI,
    UC_X86_REG_ESI, UC_X86_REG_EBP, UC_X86_REG_ESP, UC_X86_REG_EIP,
    UC_X86_REG_FP0, UC_X86_REG_FPSW,
)
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
from progression_fixes import WEAK_TYPES
from v3_fixes import QUEUE_MAGIC, QUEUE_CAPACITY


class V3Tests(unittest.TestCase):
    def test_all_hooks_cover_whole_instructions(self):
        pe = pefile.PE(data=ORIGINAL)
        dis = Cs(CS_ARCH_X86, CS_MODE_32)
        for hook in MANIFEST['hooks']:
            va, size = int(hook['va'], 16), hook['length']
            if va in (0x65124a, 0x651213, 0x4539d0):
                # Footer data and V2 complete function replacements never
                # return to the overwritten block's successor.
                continue
            instructions = list(dis.disasm(pe.get_data(va-0x400000, size), va))
            with self.subTest(va=hex(va)):
                self.assertEqual(sum(i.size for i in instructions), size)

    def test_startup_advice_uses_real_stack_argument(self):
        old, new = pefile.PE(data=ORIGINAL), pefile.PE(data=PATCHED)
        self.assertEqual(old.get_data(0x599e0, 32), new.get_data(0x599e0, 32))
        vm = VM()
        vm.u.mem_map(0, 0x1000)  # Thread exception-handler chain.
        message = APP+0x9000
        vm.w(message, APP)
        vm.w(message+0x88, 100)
        vm.w(STACK+4, message)
        vm.reg(UC_X86_REG_ECX, 0x61fcf3)  # Actual crash-log register value.
        vm.run(0x4599e0, 0x459a1a)
        self.assertEqual(vm.reg(UC_X86_REG_EAX), message)

    def test_rejected_v3_startup_crash_reproduced(self):
        path = ROOT/'backups/PlantsVsZombies.v3-failed.exe'
        if not path.exists():
            self.skipTest('Local failed V3 executable is not distributed')
        vm = VM(path.read_bytes())
        vm.reg(UC_X86_REG_ECX, 0x61fcf3)
        with self.assertRaises(UcError):
            vm.run(0x4599e0)
        self.assertEqual(vm.reg(UC_X86_REG_EIP), 0x794b12)

    def test_vehicles_keep_body_max_and_armor_through_real_division(self):
        self.assertTrue({26, 29, 30}.issubset(WEAK_TYPES))
        for mode in (0, 60, 61, 70, 71):
            for kind in (12, 22):
                vm = VM(mode=mode)
                vm.w(ZOMBIE+0x24, kind)
                vm.reg(UC_X86_REG_EAX, ZOMBIE)
                vm.reg(UC_X86_REG_EBX, PLANT)
                vm.w(PLANT+0x2c, 0x43c80000)
                for off in (0xc8, 0xd0, 0xdc):
                    vm.w(ZOMBIE+off, 300)
                vm.stub(0x5af400, 'roll', eax=4)
                vm.run(0x651171, 0x6511cd)
                for off in (0xc8, 0xcc, 0xd0, 0xd4, 0xdc, 0xe0):
                    self.assertEqual(vm.r(ZOMBIE+off), 300 if 61 <= mode <= 70 else 60)
                self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK)

    def test_random_bungee_retains_target_through_actual_caller(self):
        for mode, kind in ((70, 20), (61, 20), (0, 20), (70, 0)):
            vm = VM(mode=mode)
            vm.w(ZOMBIE+0x24, kind)
            vm.w(ZOMBIE+0x2c, 0x43a00000)
            vm.w(ZOMBIE+0x30, 0x43480000)
            vm.w(ZOMBIE+0x80, 3)
            vm.w(ZOMBIE+0x1c, 2)
            vm.w(ZOMBIE+0xc8, 450)
            vm.w(PLANT+0x2c, 0x44160000)
            vm.reg(UC_X86_REG_EAX, ZOMBIE)
            vm.reg(UC_X86_REG_EBX, PLANT)
            vm.stub(0x5af400, 'roll', eax=0)
            vm.run(0x651139, 0x6511dc)
            keep = 61 <= mode <= 70 and kind == 20
            self.assertEqual(vm.r(ZOMBIE+0x2c), 0x43a00000 if keep else 0x44160000)
            self.assertEqual(vm.r(ZOMBIE+0x80), 3)
            self.assertEqual(vm.r(ZOMBIE+0x1c), 2)
            self.assertEqual(vm.r(ZOMBIE+0x30), 0x43480000)

    def test_ice_trail_15_seconds_and_original_final_boss_case(self):
        for mode, expected in ((0,3000),(60,3000),(61,4500),(70,4500),(71,3000),(28,0x7fffffff)):
            vm = VM(mode=mode)
            vm.reg(UC_X86_REG_ESI, ZOMBIE)
            vm.w(ZOMBIE+0x1c, 2)
            vm.run(0x52a8a9, 0x52a8d6)
            self.assertEqual(vm.r(BOARD+0x624+8), expected)
        self.assertEqual((4500-3000)*10, 15000)

    def test_squash_starts_jump_without_chewing_brain(self):
        for mode, kind, end in ((70,30,0x42b9c2),(61,30,0x42b9c2),(0,30,0x42b996),(70,0,0x42b996)):
            vm = VM(mode=mode)
            vm.w(ZOMBIE+0x24, kind)
            vm.w(BRAIN+0x18, 70)
            vm.reg(UC_X86_REG_EDI, ZOMBIE)
            vm.reg(UC_X86_REG_ESI, BRAIN)
            vm.stub(0x52f250, 'start_eating')
            vm.run(0x42b98f, end)
            self.assertEqual(vm.events, ['start_eating'])
            self.assertEqual(vm.r(BRAIN+0x18), 70)

    def test_squash_impact_passes_actual_brain_pointer_and_scores_once(self):
        vm = VM()
        vm.w(BRAIN+0xc, 0)
        def target(v):
            self.assertEqual(v.reg(UC_X86_REG_EAX), ZOMBIE)
            self.assertEqual(v.r(v.reg(UC_X86_REG_ESP)+4), CHALLENGE)
            v.ret(4, BRAIN if v.r(BRAIN+0xc) != 29 else 0)
        vm.stubs[0x42b810] = target
        vm.u.mem_write(APP+0x8c5, b'\1')  # Original SquishBrain skips sound.
        def score(v):
            self.assertEqual(v.reg(UC_X86_REG_EBX), BRAIN)
            self.assertEqual(v.reg(UC_X86_REG_ESI), CHALLENGE)
            v.w(CHALLENGE+0x60, v.r(CHALLENGE+0x60)+1)
            v.ret()
        vm.stubs[0x42b8b0] = score
        vm.stub(0x52e920, 'squish_plants', pop=12)
        for _ in range(2):
            vm.reg(UC_X86_REG_ESP, STACK)
            vm.reg(UC_X86_REG_EDI, ZOMBIE)
            vm.w(STACK, 0); vm.w(STACK+4, 2); vm.w(STACK+8, 0)
            vm.run(0x527e2e, 0x527e33)
            self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK+12)
        self.assertEqual(vm.r(BRAIN+0xc), 29)
        self.assertEqual(vm.r(CHALLENGE+0x60), 1)

    def test_squash_aim_updates_local_without_corrupting_saved_registers(self):
        for site, end in ((0x527c26,0x527c2f),(0x527db2,0x527db8)):
            vm = VM()
            vm.reg(UC_X86_REG_EBP, ZOMBIE)
            vm.w(STACK+0x1c, 40)
            vm.stub(0x42b810, 'target', pop=4, eax=BRAIN)
            vm.run(site, end)
            self.assertEqual(vm.r(STACK+0x1c), 0xffffffd8)
            self.assertEqual(vm.reg(UC_X86_REG_EBP), ZOMBIE)
            self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK)

    def test_yeti_does_not_enter_running_and_loaded_yeti_recovers(self):
        for phase in (0, 0x5b):
            vm = VM()
            vm.w(ZOMBIE+0x24, 19)
            vm.w(ZOMBIE+0x28, phase)
            vm.w(ZOMBIE+0x68, 0)
            vm.u.mem_write(ZOMBIE+0xbc, bytes([0 if phase else 1]))
            vm.reg(UC_X86_REG_EAX, ZOMBIE)
            vm.run(0x52a8e0)
            self.assertEqual(vm.r(ZOMBIE+0x28), 0)
            vm.reg(UC_X86_REG_ESP, STACK)
            vm.reg(UC_X86_REG_ECX, ZOMBIE)
            vm.run(0x52bee0)
            self.assertEqual(vm.reg(UC_X86_REG_EAX)&255, 0)
        vm = VM(mode=0)
        vm.reg(UC_X86_REG_EAX, ZOMBIE)
        vm.stub(0x524a70, 'speed')
        vm.run(0x52a8e0)
        self.assertEqual(vm.r(ZOMBIE+0x28), 0x5b)

    def test_boss_health_mode_boundaries(self):
        for mode, hp in ((0,40000),(35,60000),(60,60000),(61,500),(70,500),(71,60000)):
            vm = VM(mode=mode)
            vm.reg(UC_X86_REG_ECX, APP)
            vm.reg(UC_X86_REG_EDI, ZOMBIE)
            vm.run(0x523612, 0x523638)
            self.assertEqual(vm.r(ZOMBIE+0xc8), hp)

    def test_boss_baseline_returns_to_intact_animation_call(self):
        vm = VM()
        vm.reg(UC_X86_REG_EDI, ZOMBIE)
        vm.reg(UC_X86_REG_EAX, 4500)
        vm.w(ZOMBIE+0xc8, 500)
        vm.stub(0x528b00, 'animation', pop=16)
        vm.run(0x5353cf, 0x5353da)
        self.assertEqual(vm.r(ZOMBIE+0x154), 500)
        self.assertEqual(vm.r(ZOMBIE+0x13c), 4500)
        self.assertEqual(vm.events, ['animation'])
        self.assertEqual(vm.reg(UC_X86_REG_ESP), STACK+16)

    def test_boss_no_damage_only_at_half_second_boundary(self):
        for mode, hp, baseline, ticks, expected in (
                (70,500,500,51,500),(70,500,500,50,1),(70,500,500,49,500),
                (61,400,400,50,1),(70,499,500,50,499),(0,500,500,50,500),
                (70,1,500,50,1),(70,500,0,50,500)):
            vm = VM(mode=mode)
            vm.reg(UC_X86_REG_EDI, ZOMBIE)
            vm.w(ZOMBIE+0xc8, hp)
            vm.w(ZOMBIE+0x154, baseline)
            vm.w(ZOMBIE+0x68, ticks)
            vm.u.mem_write(STOP, asm('fld1; nop',STOP))
            vm.run(STOP, STOP+2)
            before = vm.reg(UC_X86_REG_FP0), vm.reg(UC_X86_REG_FPSW)
            vm.run(0x5365f5, 0x5365fc)
            self.assertEqual(vm.r(ZOMBIE+0xc8), expected)
            self.assertEqual((vm.reg(UC_X86_REG_FP0), vm.reg(UC_X86_REG_FPSW)), before)


class PauseTests(unittest.TestCase):
    def base(self, mode=70, paused=True):
        vm = VM(mode=mode)
        vm.w(BOARD+0x8c, APP)
        vm.u.mem_write(BOARD+0x164, bytes([paused]))
        vm.w(APP+0x7fc, 3)
        vm.w(APP+0x83c, APP+0xb000)
        vm.stub(0x5152d0, 'sound_pause', pop=4)
        vm.stub(0x45b930, 'music_pause', pop=4)
        return vm

    def test_keyboard_toggles_real_pause_without_modal_and_focus_never_resumes(self):
        vm = self.base(paused=False)
        for expected in (1,0,1):
            vm.reg(UC_X86_REG_ECX, APP)
            vm.reg(UC_X86_REG_ESP, STACK)
            vm.run(0x41b8ec, 0x41b8f1)
            self.assertEqual(vm.r(BOARD+0x164)&255, expected)
        vm.reg(UC_X86_REG_ECX, APP)
        vm.reg(UC_X86_REG_ESP, STACK)
        vm.w(STACK, STOP)
        vm.run(0x4502c0)
        self.assertEqual(vm.r(BOARD+0x164)&255, 1)
        vm = self.base(mode=0)
        vm.reg(UC_X86_REG_ECX, APP)
        vm.run(0x4502c0, 0x4502c6)
        self.assertEqual(vm.reg(UC_X86_REG_EBP), STACK-4)

    def test_card_selection_includes_real_scene_money_and_packet_checks(self):
        for mode, paused, money, scene, expected in (
                (70,True,True,3,1),(61,True,True,3,1),(0,True,True,3,0),
                (0,False,True,3,1),(70,True,False,3,0),(70,True,True,2,0)):
            vm = self.base(mode,paused)
            packet = APP+0x9000
            vm.w(packet, APP); vm.w(packet+4, BOARD)
            vm.w(packet+0x34, 61)
            vm.u.mem_write(packet+0x48, b'\1')
            vm.w(APP+0x7fc, scene)
            vm.stub(0x41dae0, 'cost', eax=75)
            vm.stub(0x41bab0, 'money', pop=4, eax=int(money))
            vm.stub(0x41be50, 'free', eax=0)
            vm.stub(0x41d7d0, 'allowed', eax=1)
            vm.reg(UC_X86_REG_ESI, packet)
            vm.run(0x488500)
            self.assertEqual(vm.reg(UC_X86_REG_EAX)&255, expected)

    def test_board_mouse_preserves_unpaused_other_modes_and_packet_pointer(self):
        for mode,paused in ((70,True),(61,True),(0,False),(0,True),(71,True)):
            vm = self.base(mode,paused)
            packet=APP+0x9000
            vm.w(packet+4,BOARD)
            vm.w(STACK+0x10,packet)
            def click(v):
                self.assertEqual(v.r(v.reg(UC_X86_REG_ESP)+4),packet)
                v.events.append('click');v.ret(4)
            vm.stubs[0x488590]=click
            allowed=not paused or 61<=mode<=70
            vm.run(0x412221,0x41223b if allowed else 0x412320)
            self.assertEqual('click' in vm.events,allowed)
            self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK)

    def enqueue(self,vm,kind,col,row):
        vm.reg(UC_X86_REG_ESP,STACK)
        vm.w(STACK,STOP);vm.w(STACK+4,kind);vm.w(STACK+8,col)
        vm.reg(UC_X86_REG_ECX,CHALLENGE)
        vm.reg(UC_X86_REG_EAX,row)
        vm.run(0x42a0f0)
        self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK+12)

    def test_queue_survives_save_copy_spawns_in_order_only_after_resume(self):
        vm=self.base()
        orders=[(2,8,4),(20,2,1),(12,5,0)]
        for order in orders:self.enqueue(vm,*order)
        self.assertEqual(vm.r(CHALLENGE+0xc),3)
        self.assertEqual(vm.events,[])
        loaded=self.base()
        loaded.u.mem_write(CHALLENGE+8,bytes(vm.u.mem_read(CHALLENGE+8,0x42)))
        loaded.reg(UC_X86_REG_EBP,BOARD)
        loaded.stub(0x438da0,'preview')
        loaded.stub(0x438780,'cursor')
        loaded.run(0x415df0,0x415e18)
        self.assertEqual(loaded.events,['preview','cursor'])
        self.assertEqual(loaded.r(CHALLENGE+0xc),3)
        spawned=[]
        def spawn(v):
            sp=v.reg(UC_X86_REG_ESP)
            self.assertEqual(v.reg(UC_X86_REG_EAX),BOARD)
            kind,row=v.r(sp+4),v.r(sp+8)
            ptr=APP+0x9000+len(spawned)*0x15c
            v.w(ptr,APP);v.w(ptr+4,BOARD);v.w(ptr+0x24,kind);v.w(ptr+0x1c,row)
            spawned.append(ptr)
            v.ret(8,ptr)
        loaded.stubs[0x40ddc0]=spawn
        loaded.u.mem_write(0x531880,asm('fld1; ret 4',0x531880))
        loaded.u.mem_write(BOARD+0x164,b'\0')
        loaded.run(0x415df0,0x415e2e)
        self.assertEqual(len(spawned),3)
        for ptr,(kind,col,row) in zip(spawned,orders):
            self.assertEqual(loaded.r(ptr+0x24),kind)
            self.assertEqual(loaded.r(ptr+0x1c),row)
            x=struct.unpack('<f',loaded.u.mem_read(ptr+0x2c,4))[0]
            self.assertEqual(x,col*80+(40 if kind==20 else 10))
        self.assertEqual(loaded.r(CHALLENGE+0xc),0)
        loaded.run(0x415df0,0x415e2e)
        self.assertEqual(len(spawned),3)

    def test_queue_capacity_guard_precedes_debit_and_preserves_adjacent_fields(self):
        vm=self.base()
        vm.w(CHALLENGE+0x4a,0x12345678)
        vm.w(CHALLENGE+0x68,0x12345678)
        for i in range(QUEUE_CAPACITY):self.enqueue(vm,2,5,i%5)
        self.assertEqual(vm.r(CHALLENGE+0x4a),0x12345678)
        self.assertEqual(vm.r(CHALLENGE+0x68),0x12345678)
        vm.reg(UC_X86_REG_EBP,CHALLENGE)
        vm.run(0x42a3bd,0x42a51a)
        self.assertEqual(vm.r(CHALLENGE+0xc),QUEUE_CAPACITY)
        vm.w(CHALLENGE+0xc,QUEUE_CAPACITY-1)
        vm.run(0x42a3bd,0x42a3c7)

    def test_real_purchase_charges_once_and_full_or_unaffordable_orders_do_not_toggle(self):
        for money, count, success in ((75,0,True),(74,0,False),(100,27,False)):
            vm=self.base()
            vm.w(0x6a9ec0,APP)
            vm.w(BOARD+0x138,APP+0x9000)
            vm.w(APP+0x9028,66)
            vm.w(BOARD+0x5560,money)
            vm.w(CHALLENGE+0x10,QUEUE_MAGIC)
            vm.w(CHALLENGE+0xc,count)
            vm.w(STACK+0x58,2)
            vm.w(STACK+0x60,4)
            vm.reg(UC_X86_REG_EBP,CHALLENGE)
            vm.reg(UC_X86_REG_ESI,BOARD)
            vm.stub(0x41b980,'count_sun',eax=0)
            vm.stub(0x40cab0,'advice')
            vm.w(APP,APP+0xa000)
            vm.w(APP+0xa0d8,0x800100)
            vm.stub(0x800100,'failure_sound',pop=4)
            vm.run(0x42a3bd,0x42a433 if success else 0x42a51a)
            self.assertEqual(vm.r(BOARD+0x5560),money-75 if success else money)
            self.assertEqual(vm.r(CHALLENGE+0xc),count+int(success))
            self.assertEqual(vm.r(CHALLENGE+0xb8),int(success))


if __name__ == '__main__':
    unittest.main()
