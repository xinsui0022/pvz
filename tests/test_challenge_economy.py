import unittest
from test_machine_code import VM, MANIFEST, APP, BOARD, CHALLENGE, PLANT, ZOMBIE, STACK
from unicorn.x86_const import *
from challenge_mode import CHALLENGE_FIELD, CHALLENGE_MAGIC


class ChallengeEconomyTests(unittest.TestCase):
    def configure(self, seed, mode=70, challenge=True, health=280):
        vm=VM(mode=mode)
        vm.w(CHALLENGE+CHALLENGE_FIELD,CHALLENGE_MAGIC if challenge else 0)
        vm.w(PLANT+0x24,seed); vm.w(PLANT+0x40,health)
        vm.reg(UC_X86_REG_ESI,PLANT); vm.coin_stub()
        return vm

    def test_biting_sun_family_uses_native_health_boundaries(self):
        for seed in (1,9,41,0):
            for mode,challenge in ((70,True),(61,True),(70,False),(0,True)):
                for health in (300,280,40,4,1):
                    with self.subTest(seed=seed,mode=mode,challenge=challenge,health=health):
                        vm=self.configure(seed,mode,challenge,health)
                        vm.reg(UC_X86_REG_EBP,ZOMBIE)
                        vm.reg(UC_X86_REG_ECX,seed); vm.reg(UC_X86_REG_EBX,1)
                        vm.run(0x52FC9C,0x52FCF4)
                        eligible=mode>=61 and (seed==1 or (challenge and seed in (9,41)))
                        expected=int(eligible and (health//40 != (health-4)//40 or health<=4))
                        if seed==41 and mode>=61 and challenge: expected*=2
                        self.assertEqual(len(vm.events),expected)
                        self.assertEqual(vm.r(PLANT+0x40),(health-4)&0xffffffff)
                        self.assertEqual(vm.r(PLANT+0x24),seed)
                        self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK)

    def test_remaining_sun_on_explosive_death_keeps_abi_and_quantity(self):
        for seed in (1,9,41,0):
            for challenge in (True,False):
                vm=self.configure(seed,challenge=challenge,health=300)
                vm.w(STACK+4,CHALLENGE)
                vm.run(0x42B9D0)
                expected=8 if seed==1 or (challenge and seed in (9,41)) else 0
                if seed==41 and challenge: expected*=2
                self.assertEqual(len(vm.events),expected)
                self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK+8)
                self.assertEqual(vm.r(PLANT+0x24),seed)

    def test_projectile_damage_sun_family_never_duplicates_payout(self):
        for seed in (1,9,41,0):
            for challenge in (True,False):
                vm=self.configure(seed,challenge=challenge,health=80)
                vm.stub(0x4679B0,'die',pop=4)
                vm.reg(UC_X86_REG_ECX,40)
                vm.run(int(MANIFEST['symbols']['projectile_damage'],16))
                self.assertEqual(vm.r(PLANT+0x40),40)
                expected=1 if seed==1 or (challenge and seed in (9,41)) else 0
                if seed==41 and challenge: expected*=2
                self.assertEqual(len(vm.events),expected)
                vm.reg(UC_X86_REG_ESP,STACK)
                vm.run(int(MANIFEST['symbols']['projectile_damage'],16))
                self.assertEqual(vm.r(PLANT+0x40),0)
                self.assertEqual(sum(isinstance(event,tuple) and event[0]=='sun' for event in vm.events),3*expected)
                self.assertEqual(vm.events[-1],'die')
                self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK+4)

    def test_twin_explosive_kills_double_once_through_both_native_wrappers(self):
        for hook in ('jack_sun','jalapeno_sun'):
            vm=self.configure(41,health=300)
            def die(v):
                v.u.mem_write(PLANT+0x141,b'\1')
                v.ret(4)
            vm.stubs[0x4679B0]=die
            for attempt in range(2):
                vm.reg(UC_X86_REG_ESP,STACK)
                vm.w(STACK+4,PLANT)
                vm.reg(UC_X86_REG_EAX,PLANT)
                vm.run(int(MANIFEST['symbols'][hook],16))
                self.assertEqual(len(vm.events),16)
                self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK+8)


if __name__=='__main__': unittest.main()
