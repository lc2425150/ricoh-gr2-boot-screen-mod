# GR II 自定义开机画面 · 操作手册（路径 B）

> **结论：可以做到，且不碰固件、无变砖风险。**
> 全程只需一台电脑 + 一张 SD 卡，不需要拆机、不需要刷固件。

---

## 〇、开工前必须知道的三件事

| 项 | 说明 |
|---|---|
| **会不会变砖** | **不会**。最坏情况只是开机画面不对，相机其他功能正常。拔卡即恢复。 |
| **要改哪些文件** | SD 卡根目录加一个 `Startup.ttl`，可选再放一个 `dvf_TDSt.brp` |
| **有没有实机验证过** | **没有**。全部结论来自固件静态分析。第 1 步验证脚本就是用来确认这条路走得通。 |

---

## 一、准备

### 1.1 工具（已在本地备好）

```
gr2-analysis/out/
├── gr2boot.py              画面转换工具
├── bootimg/
│   ├── dvf_TDSt.png        原始开机画面（640×480，可直接编辑）
│   ├── dvf_TDSt_原始.brp    原始备份（回滚用，请勿删除）
│   └── dvf_TDSt_替换样例.png  示例（黑底绿框 GR II CUSTOM）
└── ricohdec/               解码后的明文固件（分析用，你不需要动）

gr2-analysis/Startup.ttl    要放到 SD 卡的脚本
```

### 1.2 SD 卡

- 容量任意（脚本 + 614 KB 画面，1 GB 都够）
- 格式 **FAT32**（相机才能识别）
- 卡内**根目录**（不是子文件夹）放脚本

---

## 二、制作开机画面

### 2.1 解出原始画面

```bash
cd gr2-analysis/out
/Users/achen/.workbuddy/binaries/python/envs/default/bin/python gr2boot.py extract
```

生成 `bootimg/dvf_TDSt.png`（640×480 PNG）。这就是相机开机时显示的画面。

### 2.2 编辑画面

用任意图片编辑器打开它：

| 要求 | 值 |
|---|---|
| 尺寸 | **必须是 640×480**，工具会自动缩放但不建议 |
| 色彩 | RGB，工具会自动转 RGB565 |
| 格式 | PNG |

> **建议**：从原图出发修改，保留 GR 原有的留白和文字位置，观感最协调。

### 2.3 转回 brp 并导出

```bash
/Users/achen/.workbuddy/binaries/python/envs/default/bin/python gr2boot.py repack \
    --png bootimg/我的开机画面.png --out bootimg/dvf_TDSt.brp
```

得到 `bootimg/dvf_TDSt.brp`，**必须是 614,400 字节**。

---

## 三、写入 SD 卡

```
SD 卡根目录/
├── Startup.ttl          ← 脚本
└── dvf_TDSt.brp         ← 你的新画面（第二步才需要）
```

> ⚠ 文件名必须完全一致：脚本是 `Startup.ttl`（大写 S），画面是 `dvf_TDSt.brp`。
> macOS 会自动加 `.txt` 后缀，拷完记得在 Finder 里「显示扩展名」确认，或用命令行：
> ```bash
> cp ~/Desktop/Startup.ttl /Volumes/<卡名>/
> ls -l /Volumes/<卡名>/Startup.ttl   # 确认没有 .txt
> ```

---

## 四、第一次测试：只验证脚本会被执行

**这一步是整个方案的关键。** 不要跳过。

SD 卡上只放 `Startup.ttl`（用下面这个版本，脚本里只有两行有效代码）：

```
sprintf "dispstr STARTUP_TTL_RUNNING"
sendln inputstr
end
```

然后：

1. 相机装上这张卡，**正常开机**（不是 USB 模式）
2. 看屏幕有没有出现 `STARTUP_TTL_RUNNING`

### 结果对照

