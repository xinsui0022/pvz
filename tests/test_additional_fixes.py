import struct
import unittest
from test_machine_code import *
del PatchTests  # Avoid rediscovering the imported test case.

def symbol(name): return int(MANIFEST['symbols'][name],16)

class AdditionalTests(unittest.TestCase):
    def test_pea_gatling_mixed_damage_conserves_sun_and_dies_at_zero(self):
        for hits in ([75]*4,[20]*15,[20,75,20,75,20,20,20,20,30]):
            vm=VM();vm.coin_stub()
            def die(v):
                self.assertEqual(v.r(v.reg(UC_X86_REG_ESP)+4),PLANT)
                v.u.mem_write(PLANT+0x141,b'\1');v.ret(4)
            vm.stubs[0x4679b0]=die
            for damage in hits:
                if damage==75:
                    vm.reg(UC_X86_REG_ESI,PLANT);vm.reg(UC_X86_REG_ECX,damage)
                    start,end=0x46d7a6,0x46d7ac
                else:
                    vm.reg(UC_X86_REG_EAX,PLANT);vm.reg(UC_X86_REG_EDX,damage)
                    start,end=0x46cfeb,0x46cff1
                before=[vm.reg(r) for r in REGS]
                vm.run(start,end)
                self.assertEqual([vm.reg(r) for r in REGS],before)
                self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK)
            self.assertEqual(vm.r(PLANT+0x40),0)
            self.assertEqual(len(vm.events),8)
            self.assertEqual(bytes(vm.u.mem_read(PLANT+0x141,1)),b'\1')

    def test_jalapeno_sun_stack_and_remaining_health(self):
        vm=VM();vm.w(PLANT+0x40,150);vm.coin_stub()
        vm.reg(UC_X86_REG_EAX,PLANT);vm.reg(UC_X86_REG_ESI,0x1234)
        vm.w(STACK+4,PLANT)
        vm.stub(0x4679b0,'die',4)
        vm.run(symbol('jalapeno_sun'))
        self.assertEqual(len(vm.events),5) # four remaining suns, then Die.
        self.assertEqual(vm.events[-1],'die')
        self.assertEqual(vm.reg(UC_X86_REG_ESI),0x1234)
        self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK+8)

    def test_jalapeno_brain_only_same_row_and_once(self):
        for mode,mind in ((70,0),(70,1),(0,0)):
            vm=VM(mode=mode); vm.w(ZOMBIE+0x1c,4)
            vm.u.mem_write(ZOMBIE+0xb8,bytes([mind]))
            vm.reg(UC_X86_REG_EDI,ZOMBIE);vm.reg(UC_X86_REG_ECX,ZOMBIE)
            def get(v):
                self.assertEqual(v.reg(UC_X86_REG_EDI),4)
                self.assertEqual(v.reg(UC_X86_REG_EDX),BOARD)
                v.ret(4,BRAIN)
            def squish(v):
                v.events.append('brain');v.w(BRAIN+0xc,29);v.ret(4)
            vm.stubs[0x408e40]=get;vm.stubs[0x42ba30]=squish
            vm.stub(0x530510,'zombie_die')
            vm.run(symbol('jalapeno_brain'))
            vm.reg(UC_X86_REG_ESP,STACK);vm.run(symbol('jalapeno_brain'))
            self.assertEqual(vm.events.count('brain'),int(mode==70 and not mind))
            self.assertEqual(vm.events.count('zombie_die'),2)

    def test_pogo_breaks_only_at_live_brain(self):
        for mode,target in ((70,BRAIN),(70,0),(0,BRAIN)):
            vm=VM(mode=mode);vm.reg(UC_X86_REG_EDI,ZOMBIE)
            vm.reg(UC_X86_REG_EAX,0x14)
            vm.stub(0x42b810,'target',4,target)
            def pogo(v):
                sp=v.reg(UC_X86_REG_ESP)
                self.assertEqual([v.r(sp+4),v.r(sp+8)],[ZOMBIE,0])
                v.w(ZOMBIE+0x28,0);v.w(ZOMBIE+0x64,7)
                v.events.append('break');v.ret(8)
            vm.stubs[0x525350]=pogo
            breaks=mode==70 and target!=0
            vm.run(0x5254e2,0x525722 if breaks else 0x5254ef)
            self.assertEqual('break' in vm.events,breaks)
            self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK)

    def test_aquatic_conversion_animation_and_idempotence(self):
        for kind,phase,expected,anim in [(14,0x33,0x35,0x66ed94),
                (14,0x38,0x37,0x66edb4),(11,0x39,0x3b,0x66edb4),
                (14,0x36,0x36,None),(11,0x3d,0x3d,None)]:
            for mode in (70,0):
                vm=VM(mode=mode);vm.reg(UC_X86_REG_EAX,ZOMBIE)
                vm.w(ZOMBIE+0x24,kind);vm.w(ZOMBIE+0x28,phase)
                vm.stub(0x42b810,'target',4,0)
                def play(v):
                    self.assertEqual(v.reg(UC_X86_REG_EDI),ZOMBIE)
                    sp=v.reg(UC_X86_REG_ESP)
                    self.assertEqual(v.r(sp+4),anim)
                    self.assertEqual([v.r(sp+8),v.r(sp+12),v.r(sp+16)],[1,0,0x41400000])
                    v.events.append('play');v.ret(16)
                vm.stubs[0x528b00]=play
                for i in range(2):
                    vm.reg(UC_X86_REG_ESP,STACK);vm.run(symbol('aquatic_mode'))
                self.assertEqual(vm.r(ZOMBIE+0x28),expected if mode==70 else phase)
                self.assertEqual(vm.events.count('play'),int(mode==70 and anim is not None))
                self.assertEqual(vm.reg(UC_X86_REG_EAX),ZOMBIE)

    def test_dolphin_dismounts_for_brain(self):
        vm=VM();vm.w(ZOMBIE+0x24,14);vm.w(ZOMBIE+0x28,0x35)
        vm.reg(UC_X86_REG_EAX,ZOMBIE);vm.stub(0x42b810,'target',4,BRAIN)
        vm.stub(0x528b00,'swim',16)
        vm.run(symbol('aquatic_mode'))
        self.assertEqual(vm.r(ZOMBIE+0x28),0x37)
        self.assertEqual(vm.r(ZOMBIE+0x9c),30)
        self.assertEqual(vm.r(ZOMBIE+0xa4),30)
        self.assertEqual(vm.events,['target','swim'])

    def test_virtual_pool_edges(self):
        for name,site,end,original in [
                ('snorkel',0x52695d,0x5269c6,0x526963),
                ('dolphin_swim',0x5266b9,0x52670f,0x5266bf),
                ('dolphin_ride',0x5263e4,0x52642f,0x5263ea)]:
            for mode in (70,0):
                vm=VM(mode=mode);vm.reg(UC_X86_REG_EDI,ZOMBIE)
                vm.w(ZOMBIE+8,0)
                vm.run(site,end if mode==70 else original)
                self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK)

    def test_exact_weight_distribution(self):
        for mode,limit in ((70,35),(0,33)):
            results=[]
            for ticket in range(limit):
                vm=VM(mode=mode);vm.reg(UC_X86_REG_EBX,ZOMBIE)
                def rand(v):
                    self.assertEqual(v.reg(UC_X86_REG_EAX),limit)
                    v.ret(eax=ticket)
                vm.stubs[0x5af400]=rand
                vm.run(symbol('weighted_random'))
                results.append(vm.reg(UC_X86_REG_EAX))
            self.assertEqual(results.count(25),3 if mode==70 else 1)
            self.assertEqual(set(results),set(range(33)))

if __name__=='__main__': unittest.main()
