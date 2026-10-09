/* GR II 画面定制工具 —— 前端逻辑 */
(function () {
  "use strict";

  let resources = [];
  let current = null;        // 当前资源 key
  let originalPng = null;    // 原始画面 PNG data URL
  let newBrpB64 = null;      // 转换后的 brp base64
  let newPng = null;         // 转换后的 PNG data URL
  let pendingFile = null;    // 用户选中的图片文件

  const $ = (sel) => document.querySelector(sel);

  // ---- 工具 ----
  function dataUrl(b64, mime) { return "data:" + mime + ";base64," + b64; }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  function downloadB64(b64, filename, mime) {
    const bytes = atob(b64);
    const arr = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
    downloadBlob(new Blob([arr], { type: mime || "application/octet-stream" }), filename);
  }

  function downloadText(text, filename) {
    downloadBlob(new Blob([text], { type: "text/plain;charset=utf-8" }), filename);
  }

  async function apiGet(path) {
    const r = await fetch(path, { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }

  async function apiPost(path, payload) {
    const r = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
    });
    return r.json();
  }

  // ---- 渲染侧边栏 ----
  function renderSidebar() {
    const sb = $("#sidebar");
    sb.innerHTML = "<h3>画面资源</h3>";
    resources.forEach((r) => {
      const btn = document.createElement("button");
      btn.className = "side-item" + (r.editable ? "" : " locked");
      btn.dataset.key = r.key;
      btn.innerHTML = r.label +
        '<span class="tag">' + (r.editable
          ? (r.width ? r.width + "×" + r.height : "")
          : "只读") + "</span>";
      btn.addEventListener("click", () => select(r));
      sb.appendChild(btn);
    });
  }

  // ---- 选择资源 ----
  function select(r) {
    current = r.key;
    newBrpB64 = null;
    newPng = null;
    pendingFile = null;
    document.querySelectorAll(".side-item").forEach((b) =>
      b.classList.toggle("active", b.dataset.key === r.key));

    if (!r.editable) {
      renderLocked(r);
      return;
    }
    renderEditor(r);
    loadOriginal(r);
  }

  function renderLocked(r) {
    $("#editor").style.display = "block";
    $("#editor").innerHTML =
      '<div class="ed-head"><h2>' + r.label + '</h2>' +
      '<span class="note">该资源不提供编辑</span></div>' +
      '<div class="hint-box"><b>已锁定。</b> ' + r.note + "</div>";
  }

  function renderEditor(r) {
    $("#editor").style.display = "block";
    $("#editor").innerHTML =
      '<div class="ed-head"><h2>' + r.label + '</h2>' +
      '<span class="note">' + r.note + "</span></div>" +
      '<div class="compare">' +
      '  <div class="col">' +
      '    <h4>原始画面 <span class="badge">机内</span></h4>' +
      '    <div class="canvas-wrap" id="orig-wrap"><div class="placeholder">加载中…</div></div>' +
      '  </div>' +
      '  <div class="col">' +
      '    <h4>你的新画面 <span class="badge new">自定义</span></h4>' +
      '    <div class="canvas-wrap" id="new-wrap"><div class="placeholder">导入图片后预览</div></div>' +
      '    <div class="dropzone" id="dropzone">' +
      '      点击选择或拖拽图片到此处<br>' +
      '      <strong>' + r.width + '×' + r.height + '</strong> · PNG / JPG，自动缩放适配' +
      '    </div>' +
      '  </div>' +
      '</div>' +
      '<div class="actions">' +
      '  <button class="btn primary" id="btn-convert" disabled>转换并预览</button>' +
      '  <button class="btn" id="btn-brp" disabled>下载 .brp 画面文件</button>' +
      '  <button class="btn" id="btn-ttl">下载 Startup.ttl 脚本</button>' +
      '  <button class="btn" id="btn-reset" disabled>还原原始画面</button>' +
      '</div>' +
      '<div class="info" id="info"></div>' +
      '<div class="hint-box"><b>写入 SD 卡：</b>把下载的 <b>' + r.key +
      '</b> 和 <b>Startup.ttl</b> 都放到 SD 卡【根目录】，相机正常开机即可自动应用。拔卡即恢复，无变砖风险。</div>';

    const dz = $("#dropzone");
    dz.addEventListener("click", () => {
      const inp = document.createElement("input");
      inp.type = "file";
      inp.accept = "image/*";
      inp.onchange = () => { if (inp.files[0]) onFile(inp.files[0]); };
      inp.click();
    });
    dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("drag"); });
    dz.addEventListener("dragleave", () => dz.classList.remove("drag"));
    dz.addEventListener("drop", (e) => {
      e.preventDefault();
      dz.classList.remove("drag");
      if (e.dataTransfer.files[0]) onFile(e.dataTransfer.files[0]);
    });

    $("#btn-convert").addEventListener("click", convert);
    $("#btn-brp").addEventListener("click", downloadBrp);
    $("#btn-ttl").addEventListener("click", downloadTtl);
    $("#btn-reset").addEventListener("click", resetPreview);
  }

  async function loadOriginal(r) {
    try {
      const d = await apiGet("/api/original?name=" + encodeURIComponent(r.key));
      originalPng = dataUrl(d.png_base64, "image/png");
      $("#orig-wrap").innerHTML = '<img src="' + originalPng + '" alt="原始画面">';
      $("#info").innerHTML = "原始资源 <b>" + d.size.toLocaleString() +
        " 字节</b>（" + d.width + "×" + d.height + " RGB565 大端）";
    } catch (e) {
      $("#orig-wrap").innerHTML =
        '<div class="placeholder">原始画面未随仓库提供。<br>' +
        '用 <code>python3 tools/gr2boot.py extract</code> 自提，<br>' +
        '或直接导入你的图片（不影响替换）。</div>';
      $("#info").innerHTML = "原始资源未提供（不影响导入自定义图片）";
    }
  }

  function onFile(file) {
    pendingFile = file;
    // 先在「新画面」区本地预览原图
    const reader = new FileReader();
    reader.onload = (ev) => {
      $("#new-wrap").innerHTML = '<img src="' + ev.target.result + '" alt="预览">';
    };
    reader.readAsDataURL(file);
    $("#btn-convert").disabled = false;
    $("#btn-brp").disabled = true;
    $("#btn-reset").disabled = true;
  }

  async function convert() {
    if (!pendingFile) return;
    const btn = $("#btn-convert");
    btn.disabled = true;
    btn.textContent = "转换中…";
    try {
      const buf = await pendingFile.arrayBuffer();
      const bytes = new Uint8Array(buf);
      let bin = "";
      for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
      const b64 = btoa(bin);
      const d = await apiPost("/api/convert", { target: current, image_base64: b64 });
      if (d.error) throw new Error(d.error);
      newBrpB64 = d.brp_base64;
      newPng = dataUrl(d.png_base64, "image/png");
      $("#new-wrap").innerHTML = '<img src="' + newPng + '" alt="转换后">';
      $("#btn-brp").disabled = false;
      $("#btn-reset").disabled = false;
      $("#info").innerHTML = "转换完成：<b>" + d.size.toLocaleString() +
        " 字节</b>（RGB565 大端，等长替换，目录表无需改动）";
    } catch (e) {
      alert("转换失败：" + e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "转换并预览";
    }
  }

  function downloadBrp() {
    if (!newBrpB64) return;
    downloadB64(newBrpB64, current, "application/octet-stream");
  }

  async function downloadTtl() {
    try {
      const d = await apiGet("/api/startup-ttl?name=" + encodeURIComponent(current));
      downloadText(d.ttl, "Startup.ttl");
    } catch (e) {
      alert("获取脚本失败：" + e.message);
    }
  }

  function resetPreview() {
    if (originalPng) {
      $("#new-wrap").innerHTML = '<img src="' + originalPng + '" alt="原始画面">';
    }
    newPng = null;
    newBrpB64 = null;
    pendingFile = null;
    $("#btn-brp").disabled = true;
    $("#btn-reset").disabled = true;
    $("#btn-convert").disabled = true;
  }

  // ---- 启动 ----
  async function init() {
    try {
      const d = await apiGet("/api/resources");
      resources = d.resources;
      renderSidebar();
      const first = resources.find((r) => r.editable) || resources[0];
      if (first) select(first);
    } catch (e) {
      document.getElementById("main").innerHTML =
        '<div class="panel"><h2>无法连接后端</h2><p>' + e.message +
        "</p><p>请确认已运行 <code>python3 app.py</code>。</p></div>";
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
