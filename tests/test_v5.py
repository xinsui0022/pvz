"""V5 actual x86: rescue, single-boss credit, music ABI and waiting advice."""
from test_machine_code import *
del PatchTests
from v5_fixes import V5_MAGIC
from v4_3_fixes import RESCUE_MAGIC, ICE_MAGIC
from v4_1_fixes import GRACE_MAGIC
import test_v4_1

MUSIC=APP+0x9000
MESSAGE=APP+0xa000


def symbol(name):return int(MANIFEST['symbols'][name],16)


class V5Tests(unittest.TestCase):
    def field(self,kinds=(25,),mode=70):
        vm=VM(mode=mode)
        vm.w(BOARD+0x90,ZOMBIE);vm.w(BOARD+0x94,len(kinds))
        vm.w(BOARD+0x98,len(kinds));vm.w(BOARD+0xa0,len(kinds))
        vm.w(BOARD+0x5560,100)
        for i,kind in enumerate(kinds):
            p=ZOMBIE+i*0x15c
            vm.w(p,APP);vm.w(p+4,BOARD);vm.w(p+0x24,kind)
            vm.w(p+0x158,0x10000+i);vm.w(p+0xc8,500)
            vm.w(p+0x28,0)
        vm.reg(UC_X86_REG_EBP,CHALLENGE)
        return vm

    def call(self,vm,name):
        vm.reg(UC_X86_REG_ESP,STACK);vm.w(STACK,STOP)
        vm.reg(UC_X86_REG_EBP,CHALLENGE)
        vm.run(symbol(name))
        self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK+4)

    def music(self,vm,tune):
        vm.w(APP+0x83c,MUSIC);vm.w(MUSIC,APP);vm.w(MUSIC+8,tune)
        def stop(v):
            self.assertEqual(v.reg(UC_X86_REG_ESI),MUSIC)
            v.w(MUSIC+8,-1);v.events.append('stop');v.ret()
        def play(v):
            self.assertEqual(v.reg(UC_X86_REG_ESI),MUSIC)
            self.assertEqual(v.reg(UC_X86_REG_EAX),0xffffffff)
            self.assertEqual(v.reg(UC_X86_REG_EDX),0xffffffff)
            tune=v.reg(UC_X86_REG_ECX)
            v.w(MUSIC+8,tune);v.events.append(('play',tune));v.ret()
        vm.stubs[0x45abb0]=stop;vm.stubs[0x45adb0]=play
        # MakeSureMusicIsPlaying itself executes the real native ABI.

    def advice(self,vm):
        vm.w(BOARD+0x140,MESSAGE)
        def label(v):
            self.assertEqual(v.reg(UC_X86_REG_ESI),MESSAGE)
            self.assertEqual(v.reg(UC_X86_REG_ECX),7)
            string=v.reg(UC_X86_REG_EDX)
            size=v.r(string+0x14)
            src=v.r(string+4)
            text=bytes(v.u.mem_read(src,size))
            v.u.mem_write(MESSAGE+4,text+b'\0')
            v.w(MESSAGE+0x88,500)
            v.events.append(text.decode('gbk'));v.ret()
        vm.stubs[0x459010]=label

    def roll(self,vm,ticket,replacement=0):
        def rng(v):
            n=v.reg(UC_X86_REG_EAX)
            v.ret(eax=replacement if n==32 else ticket)
        vm.stubs[0x5af400]=rng
        vm.reg(UC_X86_REG_EBX,PLANT) # Conversion source points to this board.
        self.call(vm,'v5_single_boss_random')
        return vm.reg(UC_X86_REG_EAX)

    def test_rescue_live_zombie_blocks_then_empty_triggers_once_before_failure(self):
        for kind in (0,8,12,25):
            vm=self.field((kind,));vm.w(BOARD+0x5560,25)
            self.call(vm,'sun_rescue_once')
            self.assertEqual(vm.r(BOARD+0x5560),25)
            self.assertEqual(vm.r(CHALLENGE+0xa4),0)
            vm.u.mem_write(ZOMBIE+0xec,b'\1')
            self.call(vm,'sun_rescue_once')
            self.assertEqual(vm.r(BOARD+0x5560),5025)
            self.assertEqual(vm.r(CHALLENGE+0xa4),RESCUE_MAGIC)
            vm.w(BOARD+0x5560,0)
            self.call(vm,'sun_rescue_once')
            self.assertEqual(vm.r(BOARD+0x5560),0)
        # Run native IZombieUpdate through the actual failure decision.
        vm=self.field(())
        vm.w(BOARD+0x5560,0);vm.w(BOARD+0x5600,-1)
        vm.w(BOARD+0x8c,APP);vm.w(APP+0x820,REANIM)
        vm.w(REANIM,REANIM+0x200)
        vm.stub(0x413400,'failure',8)
        vm.w(STACK+4,CHALLENGE)
        vm.run(0x42b340)
        self.assertEqual(vm.r(BOARD+0x5560),5000)
        self.assertNotIn('failure',vm.events)

    def test_corpse_phases_do_not_spend_rescue_until_no_live_zombies_remain(self):
        for phase in (1,2,3):
            vm=self.field((0,25));vm.w(BOARD+0x5560,0)
            vm.w(ZOMBIE+0x28,phase)
            self.call(vm,'sun_rescue_once')
            self.assertEqual(vm.r(BOARD+0x5560),0)
            vm.w(ZOMBIE+0x15c+0xc8,0)
            self.call(vm,'sun_rescue_once')
            self.assertEqual(vm.r(BOARD+0x5560),5000)

    def test_duplicate_rolls_never_make_two_or_extend_pending_deadline(self):
        vm=self.field()
        for replacement in range(32):
            result=self.roll(vm,25,replacement)
            self.assertEqual(result,replacement+(replacement>=25))
            self.assertNotEqual(result,25)
            self.assertEqual(vm.r(CHALLENGE+0x7c),5)
        vm.w(CHALLENGE+0x7c,2)
        self.assertNotEqual(self.roll(vm,34),25)
        self.assertEqual(vm.r(CHALLENGE+0x7c),2)
        self.assertEqual(self.roll(vm,3),3)
        self.assertEqual(vm.r(CHALLENGE+0x7c),2)

    def test_deferred_boss_fifth_roll_early_natural_and_save_resume(self):
        vm=self.field();self.roll(vm,25)
        vm.u.mem_write(ZOMBIE+0xec,b'\1')
        self.assertEqual([self.roll(vm,2) for _ in range(2)],[2,2])
        loaded=self.field(())
        loaded.u.mem_write(CHALLENGE,bytes(vm.u.mem_read(CHALLENGE,0xbc)))
        self.assertEqual([self.roll(loaded,2) for _ in range(3)],[2,2,25])
        self.assertEqual(loaded.r(CHALLENGE+0x7c),0)
        self.assertEqual(self.roll(loaded,2),2)
        vm=self.field();self.roll(vm,25)
        vm.u.mem_write(ZOMBIE+0xec,b'\1')
        self.assertEqual(self.roll(vm,33),25)
        self.assertEqual(vm.r(CHALLENGE+0x7c),0)

    def test_mode_boundaries_and_initial_weight_distribution(self):
        for mode in (60,61,70,71):
            vm=self.field((),mode)
            for ticket in range(33 if mode in (60,71) else 35):
                self.assertEqual(self.roll(vm,ticket),25 if ticket>=33 else ticket)
        vm=self.field((25,),0)
        self.assertEqual(self.roll(vm,25),25)
        self.assertEqual(vm.r(CHALLENGE+0x78),0)

    def test_boss_music_restores_each_actual_previous_tune_including_silence(self):
        for tune in (-1,1,3,7,9,10,12,13):
            vm=self.field();self.music(vm,tune)
            before=[vm.reg(r) for r in REGS]
            self.call(vm,'v5_boss_tick')
            self.assertEqual([vm.reg(r) for r in REGS],before)
            self.assertEqual(vm.r(MUSIC+8),12)
            self.assertEqual(vm.r(CHALLENGE+0x84),tune&0xffffffff)
            count=len(vm.events)
            self.call(vm,'v5_boss_tick')
            self.assertEqual(len(vm.events),count)
            vm.u.mem_write(ZOMBIE+0xec,b'\1')
            self.call(vm,'v5_boss_tick')
            self.assertEqual(vm.r(MUSIC+8),tune&0xffffffff)
            self.assertEqual(vm.r(CHALLENGE+0x80),0)
            count=len(vm.events);self.call(vm,'v5_boss_tick')
            self.assertEqual(len(vm.events),count)

    def test_music_stage_transition_save_and_trainer_changes_do_not_replace_capture(self):
        vm=self.field();self.music(vm,5)
        self.call(vm,'v5_boss_tick')
        vm.w(MUSIC+8,3)
        self.call(vm,'v5_boss_tick')
        self.assertEqual(vm.r(MUSIC+8),12)
        self.assertEqual(vm.r(CHALLENGE+0x84),5)
        loaded=self.field();self.music(loaded,12)
        loaded.u.mem_write(CHALLENGE,bytes(vm.u.mem_read(CHALLENGE,0xbc)))
        loaded.reg(UC_X86_REG_EDI,CHALLENGE)
        loaded.stub(0x40ca50,'clear_advice')
        loaded.run(0x429ff9,0x42a005)
        self.assertEqual(loaded.r(MUSIC+8),5)
        self.assertEqual(loaded.r(CHALLENGE+0x80),0)

    def test_older_multi_boss_save_keeps_first_and_credit_without_killing_allies(self):
        vm=self.field((25,0,25,25))
        vm.stub(0x532b40,'remove_cold')
        self.call(vm,'v5_boss_tick')
        self.assertEqual(vm.r(ZOMBIE+0xec),0)
        self.assertEqual(vm.r(ZOMBIE+0x15c+0xec),0)
        self.assertEqual(vm.r(ZOMBIE+2*0x15c+0xec),1)
        self.assertEqual(vm.r(ZOMBIE+3*0x15c+0xec),1)
        self.assertEqual(vm.r(CHALLENGE+0x7c),5)

    def waiting(self,vm):
        vm.w(CHALLENGE+0x60,5);vm.w(CHALLENGE+0x90,GRACE_MAGIC)
        vm.w(CHALLENGE+0xa0,1)

    def test_wait_message_refresh_and_priority_stop_when_car_is_active(self):
        vm=self.field((25,12));self.advice(vm);self.waiting(vm)
        vm.w(ZOMBIE+0x114,500)
        self.call(vm,'v5_boss_tick')
        self.assertEqual(vm.events,['正在等待冰车僵尸'])
        self.assertEqual(vm.r(ZOMBIE+0x114),50)
        car=ZOMBIE+0x15c;vm.w(car+0x134,ICE_MAGIC)
        self.call(vm,'v5_boss_tick')
        self.assertEqual(vm.r(ZOMBIE+0x114),200)
        for _ in range(400):self.call(vm,'v5_boss_tick')
        self.assertEqual(vm.events,['正在等待冰车僵尸']*2)
        vm.w(CHALLENGE+0xa0,2)
        self.call(vm,'v5_boss_tick')
        self.assertEqual(vm.r(MESSAGE+0x88),0)

    def test_wait_clearing_never_erases_unrelated_advice_and_pause_holds_state(self):
        vm=self.field();self.advice(vm);self.waiting(vm)
        self.call(vm,'v5_boss_tick')
        vm.u.mem_write(MESSAGE+4,b'other advice\0')
        vm.w(CHALLENGE+0xa0,2)
        self.call(vm,'v5_boss_tick')
        self.assertEqual(vm.r(MESSAGE+0x88),500)
        vm=self.field();self.music(vm,3);self.advice(vm);self.waiting(vm)
        vm.w(BOARD+0x164,1)
        self.call(vm,'v5_boss_tick')
        self.assertEqual(vm.events,[])

    def test_wait_spawn_is_car_but_other_phases_and_modes_keep_original_choice(self):
        for mode,score,state in ((70,5,1),(70,4,1),(70,5,2),(61,5,1),(71,5,1)):
            vm=self.field(mode=mode);self.waiting(vm)
            vm.w(CHALLENGE+0x60,score);vm.w(CHALLENGE+0xa0,state)
            vm.reg(UC_X86_REG_ESI,ZOMBIE);vm.reg(UC_X86_REG_EAX,4)
            vm.run(0x534e0a,0x534e10)
            self.assertEqual(vm.reg(UC_X86_REG_EAX),12 if (mode,score,state)==(70,5,1) else 4)


if __name__=='__main__':unittest.main()
