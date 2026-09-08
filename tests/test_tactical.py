import unittest
from test_machine_code import VM, ORIGINAL, PATCHED, APP, BOARD, PLANT, ZOMBIE, CHALLENGE, STACK, STOP, REGS
from test_machine_code import UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP

class TacticalTests(unittest.TestCase):
    def vm(self,mode=70):
        v=VM(mode=mode)
        v.w(0x6a9ec0,APP);v.w(BOARD+0x138,APP+0x9000)
        v.w(APP+0x9028,66)
        return v

    def price(self,v,seed=66,current=False):
        v.reg(UC_X86_REG_ESP,STACK);v.w(STACK,STOP)
        v.reg(UC_X86_REG_EAX,seed);v.reg(UC_X86_REG_EDX,0xffffffff)
        v.reg(UC_X86_REG_EDI,BOARD)
        v.run(0x41dae0 if current else 0x467b00)
        self.assertEqual(v.reg(UC_X86_REG_ESP),STACK+4)
        return v.reg(UC_X86_REG_EAX)

    def purchased(self,v,seed=66):
        v.w(APP+0x9028,seed)
        v.reg(UC_X86_REG_ESP,STACK);v.reg(UC_X86_REG_EBP,CHALLENGE)
        v.run(0x42a42a,0x42a433)
        self.assertEqual(v.reg(UC_X86_REG_ESP),STACK)
        self.assertEqual(v.reg(UC_X86_REG_EAX),BOARD)
        self.assertEqual(v.reg(UC_X86_REG_ECX),APP+0x9000)

    def test_price_sequence_display_charge_stage_save_restart(self):
        v=self.vm()
        for i in range(6):
            expected=75 if i%2==0 else 100
            for _ in range(3):
                self.assertEqual(self.price(v),expected)
                self.assertEqual(self.price(v,current=True),expected)
            self.purchased(v)
            v.w(CHALLENGE+0x6c,i+1)
            # Save/load uses the actual entire serialized Challenge storage.
            loaded=self.vm()
            loaded.u.mem_write(CHALLENGE,bytes(v.u.mem_read(CHALLENGE,0xbc)))
            v=loaded
        self.purchased(v)
        self.assertEqual(self.price(v),100)
        # Execute actual constructor initialization through its first memset.
        v.w(0x6a9f38,APP);v.reg(UC_X86_REG_EDI,CHALLENGE)
        v.reg(UC_X86_REG_ESP,STACK);v.run(0x41f1b0,0x41f23d)
        self.assertEqual(self.price(v),75)

    def test_other_cards_modes_and_missing_board(self):
        v=self.vm()
        for seed,cost in [(65,125),(63,125),(60,50),(67,175)]:
            self.assertEqual(self.price(v,seed),cost)
            self.purchased(v,seed)
            self.assertEqual(v.r(CHALLENGE+0xb8),0)
        for mode in (0,60,71):
            v=self.vm(mode);self.assertEqual(self.price(v),125)
            self.purchased(v);self.assertEqual(v.r(CHALLENGE+0xb8),0)
        v=self.vm();v.w(APP+0x768,0)
        self.assertEqual(self.price(v),125)

    def test_successful_payment_places_then_toggles_and_failure_does_not(self):
        for money,parity,success in [(75,0,True),(74,0,False),(100,1,True),(99,1,False)]:
            v=self.vm();v.w(CHALLENGE+0xb8,parity);v.w(BOARD+0x5560,money)
            # Execute actual mouse-placement payment through the post-spawn
            # hook; stub only advice, coin counting, spawn and failure sound.
            v.reg(UC_X86_REG_EBP,CHALLENGE);v.reg(UC_X86_REG_ESI,BOARD)
            v.reg(UC_X86_REG_ESP,STACK)
            v.stub(0x41b980,'count_sun',eax=0)
            v.stub(0x40cab0,'advice')
            v.stub(0x42a0f0,'spawn',pop=8)
            v.w(BOARD+0x8c,APP);v.w(APP,APP+0xa000)
            v.w(APP+0xa0d8,0x800100);v.stub(0x800100,'failure_sound',pop=4)
            v.run(0x42a3bd,0x42a433 if success else 0x42a51a)
            self.assertEqual(v.r(CHALLENGE+0xb8),parity^int(success))
            self.assertEqual('spawn' in v.events,success)
            self.assertEqual(v.r(BOARD+0x5560),0 if success else money)

    def target(self,binary=PATCHED,mode=70,phase=33,col=0,x=0,plant=6,kind=17,biting=True,gap=None,eating=True):
        v=VM(binary,mode)
        v.w(BOARD+0x90,ZOMBIE);v.w(BOARD+0x94,1)
        v.w(ZOMBIE+0x158,0x10000);v.w(ZOMBIE+0x24,kind);v.w(ZOMBIE+0x28,phase)
        v.w(ZOMBIE+8,x);v.w(ZOMBIE+0x1c,0);v.u.mem_write(ZOMBIE+0x51,bytes([eating]))
        v.w(PLANT+0x24,plant);v.w(PLANT+0x28,col);v.w(PLANT+8,40)
        v.w(PLANT+0x3c,10 if biting else 0)
        v.stub(0x45eb10,'damage_flags',pop=4,eax=1)
        def rect(v):
            p=v.reg(UC_X86_REG_EAX)
            for off,value in [(0,120),(4,0),(8,40),(12,100)]:v.w(p+off,value)
            v.ret(4)
        v.stubs[0x467f90]=rect
        v.stub(0x5324b0,'special_head',eax=0)
        v.stub(0x531a80,'damageable',pop=4,eax=1)
        def zr(v):
            p=v.reg(UC_X86_REG_EDI)
            for off,value in [(0,80 if gap is None else 160+gap),(4,0),(8,100),(12,100)]:v.w(p+off,value)
            v.ret()
        v.stubs[0x5320b0]=zr
        if gap is None:v.stub(0x41c820,'overlap',eax=0)
        v.w(STACK+4,PLANT);v.w(STACK+8,0);v.reg(UC_X86_REG_ECX,0)
        v.run(0x4675c0)
        self.assertEqual(v.reg(UC_X86_REG_ESP),STACK+12)
        return v.reg(UC_X86_REG_EAX)

    def test_original_digger_swallow_target_reproduced_and_excluded(self):
        self.assertEqual(self.target(ORIGINAL),ZOMBIE)
        for phase in range(32,39):
            for biting in (False,True):
                for x in (-20,0,80):
                    self.assertEqual(self.target(phase=phase,biting=biting,x=x),0)

    def test_digger_protection_is_local_to_rear_chomper_and_iz(self):
        for kwargs in [dict(col=1),dict(x=81),dict(phase=0),dict(mode=0),dict(kind=0),dict(plant=0)]:
            self.assertEqual(self.target(**kwargs),ZOMBIE,kwargs)

    def test_dancer_cannot_inherit_dead_backups_extended_bite_range(self):
        # Real rectangle-overlap code: mouth ends at x=160; the leader
        # stands beyond it. Old bite reacquisition admits a 60-pixel gap.
        for gap in (1,30,60):
            self.assertEqual(self.target(ORIGINAL,kind=8,phase=43,gap=gap,eating=False),ZOMBIE)
            for phase in range(40,51):
                self.assertEqual(self.target(kind=8,phase=phase,gap=gap,eating=False),0)
        for gap in (-20,0):
            self.assertEqual(self.target(kind=8,phase=43,gap=gap),ZOMBIE)
        for kind,mode in ((9,70),(0,70),(8,0),(8,71)):
            self.assertEqual(self.target(kind=kind,mode=mode,gap=30),ZOMBIE)
        self.assertEqual(self.target(kind=8,gap=30,biting=False,eating=True),0)

if __name__=='__main__':unittest.main()
