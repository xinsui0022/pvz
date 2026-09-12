"""V4.2 native butter lifecycle, per-team ice, HP rendering and win grace."""
from test_machine_code import *
del PatchTests
import test_v4
import test_v4_1
from v4_2_fixes import SLED_MAGIC, HP_MAGIC

wf, rf = test_v4.wf, test_v4.rf
GFX = APP+0xc000


def symbol(name):
    return int(MANIFEST['symbols'][name], 16)


class V42Tests(unittest.TestCase):
    def test_actual_butter_application_and_removal_keep_all_four_members(self):
        helper = test_v4.V4Tests()
        for binary in (ORIGINAL, PATCHED):
            for member in range(1, 5):
                vm, team = helper.team(binary)
                ptr = team[member]
                vm.u.mem_write(ptr+0xba, b'\1')
                vm.stub(0x531a10, 'can_freeze', eax=1)
                vm.stub(0x5324b0, 'kelp', eax=0)
                vm.stub(0x52f050, 'animation')
                vm.stub(0x530850, 'stop_sound', 4)
                vm.stub(0x530770, 'start_sound')
                vm.reg(UC_X86_REG_EAX, ptr)
                vm.run(0x5326d0)
                self.assertEqual(vm.r(ptr+0xb0), 400)
                self.assertEqual(vm.r(ptr+0xf0), 0 if binary == ORIGINAL else 0x10000)
                if binary == ORIGINAL: continue
                before = [rf(vm,p+0x2c) for p in team]
                for p in team: helper.walk(vm,p)
                self.assertEqual([rf(vm,p+0x2c) for p in team], before)
                vm.w(ptr+0xb0, 0)
                vm.reg(UC_X86_REG_ESP, STACK)
                vm.reg(UC_X86_REG_EAX, ptr)
                vm.run(0x532570)
                for p in reversed(team): helper.walk(vm,p)
                for p,x in zip(team,before):
                    self.assertAlmostEqual(x-rf(vm,p+0x2c),0.45,delta=0.001)
                self.assertEqual(vm.r(ptr+0xf0),0x10000)

    def test_old_butter_orphan_recovers_without_adopting_foreign_members(self):
        helper = test_v4.V4Tests()
        vm, team = helper.team()
        vm.w(team[1]+0xf0,0)
        vm.w(team[2]+0xf0,0x20000)
        vm.w(team[3]+0xf0,0)
        vm.w(team[3]+0xb8,1)
        helper.walk(vm,team[0])
        self.assertEqual(vm.r(team[1]+0xf0),0x10000)
        self.assertEqual(vm.r(team[2]+0xf0),0x20000)
        self.assertEqual(vm.r(team[3]+0xf0),0)

    def test_butter_does_not_change_other_modes_or_non_dancer_links(self):
        for mode,kind in ((60,9),(71,9),(70,0)):
            vm=VM(mode=mode)
            vm.w(ZOMBIE+0x24,kind)
            vm.w(PLANT+0x24,8)
            vm.w(ZOMBIE+0xf0,123)
            vm.w(PLANT+0xf0,456)
            vm.reg(UC_X86_REG_ESI,ZOMBIE)
            vm.reg(UC_X86_REG_EAX,PLANT)
            vm.run(0x53274e,0x532762)
            self.assertEqual(vm.r(ZOMBIE+0xf0),0)
            self.assertEqual(vm.r(PLANT+0xf0),0)

    def test_sunflower_waits_full_20_seconds(self):
        helper=test_v4_1.V41Tests()
        vm=helper.field((1,),())
        helper.start(vm)
        for _ in range(1999): helper.tick(vm)
        self.assertEqual(vm.events,[])
        self.assertEqual(vm.r(CHALLENGE+0x94),1)
        helper.tick(vm)
        self.assertEqual(vm.events,['complete'])
        helper.tick(vm)
        self.assertEqual(vm.events,['complete'])

    def sled(self, mode=70, roll=0):
        vm,team=test_v4.V4Tests().team(mode=mode)
        vm.w(BOARD+0x94,4)
        vm.w(BOARD+0x98,4)
        for p in team[:4]:
            vm.w(p+0x24,13)
            vm.w(p+0x28,17)
            vm.w(p+0x68,500)
        for i,p in enumerate(team[:4]): wf(vm,p+0x2c,600.5+i*50)
        def rng(v):
            self.assertEqual(v.reg(UC_X86_REG_EAX),2)
            v.events.append('roll')
            v.ret(eax=roll)
        vm.stubs[0x5af400]=rng
        return vm,team[:4]

    def sled_ice(self, vm, ptr):
        vm.reg(UC_X86_REG_ESP,STACK)
        vm.reg(UC_X86_REG_ESI,ptr)
        # Return at the original epilogue, retaining the real damage call ABI.
        def damage(v):
            self.assertEqual(v.reg(UC_X86_REG_EAX),8)
            self.assertEqual(v.r(v.reg(UC_X86_REG_ESP)+4),6)
            v.events.append('damage')
            v.ret(4)
        vm.stubs[0x5317c0]=damage
        vm.run(0x5281d5,0x52822d)
        self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK)

    def test_health_toggle_modes_pause_and_serialized_state(self):
        for mode in (60,61,70,71):
            vm=VM(mode=mode)
            vm.w(BOARD+0x8c,APP)
            vm.w(BOARD+0x164,1)
            for enabled in (True,False,True):
                vm.reg(UC_X86_REG_ESP,STACK)
                vm.reg(UC_X86_REG_ECX,BOARD)
                vm.w(STACK+4,119)
                vm.run(0x41b820,STOP if 61<=mode<=70 else 0x41b826)
                self.assertEqual(vm.r(CHALLENGE+0x9c)==HP_MAGIC,enabled and 61<=mode<=70)
                if not 61<=mode<=70: break

    def test_health_totals_include_depleted_armor_without_changing_zombie(self):
        for cur,maximum,expected in (((270,370,1100),(270,370,1100),(1740,1740)),
                ((1,-5,0),(500,300,0),(1,800)), ((300,0,0),(200,0,0),(300,300))):
            vm=VM()
            for off,h,m in zip((0xc8,0xd0,0xdc),cur,maximum):
                vm.w(ZOMBIE+off,h);vm.w(ZOMBIE+off+4,m)
            old=bytes(vm.u.mem_read(ZOMBIE,0x15c))
            vm.reg(UC_X86_REG_ESI,ZOMBIE)
            vm.run(symbol('health_display_totals'))
            self.assertEqual((vm.reg(UC_X86_REG_EAX),vm.reg(UC_X86_REG_EDX)),expected)
            self.assertEqual(bytes(vm.u.mem_read(ZOMBIE,0x15c)),old)

    def render(self, mode=70, enabled=True, kind=0, health=270):
        vm=VM(mode=mode)
        vm.w(BOARD+0x8c,APP)
        vm.w(BOARD+0x90,ZOMBIE)
        vm.w(BOARD+0x94,1)
        vm.w(ZOMBIE+0x158,0x10000)
        vm.w(ZOMBIE+0x24,kind)
        vm.w(ZOMBIE+0xc8,health)
        vm.w(ZOMBIE+0xcc,270 if kind!=25 else 500)
        wf(vm,ZOMBIE+0x2c,300)
        wf(vm,ZOMBIE+0x30,200)
        vm.w(CHALLENGE+0x9c,HP_MAGIC if enabled else 0)
        for off,val in ((0x30,11),(0x34,22),(0x38,33),(0x3c,44),(0x44,1)):
            vm.w(GFX+off,val)
        graphics=bytes(vm.u.mem_read(GFX,0x50))
        zombie=bytes(vm.u.mem_read(ZOMBIE,0x15c))
        def rect(v):
            self.assertEqual(v.reg(UC_X86_REG_EAX),GFX)
            sp=v.reg(UC_X86_REG_ESP)
            args=[v.r(sp+i*4) for i in range(1,5)]
            colors=[v.r(GFX+0x30+i*4) for i in range(4)]
            v.events.append((args,colors))
            v.ret(16)
        vm.stubs[0x586d50]=rect
        vm.w(STACK+4,BOARD)
        vm.w(STACK+8,GFX)
        vm.run(symbol('health_overlay_draw'))
        self.assertEqual(vm.reg(UC_X86_REG_ESP),STACK+12)
        self.assertEqual(bytes(vm.u.mem_read(GFX,0x50)),graphics)
        self.assertEqual(bytes(vm.u.mem_read(ZOMBIE,0x15c)),zombie)
        return vm

    def test_health_overlay_geometry_numbers_colors_and_graphics_restoration(self):
        vm=self.render()
        self.assertEqual(vm.events[0][0],[335,187,50,18])
        self.assertEqual(vm.events[1][0],[336,188,48,4])
        self.assertTrue(all(e[0][2:]==[2,2] for e in vm.events[2:]))
        for mode,enabled,hp in ((60,True,270),(71,True,270),(70,False,270),(70,True,0)):
            self.assertEqual(self.render(mode,enabled,health=hp).events,[])
        boss=self.render(kind=25,health=1)
        self.assertEqual(boss.events[1][0][2],1)
        self.assertEqual(boss.events[1][1][:2],[255,65])

    def test_new_hooks_overwrite_whole_instructions(self):
        from capstone import Cs,CS_ARCH_X86,CS_MODE_32
        pe=pefile.PE(data=ORIGINAL)
        dis=Cs(CS_ARCH_X86,CS_MODE_32)
        for site in (0x53274e,0x651177,0x5281d5,0x41b820,0x419ae0):
            h=next(h for h in MANIFEST['hooks'] if int(h['va'],16)==site)
            self.assertEqual(sum(i.size for i in dis.disasm(pe.get_data(site-0x400000,h['length']),site)),h['length'])


if __name__=='__main__': unittest.main()
