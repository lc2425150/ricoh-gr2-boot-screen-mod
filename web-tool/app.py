#!/usr/bin/env python3
"""
GR II 画面定制工具 —— 本地后端服务
====================================

针对理光 GR II（固件 rg2_v003）的开机画面 / 机身线稿图替换，
提供本地浏览器 Web 界面。

原理（由上一轮固件静态分析确证）：
    GR II 的开机画面是资源文件 A:/img/dvf_TDSt.brp，位于固件镜像
    b01firm6.bin 内，是未压缩的原始帧缓冲：
        640 x 480 x 2 字节/像素 = 614,400 字节
        像素格式 = RGB565 大端（ARM 原生字节序）
    因为是等长定长资源，替换时无需改动目录表，配合 SD 卡根目录的
    Startup.ttl（filecopy 覆盖）即可，全程不碰固件、无变砖风险。

用法：
    python3 app.py [--port 8787]
    然后浏览器打开 http://127.0.0.1:8787
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import struct
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from PIL import Image

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
STATIC = HERE / "static"

# ── 资源清单 ────────────────────────────────────────────────────────────
# 每项：机内路径、显示名、宽、高、字节/像素、说明
RESOURCES = [
    {
        "key": "dvf_TDSt.brp",
        "internal": "A:/img/dvf_TDSt.brp",
        "label": "开机画面",
        "width": 640,
        "height": 480,
        "bpp": 2,
        "note": "开机启动画面（蓝底 RICOH）。可安全替换。",
        "editable": True,
    },
    {
        "key": "dvf_key.brp",
        "internal": "A:/img/dvf_key.brp",
        "label": "机身线稿图",
        "width": 640,
        "height": 480,
        "bpp": 2,
        "note": "机身线稿图（相机外形示意图）。可安全替换。",
        "editable": True,
    },
    {
        "key": "dvf_mark.brp",
        "internal": "A:/img/dvf_mark.brp",
        "label": "背面铭牌",
        "width": 640,
        "height": 480,
        "bpp": 2,
        "note": "背面认证标签（FCC/CE/IC/RoHS）。改动触及合规，工具默认禁止编辑。",
        "editable": False,
    },
    {
        "key": "dvf_PBWB.brp",
        "internal": "A:/img/dvf_PBWB.brp",
        "label": "PBWB 资源",
        "width": 0,
        "height": 0,
        "bpp": 2,
        "note": "53,792 字节，尺寸/用途待确认，暂不提供编辑。",
        "editable": False,
    },
]


# ── RGB565 转换（与 gr2boot.py 一致，已验证逐字节往返无损）──────────────
def be565_to_rgb(v: int) -> tuple[int, int, int]:
    return (
        ((v >> 11) & 0x1F) * 255 // 31,
        ((v >> 5) & 0x3F) * 255 // 63,
        (v & 0x1F) * 255 // 31,
    )


def rgb_to_be565(r: int, g: int, b: int) -> int:
    return (
        ((r * 31 + 127) // 255) << 11
        | ((g * 63 + 127) // 255) << 5
        | ((b * 31 + 127) // 255)
    )


def fb_to_png_bytes(fb: bytes, w: int, h: int) -> bytes:
    px = struct.unpack(">" + "H" * (w * h), fb[: w * h * 2])
    im = Image.new("RGB", (w, h))
    im.putdata([be565_to_rgb(v) for v in px])
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def image_bytes_to_fb(data: bytes, w: int, h: int) -> bytes:
    im = Image.open(io.BytesIO(data)).convert("RGB")
    if im.size != (w, h):
        im = im.resize((w, h), Image.LANCZOS)
    out = bytearray()
    for r, g, b in im.getdata():
        out += struct.pack(">H", rgb_to_be565(r, g, b))
    assert len(out) == w * h * 2, len(out)
    return bytes(out)


# ── Startup.ttl 生成 ────────────────────────────────────────────────────
def make_startup_ttl(target: str, internal: str) -> str:
    """生成 SD 卡根目录的 Startup.ttl，用 filecopy 覆盖机内资源。"""
    fn = target
    return f"""; ============================================================================
;  GR II 自定义画面 —— SD 卡 Startup.ttl 脚本（路径 B）
;  目标资源：{internal}
; ============================================================================
;
;  用法
;    1. 把本脚本与 {fn} 一起放到 SD 卡【根目录】
;    2. 相机正常开机（不要用 USB 模式），脚本会被自动执行
;
;  原理（已由固件静态分析确证）
;    · 开机 job0 在 isLoaded[CORE] && isLoaded[BE0] && isLoaded[BE] 满足后，
;      执行 sprintf("script %s", "W*:/Startup.ttl")
;    · "*:" 是通配符，匹配所有已挂载盘符；SD 卡盘符 = H:
;    · 因此卡根目录的 Startup.ttl 必然被执行
;
;  回滚：直接拔掉 SD 卡即可，相机恢复机内原始资源，无变砖风险。
; ============================================================================

; ---- 第 1 步：最小验证脚本（首次测试请只保留这一段，确认脚本被执行）----
sprintf "dispstr STARTUP_TTL_RUNNING"
sendln inputstr
end

