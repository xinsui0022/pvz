# 定位记录与实现约束

参考重建仓库提交：`8a2d121899ba5cb4df644cd7d2e4c1aaf88dd238`。函数地址与调用约定以本地用户 EXE 的反汇编为准。

## 僵王崩溃

用户日志：访问异常 `0x004539F1`，EAX=0。原作者在 `0x5366D0` 的 `Zombie::BossDie` 入口跳转到 `0x651213`，执行：

```asm
pushad
mov eax, [ecx]    ; ECX 仍是 Zombie*，EAX 才是 LawnApp*
call 0x4539D0    ; IsFinalBossLevel 实际要求 ECX=LawnApp*
```

函数把僵尸及相邻内存解释成 LawnApp，最终把 `[ECX+0x82C]` 当成 PlayerInfo，再读取 `[EAX+0x24]`。仿真能够复现相同的崩溃指令。

修复保留 Zombie 指针，正确向 ECX 传入 LawnApp；真正的僵王关卡恢复原 prologue 并进入原函数。我是僵尸只移除当前僵王的球（清零 ID 后调用具备代际校验的 RemoveReanimation）与寒冷效果，然后标记其死亡。原补丁以 DWORD 写入 bool `mDead`，现改为 BYTE，保护紧邻字段。关卡判断另加 PlayerInfo 空指针保护。

## 阳光与死亡

原版啃食按 40 血量分段，最终死亡还有最后一份阳光。剩余份数定义：`R(h)=h//40+1 (h>0)`，否则为 0。伤害 d 应掉 `R(h)-R(h-d)` 份，每份 25 阳光。

300 血的向日葵受到 4 次 75 点投篮伤害：每次 2 份阳光，第四次血量为 0，总计 200。原 `Plant::Update` 判断为 `<0`，因此正好归零的植物仍可留在场上。新投篮／豌豆伤害路径在 `<=0` 时调用 Plant::Die；不会把“阳光已经掉完”作为死亡判据。

小丑和辣椒的即时摧毁则调用原 `IZombiePlantDropRemainingSun`，仅针对活着、血量正数的植物。普通植物过滤由原函数处理。

关键 ABI：

| 函数 | 输入 | 栈清理 |
| --- | --- | --- |
| IsIZombieLevel `4537D0` | EAX=app | ret |
| IsFinalBossLevel `4539D0` | ECX=app | ret |
| AddCoin `40CB10` | ECX=board，栈 x,y,type,motion | ret 16 |
| Plant::Die `4679B0` | 栈 plant | ret 4 |
| DropRemainingSun `42B9D0` | ESI=plant，栈 challenge | ret 4 |
| GetBrainTarget `42B810` | EAX=zombie，栈 challenge | ret 4 |
| SquishBrain `42BA30` | EAX=brain，栈 challenge | ret 4 |
| GetGridItemAt `408E40` | EDX=board，EBX=column，EDI=row，栈 type | ret 4 |
| PogoBreak `525350` | 栈 zombie,damageFlags | ret 8 |
| PlayZombieReanim `528B00` | EDI=zombie，栈 track,loop,blend,rate | ret 16 |

投篮伤害位置仍有活跃 x87 栈值。统一伤害例程保存／恢复对齐的 FXSAVE 区域，保留寄存器；桥接代码重放原比较指令。不能仅用 pushad 替代浮点保存。

## 水生、跳跳与脑子

不改 Board 的行类型，也不改植物类型。水生修改只作用于当前僵尸的阶段、入水标志、攻击矩形和动画；原始攻击／跳跃状态机继续执行。

- 海豚行走阶段 `33` 转为骑乘 `35`，遇植物仍执行原跳跃 `36`，结束进入泳行 `37`。到脑子范围时仍骑乘的海豚改为泳行，恢复普通攻击矩形。
- 潜水行走 `39` 转为潜游 `3B`，保留原上浮 `3C`、啃食 `3D` 和下潜流程。
- 我是僵尸中跳过左右池边“出水上岸”分支，直到正常离场。旧行走状态仍有脑子目标兼容钩子。
- 跳跳的脑子判断插在死亡／冰冻／黄油／跳跃阶段／烟囱检查之后，调用原 PogoBreak，保留落地与啃食节奏。
- 冰火球使用球自身 X 与 `mFireballRow`，不是僵王的坐标。碰撞参考点 `X+75<=20`，且球仍存在。辣椒使用爆炸僵尸所在行。二者检查已压毁状态，避免重复加分。

## 启动签名

目录中的 Steam `partner.xml` 和签名与 `main.pak` 的旧版配套文件不同。资源读取可经 PAK，签名读取则可能直接经磁盘，混用会报错。安装器只将 PAK 内已存在的配套两文件提取到磁盘，保留 Steam 文件备份；不重签文件、不修改签名验证代码。

## 补丁封装

输入 EXE 全文件 SHA-256 锁定。追加只读可执行 `.izfix` 节，不改 gdi42.dll。更新 PE 节数量、SizeOfImage、SizeOfCode、校验和，取消已失效的 Authenticode 目录引用（保留原字节以便还原）。未使用的下一节表槽原有 `ax!TQE` 标记，仅在整个输入完全匹配时使用。

差分包不包含完整 EXE。反向操作还原全部原始字节与文件长度，并重新核对散列。任何陌生 EXE 或伙伴配置都会被拒绝覆盖。