| 现象 | 含义 | 下一步 |
|---|---|---|
| **看到文字** | ✅ 路径 B 完全成立 | 进第五节做换图 |
| **没反应** | 门控未过 / 卡未挂载 / 语法问题 | 见 6.1 排查 |

---

## 五、正式换图

确认第四步成功后：

1. 编辑 `Startup.ttl`，把第一段的验证代码**注释掉**（前面加 `;`）
2. 把第二段 `:Main` 那块的注释**去掉**（删掉 `/*` 和 `*/`）
3. 确认 SD 卡根目录有 `dvf_TDSt.brp`
4. 正常开机

预期：屏幕闪一下 `PATCHING BOOT IMAGE` → `DONE`，然后显示你的新开机画面。

### 为什么用 `filecopy` 而不是别的

`filecopy` 是 GR IV 仓库换图时用的**同一个命令**。它把 SD 卡上的文件复制到机内 `A:/img/`，
覆盖原始 `dvf_TDSt.brp`。因为是**等长覆盖**（都是 614,400 字节），
不涉及目录表改动，也不需要任何校验和重算。

---

## 六、排查

### 6.1 脚本没被执行

按可能性排序：

| 可能原因 | 怎么确认 | 怎么办 |
|---|---|---|
| SD 卡没被识别 | 相机菜单里能否看到卡？能否正常拍照存到卡上？ | 先解决卡的问题。相机要求 FAT32 |
| 文件被改名 | 用 `ls` 确认没有 `Startup.ttl.txt` | 改回正确名字 |
| 卡没插紧 / 是伪卡 | 用读卡器在电脑上验证卡能正常读写 | 换一张正常的卡 |
| 门控未过 | 三个 `isLoaded` 条件涉及 `SECT_CORE / SECT_BE0 / SECT_BE` | 属正常开机流程，理论上必过；若始终不行需进一步分析 |
| 语法错误 | 相机屏幕上是否闪出 `script ... error: ...` | 按提示改；常见是引号或分号问题 |

### 6.2 filecopy 报错

脚本里的备用方案会逐步定位：

```
sprintf "filestat H:/dvf_TDSt.brp"    ; 源文件是否可见
sprintf "getdir A:/img"              ; 目标目录是否存在
```

若报权限/只读错误，说明内部 A: 盘受保护 —— 这时改走 `A:/update.ttl` 那条路径
（它在 `fsys stop` 之前的可写状态执行）。这一步需要更多分析，我在报告里标了待确认。

---

## 七、回滚

### 方式一：拔卡（最快）

把 SD 卡拔掉，相机自动使用机内原始资源，开机画面恢复正常。**开机画面不会被永久改动**，
只有卡插着时才会被覆盖。

### 方式二：用备份覆盖回去

把 `bootimg/dvf_TDSt_原始.brp` 复制到 SD 卡、改名成 `dvf_TDSt.brp`，
再开机一次即可恢复。

---

## 八、注意事项

> ⚠ **不要动 `dvf_mark.brp`** —— 那是机身背面的 FCC / CE / IC 认证标签
> （TRA 注册号、RoHS 标志）。改动它会让设备不再符合原认证声明，
> 也可能影响出口销售。仅覆盖 `dvf_TDSt.brp`（开机画面）即可。

> ⚠ 只用 TTL 脚本覆盖资源，**不要试图改固件本身**。固件有 `nUpdateCsum` 校验和
> （详见分析报告 9.8 节），改动固件有变砖风险；改资源文件则完全安全。

---

## 九、想深入的话

分析报告第 10 章记录了完整的静态分析证据链：

- `ctx+0x68/0x78/0x7c` = `boot.isLoaded[]` 的字段名来自断言字符串
- `script %s` 与 `W*:/Startup.ttl` 的字面量池位置
- SD 卡盘符 = `H:` 的三条证据
- 附带还原出 39 个源文件的完整代码树（项目代号 **KB567**）

云端报告：https://www.workbuddy.cn/space/d/tXcEZ0g6ZPUeF0f7PRvD4F
