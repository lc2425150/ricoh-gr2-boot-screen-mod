#!/usr/bin/env python3
"""
GR II 开机画面替换工具包
========================

针对理光 GR II（固件 rg2_v003）更换开机启动画面的完整工具链。

原理
----
GR II 的开机启动画面是资源文件 ``A:/img/dvf_TDSt.brp``，位于固件镜像
``b01firm6.bin`` 内。它是**未压缩的原始帧缓冲**：

    640 x 480 像素 x 2 字节/像素 = 614,400 字节
    像素格式 = RGB565，**大端**（big-endian，ARM 原生字节序）

因为是等长定长资源，替换时**不需要改动目录表的 offset 与 size 字段**，
只需把新像素原位写入，再重新做容器加密即可。

用法
----
    # 1. 解出资源 + 转成 PNG 供查看/编辑
    python3 gr2boot.py extract

    # 2. 把编辑好的 PNG 转回 brp 并回灌镜像
    python3 gr2boot.py repack --png 我的开机画面.png

    # 3. 重新打包成可写入 SD 卡的 rg2_vXXX.frm
    python3 gr2boot.py frm --out rg2_v003_custom.frm

    # 全部命令
    python3 gr2boot.py info
"""

import argparse
import hashlib
import struct
import sys
from pathlib import Path

from PIL import Image

# ── 常量 ────────────────────────────────────────────────────────────
W, H, BPP = 640, 480, 2
FB_SIZE = W * H * BPP                      # 614400
TARGET = "A:/img/dvf_TDSt.brp"              # 开机启动画面
EXTRA = ["A:/img/dvf_key.brp", "A:/img/dvf_mark.brp", "A:/img/dvf_PBWB.brp"]

# 理光 UNITY FILE 容器与块加密参数
HEADER_SIZE = 2048
ENTRY_SIZE = 64
BLOCK_SIZE = 512
BLOCK_KEY = 0xF8E69612
BLOCK_KEY_DIFF = 0xBE39B193
MAGIC = b"UNITY FILE V1.10 / RICOH COMPANY"

HERE = Path(__file__).resolve().parent
BD = HERE / "ricohdec"                     # 解码后的明文载荷目录


