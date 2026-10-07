# assets 目录说明

本目录用于存放从理光 GR II 固件中提取的原始画面资源（`.brp` 文件）。

这些资源是理光（Ricoh）的版权/商标内容，**不随仓库分发**。如需在 Web 工具里预览原始画面，请自行提取：

```bash
# 1. 用公开工具 ricohdec 解密固件，得到明文 b01firm6.bin
#    （工具地址见仓库根目录 README）

# 2. 把明文固件放到 ../tools/ricohdec/b01firm6.bin

# 3. 提取原始画面到本目录
cd .. && python3 tools/gr2boot.py extract --outdir web-tool/assets
```

提取后，本目录会得到 `dvf_TDSt.brp`（开机画面）、`dvf_key.brp`（机身线稿图）等文件，Web 工具即可显示原始画面预览。

> 不提取原始资源也不影响核心功能：直接导入你自己的图片即可转换并生成替换文件。
