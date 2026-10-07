# 理光 GR II 自定义开机画面 — 固件逆向分析与双路径方案

> 起因：[radium-wang/ricoh-gr4-firmware-analysis-and-feature-expansion](https://github.com/radium-wang/ricoh-gr4-firmware-analysis-and-feature-expansion) 开源后，验证其思路能否用于 GR II（固件 `rg2_v003`）。
> 结论：**GR IV 项目的容器格式/产品 ID/DEVELOP.MOD 在 GR II 上均不存在，不能直接套用**；但 GR II 固件内置了同样的 **Tera Term TTL 宏引擎**（81 条命令），由此推导出两条更换开机画面的路径。

---

## 一、两条方案总览

| | 路径 A：刷自定义固件 | 路径 B：SD 卡 Startup.ttl + filecopy |
|---|---|---|
| 原理 | 解密容器 → 原位替换 `A:/img/dvf_TDSt.brp` → 重加密 → 打包 `.frm` 刷入 | 固件开机时自动执行 `W*:/Startup.ttl`，脚本把 SD 卡上的新画面 `filecopy` 进机内 A: 盘 |
| 文件层成熟度 | ✅ 成熟（解密/替换/重加密全链路字节级验证通过） | ✅ 成熟（解包→改图→回灌 614,400 字节逐字节验证通过） |
| 执行安全性 | ❌ **当前不可安全执行** | ✅ 最坏情况只是画面异常，**拔卡即回滚** |
| 阻塞点 | `nUpdateCsum` 校验和未重算 → **刷入可能变砖** | 无阻塞；仅剩真机首步验证 |
| 判定 | **原理可行，暂不建议执行** | **可行且安全（静态分析层面），待真机首步确认** |

## 二、路径 B（推荐）：SD 卡 Startup.ttl

### 已确证的证据链（全部来自固件静态分析，字节级）

1. **作业调度表**（`b01firm8.bin` @ `0x0EF488`，105 项 8 字节 `{name,handler}`）：
   - `job0 = "refresh"`（handler `0xA00E879B`）是开机阶段推进器
   - `job1 = "JOBID_BOOT"`、`job9 = "JOBID_SHUTDOWN"`
2. **门控条件**：`boot.isLoaded[CORE] && isLoaded[BE0] && isLoaded[BE]` 三条件全非零后执行：
   ```
   sprintf("script %s", "W*:/Startup.ttl")
   ```
   字面量池 @ `0xC9140` 相邻存放：`W*:/Startup.ttl` → `*:` → `script %s`（本次复验再次确认）。
3. **盘符表** = `I A B C D E H`；`H:` = SD 卡（证据：`H:/DCIM/%03dRICOH/R001%04d.JPG`、`H:/RADJ/%s/Adjust.ttl`、`%c:/MISC/NOCHANGE.SD`）。
4. **TTL 引擎**：81 条命令含 `filecopy / filestat / fileopen / getdir / sprintf / dispstr / sendln inputstr` 等，语法范本 = 机内原厂 `A:/update.ttl`（CRLF、`:label`、`call`、`if/then/endif`）。
5. **开机画面资源**：`A:/img/dvf_TDSt.brp` = **640×480×2 = 614,400 字节，未压缩 RGB565 大端帧缓冲**（目录表 idx=4 @ `0x139C00`，规格与实际大小精确匹配）。

### 操作步骤（详见 `docs/GRII开机画面操作手册.md`）

1. 把 `sd-card/Startup.ttl` + `sd-card/dvf_TDSt.brp` 拷到 SD 卡根目录
2. 先只启用「第一步最小验证」段（`dispstr STARTUP_TTL_RUNNING`），确认脚本被执行
3. 确认后启用 `:Main` 段（`filecopy A:/img/dvf_TDSt.brp H:/dvf_TDSt.brp`）
4. 回滚 = 拔卡，或用原始 `dvf_TDSt.brp`（本地备份 sha256 前缀 `cc3b8256…`）再覆盖一次

### 剩余真机验证项（诚实声明）

- 三个 `isLoaded` 门控在带卡开机时是否全过 —— 需真机确认
- `W` 前缀语义（推测为可写态）；若只读，改走 `A:/update.ttl` 路径（脚本内有备选段）
- `filecopy` 参数顺序（按 Tera Term 惯例假设为 `<目标> <源>`）
- **以上均未在真机验证过，第一步必须先用 `dispstr` 验证脚本执行**

## 三、路径 A：刷自定义固件（暂不推荐）

- 容器层已完全打通：UNITY FILE V1.10 头 + 512 字节块 XOR（初值 `0xF8E69612`、步进 `0xBE39B193`），解密/加密对称，等长替换无需改目录表
- **阻塞点**：`.frm` 更新头含校验字段 `nUpdateCsum / bCompareCsum / bExecVerify / bCheckHeader / bCheckRomSize / "%s is Broken."`（@ `0x36F6D` 起），且确认**不是密码学签名**——是求和类校验，但目前未定位其偏移与算法
- 固件更新流程会执行 `bExecVerify`，校验不过 = 刷入失败，最坏变砖
- 工具 `tools/gr2boot.py frm` 默认「演练模式」，无 `--force` 不产出可刷文件
- **在完成以下三项前不要刷**：① 单字节探针法定位 `nUpdateCsum` 偏移与算法；② 重算回填；③ 先用未修改的原版固件验证一次刷写与回滚流程

## 四、目录结构

```
├── README.md
├── docs/
│   ├── GR2-固件可行性分析报告.html     # 十章完整逆向报告（离线版；最新版在资料库云端页）
│   ├── GRII开机画面操作手册.md         # 6 步操作手册 + 排障表 + 回滚
│   └── GRII开机画面替换手册.md         # 早期手册（含第〇节安全勘误）
├── tools/
│   └── gr2boot.py                     # info/extract/repack/frm 四合一工具（Python3 + PIL）
├── sd-card/
│   ├── Startup.ttl                    # 带最小验证段 + 换图段 + 备选诊断段
│   └── dvf_TDSt.brp                   # 自定义开机画面（614,400 B，来自 example/ 图）
└── example/
    └── 我的开机画面.png                # 640×480 示例图（深蓝底金字 MY GR II）
```

## 五、重要声明

- 本项目所有结论来自**离线静态分析**；真机验证项见上文，请按「验证优先」流程操作
- 固件版权归理光（Ricoh）所有；本仓库**不含**任何固件二进制与提取出的原厂资源，原厂 `dvf_TDSt.brp` 备份仅保留在本地
- 请勿修改 `dvf_mark.brp`（FCC/CE/IC 认证标签），否则设备不再符合原认证声明
- 参考项目：[radium-wang/ricoh-gr4-firmware-analysis-and-feature-expansion](https://github.com/radium-wang/ricoh-gr4-firmware-analysis-and-feature-expansion)、解密器 [jokob/ricohdec](https://github.com/jokob/ricohdec)