# ── 像素转换 ────────────────────────────────────────────────────────
def be565_to_rgb(v):
    """RGB565 大端 16 位 -> (r,g,b) 0..255"""
    return (((v >> 11) & 0x1F) * 255 // 31,
            ((v >> 5) & 0x3F) * 255 // 63,
            (v & 0x1F) * 255 // 31)


def rgb_to_be565(r, g, b):
    """(r,g,b) 0..255 -> RGB565 大端 16 位"""
    return (((r * 31 + 127) // 255) << 11
            | ((g * 63 + 127) // 255) << 5
            | ((b * 31 + 127) // 255))


def fb_to_png(fb, path):
    """帧缓冲 -> PNG（仅用于查看，勿当母版）"""
    px = struct.unpack(">" + "H" * (W * H), fb[:FB_SIZE])
    im = Image.new("RGB", (W, H))
    im.putdata([be565_to_rgb(v) for v in px])
    im.save(path)
    return im


def png_to_fb(path):
    """PNG -> 帧缓冲。要求恰好 640x480，会做最近邻缩放以防尺寸不符。"""
    im = Image.open(path).convert("RGB")
    if im.size != (W, H):
        print(f"  提示：原图 {im.size}，已缩放到 {(W, H)}")
        im = im.resize((W, H), Image.LANCZOS)
    out = bytearray()
    for r, g, b in im.get_flattened_data() if hasattr(im, "get_flattened_data") else im.getdata():
        out += struct.pack(">H", rgb_to_be565(r, g, b))
    assert len(out) == FB_SIZE, len(out)
    return bytes(out)


# ── 镜像内 A: 盘目录表 ─────────────────────────────────────────────
def load_entries(f6):
    """解析 b01firm6.bin 内 0x786000 处的 121 条 64 字节目录。"""
    ENT = 0x786000
    out = {}
    for i in range(121):
        o = ENT + i * 64
        name = f6[o:o + 32].split(b"\x00")[0].decode("latin1")
        img_off, size = struct.unpack(">II", f6[o + 32:o + 40])
        out[name] = dict(idx=i, off=img_off, size=size, table=o)
    return out


# ── 容器块加密 ─────────────────────────────────────────────────────
def xor_encrypt(data):
    """按 512 字节块做 32 位字 XOR 加密（与 ricohdec 解密对称）。"""
    out = bytearray(data)
    key = BLOCK_KEY
    for blk in range(0, len(out), BLOCK_SIZE):
        for w in range(blk, min(blk + BLOCK_SIZE, len(out)), 4):
            if w + 4 <= len(out):
                out[w:w + 4] = struct.pack(">I", struct.unpack(">I", out[w:w + 4])[0] ^ key)
        key = (key + BLOCK_KEY_DIFF) & 0xFFFFFFFF
    return bytes(out)


def xor_decrypt(data):
    return xor_encrypt(data)          # XOR 对合


# ── 子命令 ─────────────────────────────────────────────────────────
def cmd_info(args):
    f6 = (BD / "b01firm6.bin").read_bytes()
    ents = load_entries(f6)
    print("=" * 78)
    print("GR II 开机画面资源信息")
    print("=" * 78)
    for name in [TARGET] + EXTRA:
        e = ents[name]
        tag = "  <== 开机启动画面" if name == TARGET else ""
        print(f"  {name:22s} idx={e['idx']:3d}  off=0x{e['off']:06x}  "
              f"size={e['size']:>9,d}{tag}")
    print()
    t = ents[TARGET]
    print(f"  帧缓冲规格：{W} x {H} x {BPP}B = {FB_SIZE:,} 字节")
    print(f"  实际大小  ：{t['size']:,} 字节  "
          f"{'✓ 精确匹配' if t['size'] == FB_SIZE else '✗ 不匹配！'}")
    print(f"  像素格式  ：RGB565 大端（ARM 原生）")
    print(f"  压缩      ：无，原始帧缓冲")
    print()
    print("  目录表条目固定为 64 字节：")
    print("    char name[32] / u32 image_offset(BE) / u32 size(BE)")
    print("    / u8 ident[12] / u32 flags(恒为 0x01000000) / u8 reserved[8]")
    print("  等长替换时 offset 与 size 均无需改动。")


def cmd_extract(args):
    f6 = (BD / "b01firm6.bin").read_bytes()
    ents = load_entries(f6)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    for name in [TARGET] + EXTRA:
        e = ents[name]
        blob = f6[e["off"]:e["off"] + e["size"]]
        base = name.split("/")[-1][:-4]
        (outdir / f"{base}.brp").write_bytes(blob)
        print(f"  导出 {name:22s} {e['size']:>9,d} B  ->  {outdir}/{base}.brp")
        if e["size"] == FB_SIZE:
            fb_to_png(blob, outdir / f"{base}.png")
            print(f"       同时渲染 PNG 供查看/编辑  ->  {outdir}/{base}.png")

    print()
    print("下一步：")
    print(f"  1) 编辑 {outdir}/dvf_TDSt.png（务必保持 640x480）")
    print(f"  2) python3 {Path(__file__).name} repack --png {outdir}/dvf_TDSt.png")


def cmd_repack(args):
    """把编辑好的 PNG 转回帧缓冲。

    默认产物 = **单个 .brp 文件**（路径 B 所需，放到 SD 卡即可）。
    仅当传入 --mirror 时才额外生成整镜像 .bin（路径 A 用，且有校验和风险）。
    """
    f6 = (BD / "b01firm6.bin").read_bytes()
    ents = load_entries(f6)
    t = ents[TARGET]
    new_fb = png_to_fb(args.png)

    if len(new_fb) != t["size"]:
        sys.exit(f"ABORT: 帧缓冲 {len(new_fb):,} B 与原资源 {t['size']:,} B 不等长")

    old = f6[t["off"]:t["off"] + t["size"]]
    diff = sum(1 for a, b in zip(old, new_fb) if a != b)
    print(f"  帧缓冲 {len(new_fb):,} B  (等长 ✓，目录表无需改动)")
    print(f"  变化字节 {diff:,} / {t['size']:,}  ({diff / t['size'] * 100:.1f}%)")
    print(f"  原 sha256 {hashlib.sha256(old).hexdigest()[:32]}…")
    print(f"  新 sha256 {hashlib.sha256(new_fb).hexdigest()[:32]}…")

    # ── 主产物：单个 brp（路径 B） ─────────────────────────────
    brp_dst = Path(args.out) if args.out else (HERE / "bootimg" / "dvf_TDSt.brp")
    brp_dst.parent.mkdir(parents=True, exist_ok=True)
    brp_dst.write_bytes(new_fb)
    print(f"\n  ✅ 已写出画面文件 {brp_dst}  ({len(new_fb):,} B)")
    print(f"\n  【路径 B · 推荐】把这个文件放到 SD 卡根目录：")
    print(f"     {brp_dst}")
    print(f"     再把 Startup.ttl 也放到 SD 卡根目录，正常开机即可。")
    print(f"     详见 gr2-analysis/GRII开机画面操作手册.md")

    # ── 可选：整镜像（路径 A，有校验和风险） ──────────────────────
    if args.mirror:
        img = bytearray(f6)
        img[t["off"]:t["off"] + t["size"]] = new_fb
        m_dst = HERE / "b01firm6_custom.bin"
        m_dst.write_bytes(img)
        print(f"\n  ⚠ 已额外生成整镜像 {m_dst}  ({len(img):,} B)")
        print(f"    这只用于路径 A（刷固件），**有校验和风险，不要直接刷**。")
        print(f"    下一步：python3 {Path(__file__).name} frm --img {m_dst}")


def cmd_frm(args):
    """把自定义 b01firm6.bin 重新打包成 .frm。

    ⚠ 安全警告：GR II 的更新头含 nUpdateCsum 校验和字段
    （b01firm8.bin 内可见 nUpdateCsum / bCompareCsum / bExecVerify / "%s is Broken."）。
    开机画面改动落在该校验覆盖范围内，而本工具**尚未重算校验和**。
    默认只做「演练输出」，不写成可直接刷入的文件；需显式 --force 才产出成品。
    """
    f6src = Path(args.img)
    f6 = f6src.read_bytes()
    src = (BD / "rg2_v003.frm").read_bytes()

    # 定位 b01firm6 在 .frm 中的载荷段：按长度与内容定位
    plain6 = (BD / "b01firm6.bin").read_bytes()
    enc6 = xor_encrypt(plain6)
    pos = src.find(enc6[:4096])
    if pos < 0:
        sys.exit("ABORT: 未能在 .frm 中定位 b01firm6 载荷段")
    print(f"  在 .frm 中定位 b01firm6 载荷：offset 0x{pos:06x}")
    print(f"  载荷长度 {len(plain6):,} B")

    if len(f6) != len(plain6):
        sys.exit("ABORT: 自定义镜像长度与原镜像不同，需重建容器目录")

    changed = sum(1 for a, b in zip(f6, plain6) if a != b)
    out = bytearray(src)
    out[pos:pos + len(f6)] = xor_encrypt(f6)
    dst = Path(args.out) if args.out else HERE / "rg2_v003_custom.frm"

    if changed and not args.force:
        dst.write_bytes(out)          # 仍写出，便于离线核对结构
        print(f"  【演练模式】已写出 {dst}  ({len(out):,} B)")
        print(f"  改动字节 {changed:,}，新 sha256 {hashlib.sha256(out).hexdigest()}")
        print()
        print("  ⚠ 该文件【不可直接刷入】")
        print("    原因：GR II 更新头含 nUpdateCsum 校验和，本工具未重算。")
        print("         刷入可能失败，最坏情况变砖。")
        print()
        print("  刷入前必须完成：")
        print("    1) 定位 nUpdateCsum 在 .frm 中的偏移与算法（用改单字节探针法反推）")
        print("    2) 重算并回填该校验和")
        print("    3) 用【未修改的原版固件】先验证一次刷写流程，确认回滚可行")
        print()
        print("  确认以上三项已完成、确实要产出可刷文件时，加 --force 重跑。")
        return

    dst.write_bytes(out)
    print(f"  已写出 {dst}  ({len(out):,} B)")
    print(f"  改动字节 {changed:,}，新 sha256 {hashlib.sha256(out).hexdigest()}")
    if changed:
        print()
        print("  ⚠ 你已用 --force 强制产出。请自行确认校验和已正确重算，否则可能变砖。")


# ── 入口 ───────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="理光 GR II 开机画面替换工具包",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("info", help="显示资源信息").set_defaults(func=cmd_info)

    p = sub.add_parser("extract", help="解出 brp 并渲染 PNG")
    p.add_argument("--outdir", default="bootimg")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("repack", help="PNG 转 brp（路径 B 产物）")
    p.add_argument("--png", required=True)
    p.add_argument("--out", default=None)
    p.add_argument("--mirror", action="store_true",
                   help="额外生成整镜像 .bin（路径 A 用，有校验和风险）")
    p.set_defaults(func=cmd_repack)

    p = sub.add_parser("frm", help="自定义镜像重新打包为 frm（默认演练模式）")
    p.add_argument("--img", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--force", action="store_true",
                   help="强制产出可刷文件（须自行确认校验和已重算）")
    p.set_defaults(func=cmd_frm)

    args = ap.parse_args()
    if not getattr(args, "func", None):
        ap.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
