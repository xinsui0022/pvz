"""Execute the actual patched x86 instructions in Unicorn.

External rendering/audio/coin allocation are stubbed at verified ABI entry
points. Core predicates, targeting, damage and hook transfers execute real
game instructions. These tests are not a substitute for a full game session.
"""
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'.tools'), str(ROOT/'tools')]
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE, UcError
from unicorn.x86_const import *
from build_patch import build, asm

ORIGINAL = (ROOT/'backups/PlantsVsZombies.original.exe').read_bytes()
PATCHED, MANIFEST = build(ORIGINAL)
APP, BOARD, ZOMBIE, PLANT, CHALLENGE, BRAIN, REANIM, PROFILE = range(0x1000000, 0x1008000, 0x1000)
STACK, STOP = 0x200f000, 0x800000
REGS = [UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX,
        UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP]

class VM:
    def __init__(self, binary=PATCHED, mode=70):
        self.u = Uc(UC_ARCH_X86, UC_MODE_32)
        p = pefile.PE(data=binary)
        self.u.mem_map(0x400000, 0x401000)
        self.u.mem_write(0x400000, p.get_memory_mapped_image())
        self.u.mem_map(APP, 0x10000)
        self.u.mem_map(0x2000000, 0x10000)
        self.u.reg_write(UC_X86_REG_ESP, STACK)
        self.w(STACK, STOP)
        self.w(APP+0x768, BOARD)
        self.w(APP+0x7f8, mode)
        self.w(APP+0x82c, PROFILE)
        self.w(BOARD+0x160, CHALLENGE)
        self.w(CHALLENGE, APP); self.w(CHALLENGE+4, BOARD)
        for ptr in (ZOMBIE, PLANT, BRAIN):
            self.w(ptr, APP); self.w(ptr+4, BOARD)
        self.w(ZOMBIE+0x24, 25)
        self.w(ZOMBIE+0x6c, 0)
        self.w(PLANT+0x24, 1)
        self.w(PLANT+0x40, 300)
        self.w(PLANT+8, 100); self.w(PLANT+12, 200)
        self.u.mem_write(ZOMBIE+0xba, b'\1')
        self.stubs = {}
        self.events = []
        self.u.hook_add(UC_HOOK_CODE, self.hook)

    def w(self, addr, value):
        self.u.mem_write(addr, struct.pack('<I', value & 0xffffffff))

    def r(self, addr):
        return struct.unpack('<I', self.u.mem_read(addr,4))[0]

    def reg(self, reg, value=None):
        if value is not None: self.u.reg_write(reg,value)
        return self.u.reg_read(reg)

    def ret(self, pop=0, eax=None):
        sp=self.reg(UC_X86_REG_ESP)
        target=self.r(sp)
        self.reg(UC_X86_REG_ESP,sp+4+pop)
        if eax is not None: self.reg(UC_X86_REG_EAX,eax)
        self.reg(UC_X86_REG_EIP,target)

    def hook(self,u,addr,size,_):
        if addr in self.stubs: self.stubs[addr](self)

    def run(self, start, end=STOP):
        self.u.emu_start(start,end,count=30000)
        if self.reg(UC_X86_REG_EIP)!=end:
            raise AssertionError(f'Execution did not reach {end:x}')

    def stub(self, addr, event, pop=0, eax=None):
        def f(vm):
            vm.events.append(event)
            vm.ret(pop,eax)
        self.stubs[addr]=f

    def coin_stub(self):
        def f(vm):
            sp=vm.reg(UC_X86_REG_ESP)
            assert vm.reg(UC_X86_REG_ECX)==BOARD
            assert vm.r(sp+12)==4
            assert vm.r(sp+16)==2
            vm.events.append(('sun',vm.r(sp+4),vm.r(sp+8),vm.r(sp+16)))
            # Adversarial volatile-register clobbers, as a real callee may do.
            vm.reg(UC_X86_REG_ECX,0xaaaa)
            vm.reg(UC_X86_REG_EDX,0xbbbb)
            vm.ret(16,0xcccc)
        self.stubs[0x40cb10]=f

