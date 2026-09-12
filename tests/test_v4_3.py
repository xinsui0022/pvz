"""Execute new hooks and native targeting with adversarial transition cases."""
from test_machine_code import *
del PatchTests
import test_v4_1
import test_v4_2
import test_tactical
from v4_1_fixes import GRACE_MAGIC
from v4_2_fixes import SLED_MAGIC, JOIN_MAGIC
from v4_3_fixes import ICE_MAGIC, RESCUE_MAGIC

wf, rf = test_v4_2.wf, test_v4_2.rf


def symbol(name):
    return int(MANIFEST['symbols'][name], 16)


class V43Tests(unittest.TestCase):
    def test_actual_new_game_constructor_resets_reused_rescue_and_grace_memory(self):
        for mode in (60,61,70,71):
            vm=VM(mode=mode)
            vm.w(0x6a9f38,APP)
            vm.u.mem_write(CHALLENGE+0x90,b'\x77'*24)
            vm.w(CHALLENGE+0xa4,RESCUE_MAGIC)
            vm.reg(UC_X86_REG_EDI,CHALLENGE)
            vm.run(0x41f1b0,0x41f23d)
            if 61<=mode<=70:
                self.assertEqual(bytes(vm.u.mem_read(CHALLENGE+0x90,24)),b'\0'*24)
            else:
                self.assertEqual(vm.r(CHALLENGE+0xa4),RESCUE_MAGIC)

    def test_rescue_threshold_once_save_stage_modes_and_pause(self):
        for mode in (60,61,70,71):
            for money in (0,24,25,26):
                vm=VM(mode=mode)
                vm.w(BOARD+0x5560,money)
                vm.reg(UC_X86_REG_EBP,CHALLENGE)
                before=[vm.reg(r) for r in REGS]
                vm.run(symbol('sun_rescue_once'))
                eligible=61<=mode<=70 and money<=25
                self.assertEqual(vm.r(BOARD+0x5560),money+5000*eligible)
                self.assertEqual([vm.reg(r) for r in REGS],before)
                self.assertEqual(vm.r(CHALLENGE+0xa4),RESCUE_MAGIC if eligible else 0)
                if eligible:
                    loaded=VM(mode=mode)
                    loaded.u.mem_write(CHALLENGE,bytes(vm.u.mem_read(CHALLENGE,0xbc)))
                    loaded.w(CHALLENGE+0x6c,10)
                    loaded.w(BOARD+0x5560,25)
                    loaded.reg(UC_X86_REG_EBP,CHALLENGE)
                    loaded.run(symbol('sun_rescue_once'))
                    self.assertEqual(loaded.r(BOARD+0x5560),25)
        vm=VM();vm.w(BOARD+0x164,1);vm.reg(UC_X86_REG_EBP,CHALLENGE)
        vm.run(symbol('sun_rescue_once'))
        self.assertEqual(vm.r(CHALLENGE+0xa4),0)

    def test_rescue_native_message_copies_exact_gbk_and_bottom_style(self):
        vm=VM();message=APP+0x9000
        vm.u.mem_map(0,0x1000)
        vm.w(BOARD+0x140,message)
        vm.w(message,APP);vm.w(message+0x290,-1)
        def translate(v):
            src=v.reg(UC_X86_REG_EDX);dest=v.reg(UC_X86_REG_EDI)
            self.assertEqual(src,symbol('rescue_string'))
            v.u.mem_write(dest,bytes(v.u.mem_read(src,28)))
            v.ret()
        vm.stubs[0x519520]=translate
        vm.stub(0x458fc0,'clear_text_animation')
        vm.stub(0x61c19a,'free_string')
        vm.reg(UC_X86_REG_EBP,CHALLENGE)
        vm.run(symbol('sun_rescue_once'))
        text='触发恢复机制，恢复5000阳光，最后一次恢复'.encode('gbk')+b'\0'
        self.assertEqual(bytes(vm.u.mem_read(message+4,len(text))),text)
        self.assertEqual(vm.r(message+0x8c),7)
        self.assertEqual(vm.r(message+0x88),500)
        self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK+4)

    def spawn_tag(self,vm,ptr):
        vm.w(ptr,APP);vm.w(ptr+4,BOARD)
        vm.reg(UC_X86_REG_ESP,STACK)
        vm.reg(UC_X86_REG_EAX,ptr)
        vm.reg(UC_X86_REG_ESI,ZOMBIE)
        vm.run(0x534e1c,0x534e25)

    def witness(self,vm,ptr,ice_x):
        vm.reg(UC_X86_REG_ESP,STACK)
        vm.reg(UC_X86_REG_ESI,ptr)
        vm.reg(UC_X86_REG_EAX,ice_x)
        vm.reg(UC_X86_REG_EDX,BOARD)
        vm.run(0x52a88d,0x52a897)

    def test_boss_requires_new_boss_car_full_lane_not_20_second_timer(self):
        helper=test_v4_1.V41Tests()
        vm=helper.field((),(25,12));car=ZOMBIE+0x15c
        # A car emitted before the final brain is never accepted.
        vm.w(CHALLENGE+0x60,4)
        self.spawn_tag(vm,car)
        self.assertEqual(vm.r(car+0x134),0)
        vm.w(CHALLENGE+0x60,5);helper.start(vm)
        self.witness(vm,car,25)
        self.assertEqual(vm.r(CHALLENGE+0xa0),1)
        for _ in range(2001):helper.tick(vm)
        self.assertNotIn('complete',vm.events)
        self.spawn_tag(vm,car)
        self.assertEqual(vm.r(car+0x134),ICE_MAGIC)
        # Even an existing full lane cannot substitute for this car's path.
        vm.w(BOARD+0x60c,25)
        self.witness(vm,car,200)
        helper.tick(vm)
        self.assertNotIn('complete',vm.events)
        vm.u.mem_write(car+0xec,b'\1')
        self.witness(vm,car,25)
        self.assertEqual(vm.r(CHALLENGE+0xa0),1)
        vm.u.mem_write(car+0xec,b'\0')
        self.witness(vm,car,26)
        self.assertEqual(vm.r(CHALLENGE+0xa0),1)
        self.witness(vm,car,25)
        helper.tick(vm);helper.tick(vm)
        self.assertEqual(vm.events,['complete'])

    def test_boss_plus_sunflower_requires_both_and_stage_provenance(self):
        helper=test_v4_1.V41Tests()
        vm=helper.field((1,),(25,12));car=ZOMBIE+0x15c
        helper.start(vm);self.spawn_tag(vm,car)
        vm.w(car+0x138,99)
        self.witness(vm,car,25)
        self.assertEqual(vm.r(CHALLENGE+0xa0),1)
        self.spawn_tag(vm,car);self.witness(vm,car,25)
        loaded=helper.field((1,),(25,12))
        loaded.u.mem_write(CHALLENGE,bytes(vm.u.mem_read(CHALLENGE,0xbc)))
        loaded.w(BOARD+0x164,1)
        helper.tick(loaded)
        self.assertEqual(loaded.r(CHALLENGE+0x94),2000)
        loaded.w(BOARD+0x164,0)
        for _ in range(1999):helper.tick(loaded)
        self.assertEqual(loaded.events,[])
        helper.tick(loaded)
        self.assertEqual(loaded.events,['complete'])

    def test_old_waiting_save_migrates_and_dead_boss_cannot_strand_a_win(self):
        helper=test_v4_1.V41Tests()
        vm=helper.field((),(25,12));car=ZOMBIE+0x15c
        vm.w(CHALLENGE+0x90,GRACE_MAGIC)
        vm.w(CHALLENGE+0x98,3)
        vm.w(CHALLENGE+0x94,1)
        helper.tick(vm)
        self.assertEqual(vm.r(CHALLENGE+0xa0),1)
        self.spawn_tag(vm,car)
        vm.u.mem_write(ZOMBIE+0xec,b'\1')
        helper.tick(vm)
        self.assertEqual(vm.events,[])
        vm.u.mem_write(car+0xec,b'\1')
        helper.tick(vm)
        self.assertEqual(vm.events,['complete'])

    def arrival(self,vm,ptr):
        vm.reg(UC_X86_REG_ESP,STACK)
        vm.reg(UC_X86_REG_EAX,ptr)
        vm.run(0x528050,0x528055)

    def test_random_sled_arrives_from_right_then_depart_as_team(self):
        vm,team=test_v4_2.V42Tests().sled()
        wf(vm,team[0]+0x2c,600.5)
        vm.reg(UC_X86_REG_EAX,team[0]);vm.run(0x651177,0x651180)
        self.assertEqual([rf(vm,p+0x2c) for p in team],[600.5,800,850,900])
        self.assertEqual(vm.r(team[0]+0x13c),320)
        self.arrival(vm,team[0])
        self.assertEqual(rf(vm,team[0]+0x34),0)
        for i,p in enumerate(team[1:]):
            self.arrival(vm,p)
            self.assertEqual(rf(vm,p+0x2c),794+50*i)
        for _ in range(50):
            for p in team:self.arrival(vm,p)
        self.assertEqual([rf(vm,p+0x2c) for p in team],[600.5,650.5,700.5,750.5])
        self.assertTrue(all(abs(rf(vm,p+0x34)-0.6)<0.001 for p in team))

    def test_sled_four_cell_cap_red_line_old_save_and_real_ice(self):
        for origin,bound in ((850,530),(700,440),(440,440),(222.25,222.25)):
            vm,team=test_v4_2.V42Tests().sled()
            leader=team[0]
            wf(vm,leader+0x2c,origin)
            vm.reg(UC_X86_REG_EAX,leader)
            vm.run(symbol('sled_private_ice_init'))
            vm.w(leader+0x13c,400)  # V4.0.2 save.
            vm.w(BOARD+0x60c,25);vm.w(BOARD+0x624,4500)
            def crash(v):
                self.assertEqual(v.reg(UC_X86_REG_EBX),leader)
                v.events.append('crash');v.w(leader+0x28,19);v.ret()
            vm.stubs[0x527f20]=crash
            if origin>bound+2:
                wf(vm,leader+0x2c,bound+2)
                vm.reg(UC_X86_REG_ESI,leader)
                vm.run(0x5281d5,0x52822d)
                self.assertNotIn('crash',vm.events)
            wf(vm,leader+0x2c,bound+0.5)
            vm.reg(UC_X86_REG_ESI,leader)
            vm.run(0x5281d5,0x52822d)
            self.assertEqual(vm.events,['crash'])
            self.assertEqual(rf(vm,leader+0x2c),bound)
            self.assertEqual(vm.r(leader+0x13c),320)
            self.assertEqual(vm.r(leader+0xc4),0)
            self.assertEqual(vm.r(leader+0xd0),0)

    def test_incoming_members_never_slide_over_four_cells_for_left_conversion(self):
        vm,team=test_v4_2.V42Tests().sled()
        wf(vm,team[0]+0x2c,222.25)
        vm.reg(UC_X86_REG_EAX,team[0]);vm.run(0x651177,0x651180)
        for _ in range(60):
            for p in team:self.arrival(vm,p)
        self.assertEqual([rf(vm,p+0x2c) for p in team],[222.25,480,530,580])

    def test_dancer_reach_hooks_reject_two_columns_but_allow_close(self):
        for plant in (4,6,17):
            for mode in (60,61,70,71):
                for x in (350,440,460):
                    vm=VM(mode=mode)
                    vm.w(PLANT+0x24,plant);vm.w(PLANT+0x28,3)
                    vm.w(PLANT+8,900) # A squash's moved X must not expand reach.
                    vm.w(ZOMBIE+0x24,8);vm.w(ZOMBIE+8,x)
                    vm.reg(UC_X86_REG_ESI,ZOMBIE);vm.reg(UC_X86_REG_EDI,PLANT)
                    vm.run(symbol('dancer_lethal_reach'))
                    self.assertEqual(vm.reg(UC_X86_REG_EAX),int(61<=mode<=70 and x+36>=440))
        helper=test_tactical.TacticalTests()
        for biting in (False,True):
            # Native FindTargetZombie runs from prologue to return, with an
            # intentionally overlapping collision rectangle after reacquire.
            self.assertEqual(helper.target(kind=8,phase=43,col=3,x=440,biting=biting),0)
            self.assertEqual(helper.target(kind=8,phase=43,col=4,x=440,biting=biting),ZOMBIE)

    def test_native_squash_retarget_and_landing_damage_respect_original_column(self):
        for mode,col,allowed in ((70,3,False),(70,4,True),(0,3,True)):
            for entry in (0x4607e0,0x4606f0):
                vm=VM(mode=mode)
                vm.w(BOARD+0x90,ZOMBIE);vm.w(BOARD+0x94,1)
                vm.w(ZOMBIE+0x158,0x10000);vm.w(ZOMBIE+0x24,8)
                vm.w(ZOMBIE+8,440);vm.w(PLANT+0x24,17)
                vm.w(PLANT+0x28,col);vm.w(PLANT+8,450)
                vm.stub(0x45eb10,'flags',4,eax=1)
                def attack(v):
                    dest=v.reg(UC_X86_REG_EAX)
                    for off,val in ((0,430),(4,0),(8,100),(12,100)):v.w(dest+off,val)
                    v.ret(4)
                def body(v):
                    dest=v.reg(UC_X86_REG_EDI)
                    for off,val in ((0,450),(4,0),(8,42),(12,115)):v.w(dest+off,val)
                    v.ret()
                vm.stubs[0x467f90]=attack;vm.stubs[0x5320b0]=body
                vm.stub(0x5324b0,'kelp',eax=0)
                vm.stub(0x531a80,'damageable',4,eax=1)
                vm.stub(0x5346a0,'sled_position',eax=-1)
                vm.stub(0x52bee0,'backwards',eax=0)
                vm.stub(0x5317c0,'damage',4)
                vm.w(STACK+4,PLANT)
                vm.run(entry)
                if entry==0x4607e0:
                    self.assertEqual(vm.reg(UC_X86_REG_EAX),ZOMBIE if allowed else 0)
                else:
                    self.assertEqual('damage' in vm.events,allowed)


if __name__=='__main__':unittest.main()
