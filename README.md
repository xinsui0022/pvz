# 我是僵尸：随机僵尸补丁修复

针对用户提供的「叔基丁路障随机变身版」PvZ **1.0.0.1051** 制作的二进制差分补丁。保留原来的路障死亡随机变身机制。仓库只提供补丁、可审查的 x86 汇编源码、安装工具及测试，不分发完整游戏或存档。

## 已实现

| 问题 | 修改后的行为 |
| --- | --- |
| 僵王死亡／换关崩溃 | 修正原补丁传错对象指针的问题；退出时清理自己的冰火球与冰冻效果，不连带清除其他僵尸。保留真正僵王关卡的原流程。 |
| 投篮伤害不掉阳光、阳光掉完植物还在 | 按实际损失血量结算阳光；血量恰好为 0 也立即死亡。 |
| 豌豆／机枪僵尸不掉阳光 | 与投篮共用伤害结算，支持混合攻击，避免漏发或重复发放。 |
| 小丑、辣椒炸向日葵不掉阳光 | 植物死亡前结算剩余阳光。 |
| 海豚／潜水僵尸的陆地行为 | 在我是僵尸中，把这两种僵尸自身设为水中状态；海豚保留原版越过植物的跳跃，随后游泳；潜水僵尸保持潜水、遇到植物上浮啃食。地图本身不改成水池。 |
| 海豚／潜水僵尸不吃脑子 | 保留水中状态到达脑子；海豚仍骑乘时会先失去海豚，再接入正常啃食。兼容旧存档中的陆地行走状态。 |
| 跳跳僵尸不吃脑子 | 到达有效脑子目标时调用原版失去跳杆流程，落地后正常啃食。 |
| 冰火球／辣椒不消灭脑子 | 冰火球到达脑子的位置时压毁同一行脑子；辣椒爆炸消灭同一行脑子。已经消灭的脑子不重复计分。 |
| 僵王概率 | 我是僵尸中从 1/33 调为 **3/35 = 8.57%**；其他每种僵尸均为 1/35，其他模式保留原分布。 |
| Steam 启动 Signature check failed | 从用户已有的 `main.pak` 提取配套的 `partner.xml` 和 `.sig`，替换不匹配的 Steam 配置。原配置备份；不修改签名检查或 Steam 设置。 |
| 界面底部文字 | 改为「由心都灬碎了提供，QQ：3389141」，保留原有位置与绘制方式。 |

除启动配置及空指针防御外，新增玩法限定于「我是僵尸」系列关卡（61–70，包括无尽）。

## 安装与还原

关闭游戏，把仓库中的文件放进该修改版游戏目录。有 Python 3 即可安装，不需要安装分析依赖：

```powershell
python tools/patch_game.py --check
python tools/patch_game.py
```

工具校验整个 EXE 的 SHA-256，拒绝修改其他版本；支持从本次工作中安装过的第一版补丁升级。原始版本备份在 `backups/PlantsVsZombies.original.exe`，第一版补丁备份在 `backups/PlantsVsZombies.v1.exe`，Steam 原配置在 `backups/steam-partner/`。

恢复到用户最初提供的修改版程序与 Steam 配置：

```powershell
python tools/patch_game.py --restore
```

此处“原始版本”指修复前的随机变身修改版，并不是 Steam 官方原版。Steam 验证游戏完整性可能覆盖修改后的 EXE、配置或资源。

## 验证与当前限制

自动化测试执行真正的 x86 补丁指令，已覆盖原崩溃复现、修复后的栈与寄存器、浮点状态、伤害边界、阳光总数、模式限制、水生状态切换、脑子单次计分、精确随机权重及补丁逐字节还原。渲染、声音及部分引擎调用由测试桩模拟。

**用户已确认启动签名弹窗消失；尚未完成完整游戏内回归测试**。桌面操作的自动审批被账户用量限制拦截。测试通过不代表已验证所有动画、地图或长时间无尽换关组合。特别需要试玩水生僵尸的跳跃／潜水视觉效果与多个僵王同时在场的换关情况。实测清单见 [docs/validation.md](docs/validation.md)。

## 开发与重建

```powershell
python -m pip install --target .tools -r requirements.txt
python tools/build_patch.py
python -m unittest discover -s tests -v
```

重建读取本地备份 EXE，输出候选程序到 `backups/PlantsVsZombies.patched.exe`，并生成 `patches/izombie-fixes.json` 与地址清单。候选程序不会自动替换游戏。输入散列与输出散列见 [patches/manifest.json](patches/manifest.json)。

技术原因与 ABI 说明见 [docs/analysis.md](docs/analysis.md)。参考函数来自 [PlantsVsZombies-decompilation](https://github.com/ruslan831/PlantsVsZombies-decompilation) 并逐项对照本地可执行文件；参考项目仅用于阅读，没有编译或上传其内容。