class PatchTests(unittest.TestCase):
    def test_original_crash_reproduced_and_corrected(self):
        old=VM(ORIGINAL)
        old.w(ZOMBIE+0x768,1) # Adjacent data mistaken for LawnApp fields.
        old.reg(UC_X86_REG_ECX,ZOMBIE)
        with self.assertRaises(UcError): old.run(0x5366d0)
        self.assertEqual(old.reg(UC_X86_REG_EIP),0x4539f1)
        vm=VM(); vm.reg(UC_X86_REG_ECX,ZOMBIE)
        vm.stub(0x532b40,'cold')
        vm.run(0x5366d0)
        self.assertEqual(vm.r(ZOMBIE+0xec),1)
        self.assertEqual(vm.reg(UC_X86_REG_ECX),ZOMBIE)
        self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK+4)

    def test_boss_cleanup_repeated_and_no_allied_death(self):
        vm=VM(); vm.w(ZOMBIE+0x140,0x10005)
        vm.u.mem_write(ZOMBIE+0xed,b'\x55\x66\x77')
        vm.reg(UC_X86_REG_ECX,ZOMBIE)
        def remove(v):
            self.assertEqual(v.reg(UC_X86_REG_EAX),APP)
            self.assertEqual(v.reg(UC_X86_REG_EDX),0x10005)
            self.assertEqual(v.r(ZOMBIE+0x140),0)
            v.events.append('remove'); v.ret()
        vm.stubs[0x453cf0]=remove
        vm.stub(0x532b40,'cold')
        vm.run(0x5366d0)
        vm.reg(UC_X86_REG_ESP,STACK); vm.run(0x5366d0)
        self.assertEqual(vm.events,['remove','cold','cold'])
        self.assertEqual(bytes(vm.u.mem_read(ZOMBIE+0xec,4)),b'\1\x55\x66\x77')

    def test_boss_predicate_matrix(self):
        for mode,board,profile,level,expected in [(70,1,0,0,0),(0,1,0,0,0),
                (0,1,1,50,1),(0,1,1,49,0),(35,1,0,0,1),(35,0,1,50,0)]:
            with self.subTest(mode=mode,board=board,profile=profile,level=level):
                vm=VM(mode=mode)
                vm.w(APP+0x768,BOARD if board else 0)
                vm.w(APP+0x82c,PROFILE if profile else 0)
                vm.w(PROFILE+0x24,level)
                vm.reg(UC_X86_REG_ECX,APP); vm.run(0x4539d0)
                self.assertEqual(vm.reg(UC_X86_REG_EAX)&255,expected)

    def test_real_boss_prologue_preserved(self):
        for mode in (0,35):
            vm=VM(mode=mode); vm.w(PROFILE+0x24,50)
            vm.reg(UC_X86_REG_ECX,ZOMBIE); vm.run(0x5366d0,0x5366d6)
            self.assertEqual(vm.reg(UC_X86_REG_ECX),ZOMBIE)
            self.assertEqual(vm.reg(UC_X86_REG_EBP),STACK-4)
            self.assertEqual(vm.reg(UC_X86_REG_ESP),(STACK-4)&~7)

    def test_jack_sun_mode_health_and_type(self):
        for mode,health,kind,dead,n in [(70,300,1,0,8),(61,40,1,0,2),
                (70,1,1,0,1),(70,0,1,0,0),(70,300,0,0,0),
                (0,300,1,0,0),(70,300,1,1,0)]:
            with self.subTest(mode=mode,health=health,kind=kind,dead=dead):
                vm=VM(mode=mode); vm.w(PLANT+0x40,health);vm.w(PLANT+0x24,kind)
                vm.u.mem_write(PLANT+0x141,bytes([dead]))
                vm.reg(UC_X86_REG_ESI,PLANT); vm.w(STACK+4,PLANT)
                vm.coin_stub(); vm.stub(0x4679b0,'plant_die',4)
                vm.run(int(MANIFEST['symbols']['jack_sun'],16))
                self.assertEqual(len(vm.events)-1,n)
                self.assertEqual(vm.events[-1],'plant_die')
                self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK+8)

    def test_basketball_damage_boundaries_and_registers(self):
        for h,d in [(300,75),(225,75),(150,75),(75,75),(40,1),(39,1),
                (1,75),(80,40),(300,1000),(0,75)]:
            for mode in (70,61,0):
                with self.subTest(health=h,damage=d,mode=mode):
                    vm=VM(mode=mode); vm.w(PLANT+0x40,h)
                    vm.reg(UC_X86_REG_ESI,PLANT); vm.reg(UC_X86_REG_ECX,d)
                    vm.reg(UC_X86_REG_EAX,17); vm.coin_stub()
                    def die(v):
                        self.assertEqual(v.r(v.reg(UC_X86_REG_ESP)+4),PLANT)
                        self.assertLessEqual(struct.unpack('<i',v.u.mem_read(PLANT+0x40,4))[0],0)
                        v.u.mem_write(PLANT+0x141,b'\1'); v.ret(4)
                    vm.stubs[0x4679b0]=die
                    before=[vm.reg(r) for r in REGS]
                    # Seed an x87 value at the actual hook's live stack depth.
                    vm.u.mem_write(STOP,asm('fld1; nop',STOP))
                    vm.run(STOP,STOP+2)
                    fp=vm.reg(UC_X86_REG_FP0); sw=vm.reg(UC_X86_REG_FPSW)
                    vm.run(0x46d7a6,0x46d7ac)
                    remaining=lambda x: x//40+1 if x>0 else 0
                    expected=remaining(h)-remaining(h-d) if mode>=61 else 0
                    self.assertEqual(len(vm.events),expected)
                    self.assertEqual(vm.r(PLANT+0x40),(h-d)&0xffffffff)
                    self.assertEqual(bytes(vm.u.mem_read(PLANT+0x141,1)),bytes([int(mode>=61 and h-d<=0)]))
                    self.assertEqual([vm.reg(r) for r in REGS],before)
                    self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK)
                    self.assertEqual(vm.reg(UC_X86_REG_FP0),fp)
                    self.assertEqual(vm.reg(UC_X86_REG_FPSW),sw)

    def test_water_gate_preserves_restrictions(self):
        for phase in (0x33,0x38,0x39,0x34,0x35,0x36,0x3a,0xc,0):
            for mode in (70,0):
                for target in (0,BRAIN):
                    with self.subTest(phase=phase,mode=mode,target=target):
                        vm=VM(mode=mode); vm.reg(UC_X86_REG_EDI,ZOMBIE)
                        vm.w(ZOMBIE+0x28,phase)
                        def get(v):
                            self.assertEqual(v.reg(UC_X86_REG_EAX),ZOMBIE)
                            self.assertEqual(v.r(v.reg(UC_X86_REG_ESP)+4),CHALLENGE)
                            v.ret(4,target)
                        vm.stubs[0x42b810]=get
                        expected=0x52f5eb if phase in (0x33,0x38,0x39) and mode==70 and target else 0x52f528
                        vm.run(0x52f522,expected)
                        self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK)
                        self.assertEqual(vm.reg(UC_X86_REG_EDI),ZOMBIE)

    def test_fireball_position_row_and_single_score(self):
        for x in (-54.99,-55,-100,float('nan')):
            for mode in (70,0):
                for state in (0,29):
                    vm=VM(mode=mode)
                    vm.reg(UC_X86_REG_EBX,ZOMBIE);vm.reg(UC_X86_REG_ESI,REANIM)
                    vm.u.mem_write(REANIM+0x2c,struct.pack('<f',x))
                    vm.w(ZOMBIE+0x140,0x10005);vm.w(ZOMBIE+0x148,3)
                    vm.w(BRAIN+0xc,state)
                    def get(v):
                        self.assertEqual(v.reg(UC_X86_REG_EDX),BOARD)
                        self.assertEqual(v.reg(UC_X86_REG_EDI),3)
                        self.assertEqual(v.reg(UC_X86_REG_EBX),0)
                        self.assertEqual(v.r(v.reg(UC_X86_REG_ESP)+4),12)
                        v.ret(4,BRAIN)
                    def squish(v):
                        self.assertEqual(v.reg(UC_X86_REG_EAX),BRAIN)
                        self.assertEqual(v.r(v.reg(UC_X86_REG_ESP)+4),CHALLENGE)
                        v.w(BRAIN+0xc,29);v.events.append('score');v.ret(4)
                    vm.stubs[0x408e40]=get;vm.stubs[0x42ba30]=squish
                    vm.run(0x535d48,0x535d4f)
                    vm.run(0x535d48,0x535d4f)
                    self.assertEqual(len(vm.events),int(x<=-55 and mode==70 and state!=29))
                    self.assertEqual(vm.reg(UC_X86_REG_EBX),ZOMBIE)
                    self.assertEqual(vm.reg(UC_X86_REG_ESI),REANIM)
                    self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK)

    def test_version_lock(self):
        with self.assertRaises(ValueError): build(ORIGINAL[:-1]+b'x')
        with self.assertRaises(ValueError): build(PATCHED)

if __name__=='__main__': unittest.main(verbosity=2)
