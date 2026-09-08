from test_machine_code import VM, ORIGINAL, PATCHED, MANIFEST, APP, BOARD, ZOMBIE, PLANT, CHALLENGE, REANIM, STACK, STOP, REGS
from test_machine_code import UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP
import unittest
import struct
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
from progression_fixes import WEAK_TYPES

class ProgressionTests(unittest.TestCase):
    def test_hooks_cover_whole_instructions(self):
        pe=pefile.PE(data=ORIGINAL)
        dis=Cs(CS_ARCH_X86,CS_MODE_32)
        sites={0x651180,0x429980,0x4167a8,0x4167d1,0x4167f4,0x416815,
               0x416867,0x41711a,0x41713c,0x417150,0x4676ea,0x467b00,0x42a42a}
        for hook in MANIFEST['hooks']:
            va=int(hook['va'],16);size=hook['length']
            if va not in sites: continue  # New trampolines that replay overwritten code.
            instructions=list(dis.disasm(pe.get_data(va-0x400000,size),va))
            self.assertEqual(sum(i.size for i in instructions),size,hex(va))

    def reward_vm(self, stage, plants, mode=70, score=5):
        vm=VM(mode=mode)
        vm.w(CHALLENGE+0x60, score)
        vm.w(CHALLENGE+0x6c, stage-1)
        vm.w(BOARD+0xac, PLANT)
        vm.w(BOARD+0xb0, len(plants))
        for i, kind in enumerate(plants):
            ptr=PLANT+i*0x14c
            vm.w(ptr+0x24,kind)
            vm.w(ptr+0x148,0x10000+i)
            vm.u.mem_write(ptr+0x144,b'\1')
        return vm

    def complete(self,vm):
        balance=vm.r(BOARD+0x5560)
        vm.coin_stub()
        event_start=len(vm.events)
        vm.reg(UC_X86_REG_ESP,STACK)
        for i, reg in enumerate(REGS): vm.reg(reg,0x123400+i)
        vm.reg(UC_X86_REG_ECX,CHALLENGE)
        before={reg:vm.reg(reg) for reg in REGS}
        vm.run(0x429980,0x429986)
        self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK-16)
        self.assertEqual(vm.reg(UC_X86_REG_EDI),before[UC_X86_REG_EAX])
        for reg in REGS:
            if reg!=UC_X86_REG_EDI: self.assertEqual(vm.reg(reg),before[reg])
        self.assertEqual(vm.r(BOARD+0x5560),balance)
        return sum(1 for event in vm.events[event_start:] if event[0] == 'sun')

    def test_rewards_stage_boundaries_stacking_and_reentry(self):
        for stage, milestone in [(1,0),(2,0),(3,100),(9,100),(10,500),(29,0),(30,600),(60,600)]:
            for plants,clear in [([21],75),([21,46],75),([],75),([21,1],0),([13],0),([27],0)]:
                with self.subTest(stage=stage,plants=plants):
                    vm=self.reward_vm(stage,plants)
                    coins=self.complete(vm)
                    self.assertEqual(coins*25,milestone+clear)
                    self.assertEqual(self.complete(vm),0)
                    # A serialized ledger copy into a fresh VM also prevents payment.
                    loaded=self.reward_vm(stage,plants)
                    loaded.w(CHALLENGE+0x70,vm.r(CHALLENGE+0x70))
                    self.assertEqual(self.complete(loaded),0)

    def test_reward_mode_score_dead_and_next_stage(self):
        for mode,score in [(0,5),(60,5),(70,4)]:
            vm=self.reward_vm(30,[21],mode,score);self.assertEqual(self.complete(vm),0)
        vm=self.reward_vm(2,[1]);vm.u.mem_write(PLANT+0x141,b'\1')
        self.assertEqual(self.complete(vm),3)
        vm.w(CHALLENGE+0x6c,2);self.assertEqual(self.complete(vm),7)

    def test_original_transition_restored_and_stage_incremented(self):
        old,new=pefile.PE(data=ORIGINAL),pefile.PE(data=PATCHED)
        self.assertEqual(old.get_data(0x29ff9,30),new.get_data(0x29ff9,30))
        vm=VM();vm.reg(UC_X86_REG_EDI,CHALLENGE);vm.w(CHALLENGE+0x6c,29)
        vm.stub(0x40ca50,'clear_advice')
        vm.run(0x429ff9,0x42a005)
        self.assertEqual(vm.r(CHALLENGE+0x6c),30)
        self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK)

    def test_actual_health_path_exact_distribution_new_zombie_not_old_cone(self):
        for kind in WEAK_TYPES:
            vm=VM();vm.w(ZOMBIE+0x24,kind);vm.w(PLANT+0x24,2)
            counts=[0]*5
            for roll in range(100):
                vm.reg(UC_X86_REG_ESP,STACK)
                vm.reg(UC_X86_REG_EAX,ZOMBIE);vm.reg(UC_X86_REG_EBX,PLANT)
                for off in (0xc8,0xd0,0xdc): vm.w(ZOMBIE+off,300)
                def rng(v,roll=roll):
                    self.assertEqual(v.reg(UC_X86_REG_EAX),100)
                    v.reg(UC_X86_REG_ECX,0xaaaa);v.reg(UC_X86_REG_EDX,0xbbbb)
                    v.ret(eax=roll)
                vm.stubs[0x5af400]=rng
                vm.run(0x651177,0x6511cd)
                value=vm.r(ZOMBIE+0xc8)
                counts[[300,150,100,75,60].index(value)]+=1
                self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK)
                self.assertEqual(vm.reg(UC_X86_REG_EBX),PLANT)
            self.assertEqual(counts,[65,25,4,3,3])
        for mode,kind in [(0,0),(70,4),(70,23),(70,7)]:
            vm=VM(mode=mode);vm.w(ZOMBIE+0x24,kind)
            vm.w(STACK+4,ZOMBIE)
            def rng(v):
                self.assertEqual(v.reg(UC_X86_REG_EAX),5);v.ret(eax=4)
            vm.stubs[0x5af400]=rng
            vm.run(int(MANIFEST['symbols']['weak_health_roll'],16))
            self.assertEqual(vm.reg(UC_X86_REG_EAX),4)