; ============================================================================
;  第 2 步：正式换图脚本
;  （先确认第 1 步屏幕上能看到 STARTUP_TTL_RUNNING，再删掉上面 3 行，
;    并去掉下面每行开头的分号）
; ============================================================================
; sprintf "dispstr PATCHING BOOT IMAGE"
; sendln inputstr
;
; sprintf "filecopy H:/{fn} {internal}"
; sendln inputstr
;
; sprintf "fileclose"
; sendln inputstr
;
; sprintf "dispstr DONE"
; sendln inputstr
; end
;
; ----------------------------------------------------------------------------
;  注意事项
;    1. filecopy 参数个数/语义以 TTL 命令表为准；若报错，固件会输出
;       "script %s error: %s"，可据此调整。
;    2. 若 filecopy 后画面未变，可能 W 前缀为只读态，需改走 A:/update.ttl 路径。
;    3. 只覆盖目标资源，不要动 dvf_mark.brp（FCC/CE/IC 认证标签）。
; ----------------------------------------------------------------------------
"""


def _resource_by_key(key: str) -> dict | None:
    for r in RESOURCES:
        if r["key"] == key:
            return r
    return None


# ── HTTP 处理器 ─────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    server_version = "GR2Tool/1.0"

    # ---- 工具方法 ----
    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _static(self, path: str):
        if path in ("", "/"):
            path = "/index.html"
        fp = (STATIC / path.lstrip("/")).resolve()
        if not str(fp).startswith(str(STATIC)) or not fp.is_file():
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        body = fp.read_bytes()
        ctype = "text/html; charset=utf-8"
        if fp.suffix == ".js":
            ctype = "application/javascript; charset=utf-8"
        elif fp.suffix == ".css":
            ctype = "text/css; charset=utf-8"
        self._send(200, body, ctype)

    # ---- 路由 ----
    def do_GET(self):
        up = urlparse(self.path)
        if up.path.startswith("/api/"):
            self._api_get(up.path, parse_qs(up.query))
        else:
            self._static(up.path)

    def do_POST(self):
        up = urlparse(self.path)
        if up.path.startswith("/api/"):
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b""
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                self._send_json(400, {"error": "invalid JSON"})
                return
            self._api_post(up.path, payload)
        else:
            self._send(405, b"method not allowed", "text/plain; charset=utf-8")

    def _api_get(self, path: str, qs: dict):
        if path == "/api/resources":
            self._send_json(200, {"resources": RESOURCES})
            return
        if path == "/api/original":
            key = (qs.get("name") or [""])[0]
            r = _resource_by_key(key)
            if not r:
                self._send_json(404, {"error": "unknown resource"})
                return
            fp = ASSETS / key
            if not fp.is_file():
                self._send_json(404, {"error": "原始资源未提供，请用 tools/gr2boot.py extract 自提"})
                return
            fb = fp.read_bytes()
            png_b64 = ""
            if r["editable"] and r["width"] and r["height"]:
                png_b64 = base64.b64encode(
                    fb_to_png_bytes(fb, r["width"], r["height"])).decode("ascii")
            self._send_json(200, {
                "key": key,
                "brp_base64": base64.b64encode(fb).decode("ascii"),
                "png_base64": png_b64,
                "size": len(fb),
                **{k: r[k] for k in ("label", "width", "height", "bpp", "note")},
            })
            return
        if path == "/api/startup-ttl":
            key = (qs.get("name") or [""])[0]
            r = _resource_by_key(key)
            if not r:
                self._send_json(404, {"error": "unknown resource"})
                return
            self._send_json(200, {"ttl": make_startup_ttl(r["key"], r["internal"])})
            return
        self._send_json(404, {"error": "unknown api"})

    def _api_post(self, path: str, payload: dict):
        if path == "/api/convert":
            key = payload.get("target", "")
            img_b64 = payload.get("image_base64", "")
            r = _resource_by_key(key)
            if not r:
                self._send_json(400, {"error": "unknown target"})
                return
            if not r["editable"] or not r["width"] or not r["height"]:
                self._send_json(400, {"error": "this resource is not editable"})
                return
            if not img_b64:
                self._send_json(400, {"error": "missing image_base64"})
                return
            # 兼容 data URL 前缀
            if "," in img_b64 and img_b64.startswith("data:"):
                img_b64 = img_b64.split(",", 1)[1]
            try:
                raw_img = base64.b64decode(img_b64)
            except Exception:
                self._send_json(400, {"error": "invalid base64 image"})
                return
            try:
                fb = image_bytes_to_fb(raw_img, r["width"], r["height"])
            except Exception as e:
                self._send_json(400, {"error": f"image decode failed: {e}"})
                return
            png_b64 = base64.b64encode(
                fb_to_png_bytes(fb, r["width"], r["height"])).decode("ascii")
            self._send_json(200, {
                "key": key,
                "brp_base64": base64.b64encode(fb).decode("ascii"),
                "png_base64": png_b64,
                "size": len(fb),
            })
            return
        self._send_json(404, {"error": "unknown api"})

    def log_message(self, fmt, *args):
        # 静默日志，避免刷屏
        pass


def main():
    ap = argparse.ArgumentParser(description="GR II 画面定制工具")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"GR II 画面定制工具已启动：http://{args.host}:{args.port}")
    print("按 Ctrl+C 停止。")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()