class MultiBossTests(unittest.TestCase):
    def test_actual_render_list_parts_resolve_separate_bosses(self):
        vm=VM();items=APP+0x9000;counter=APP+0xa000
        vm.w(BOARD+0x90,ZOMBIE);vm.w(BOARD+0x94,2)
        vm.w(BOARD+0x8c,APP);vm.w(APP+0x820,REANIM);vm.w(REANIM+8,REANIM)
        vm.w(REANIM,REANIM);vm.w(REANIM+0x9c,0x10000)
        for slot in range(2):
            ptr=ZOMBIE+slot*0x15c
            vm.w(ptr,APP);vm.w(ptr+4,BOARD);vm.w(ptr+0x24,25)
            vm.w(ptr+0x158,0x10000+slot)
            vm.w(ptr+0x140,0x10000)
            vm.reg(UC_X86_REG_ESP,STACK);vm.w(STACK,STOP)
            vm.w(STACK+4,BOARD);vm.w(STACK+8,counter);vm.w(STACK+12,ptr)
            vm.reg(UC_X86_REG_EAX,items)
            vm.run(0x4166c0)
            self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK+16)
        self.assertEqual(vm.r(counter),10)
        for i in range(10):
            field=items+i*12+8;slot=i//5
            self.assertEqual(vm.r(field),((slot+1)<<3)|(i%5))
            vm.reg(UC_X86_REG_EBX,field);vm.reg(UC_X86_REG_EBP,APP+0xb000)
            vm.w(APP+0xb008,BOARD)
            vm.run(0x41711a,0x417124)
            self.assertEqual(vm.reg(UC_X86_REG_EDI),ZOMBIE+slot*0x15c)

    def test_distinct_draw_restores_chill_and_graphics(self):
        vm=VM();graphics=APP+0x9000
        vm.w(BOARD+0x90,ZOMBIE)
        for slot in range(2):
            ptr=ZOMBIE+slot*0x15c
            vm.w(ptr,APP);vm.w(ptr+4,BOARD);vm.w(ptr+0x24,25)
            vm.w(ptr+0x158,0x10000+slot);vm.w(ptr+0xac,0)
        for slot in range(2):
            for part in range(5):
                ptr=ZOMBIE+slot*0x15c
                vm.reg(UC_X86_REG_ESP,STACK);vm.w(STACK,STOP);vm.w(STACK+4,part)
                vm.reg(UC_X86_REG_EDI,ptr);vm.reg(UC_X86_REG_EBX,graphics)
                vm.u.mem_write(graphics+8,struct.pack('<f',123.0))
                def draw(v):
                    self.assertEqual(v.r(v.reg(UC_X86_REG_ESP)+4),part)
                    self.assertEqual(v.r(ptr+0xac),slot)
                    x=struct.unpack('<f',v.u.mem_read(graphics+8,4))[0]
                    self.assertEqual(x,123.0-(80 if slot and part!=4 else 0))
                    v.ret(4)
                vm.stubs[0x536940]=draw
                vm.run(int(MANIFEST['symbols']['boss_distinct_draw'],16))
                self.assertEqual(vm.r(ptr+0xac),0)
                self.assertEqual(vm.u.mem_read(graphics+8,4),struct.pack('<f',123.0))
                self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK+8)

if __name__=='__main__': unittest.main()
