/**
 * ExplainLab Native Windows Desktop Shell (Electron)
 *
 * - 原生无边框集成标题栏（titleBarStyle: hidden + titleBarOverlay + Windows 11 Mica）
 * - 彻底脱离浏览器，无 Edge 快捷键劫持、无 Bing 弹窗
 * - 内置静态资源服务与 /api（含 SSE 流式）反向代理，无需 vite preview
 * - 自动托管本地 ExplainLab Python 后端生命周期
 */

const { app, BrowserWindow, shell, ipcMain, screen, Tray, Menu, nativeImage, dialog, globalShortcut } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");

const IS_WIN = process.platform === "win32";
const IS_MAC = process.platform === "darwin";
const ROOT_DIR = path.resolve(__dirname, "..");
const FRONTEND_DIST = path.join(ROOT_DIR, "frontend", "dist");
const BACKEND_DIR = path.join(ROOT_DIR, "backend");
const PYTHON_EXE = IS_WIN
  ? path.join(ROOT_DIR, ".venv", "Scripts", "python.exe")
  : path.join(ROOT_DIR, ".venv", "bin", "python");
const ICON_PATH = IS_WIN
  ? path.join(ROOT_DIR, "scripts", "explainlab.ico")
  : path.join(__dirname, "nesti-logo.png");

const BACKEND_HOST = "127.0.0.1";
const BACKEND_PORT = 8000;

const START_SILENT = process.argv.includes("--silent");
const STARTUP_SHORTCUT_PATH = path.join(
  app.getPath("appData"),
  "Microsoft",
  "Windows",
  "Start Menu",
  "Programs",
  "Startup",
  "ExplainLab.lnk",
);

let mainWindow = null;
let toastWindow = null;
let quickNoteWindow = null;
let tray = null;
let localServer = null;
let backendProc = null;
let startedBackendByUs = false;
let isQuitting = false;
let currentTheme = "light";
let taskCaptureEnabled = true;
let capturePollTimer = null;

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".mjs": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".woff": "font/woff",
  ".ttf": "font/ttf",
};

function isPortOpen(host, port) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host, port });
    socket.setTimeout(500);
    socket.on("connect", () => {
      socket.destroy();
      resolve(true);
    });
    socket.on("error", () => {
      socket.destroy();
      resolve(false);
    });
    socket.on("timeout", () => {
      socket.destroy();
      resolve(false);
    });
  });
}

async function ensureBackendRunning() {
  if (await isPortOpen(BACKEND_HOST, BACKEND_PORT)) {
    return;
  }
  if (!fs.existsSync(PYTHON_EXE)) {
    return;
  }
  backendProc = spawn(
    PYTHON_EXE,
    ["-m", "uvicorn", "app.main:app", "--host", BACKEND_HOST, "--port", String(BACKEND_PORT)],
    {
      cwd: BACKEND_DIR,
      windowsHide: true,
      stdio: "ignore",
    },
  );
  startedBackendByUs = true;
  for (let i = 0; i < 40; i += 1) {
    if (await isPortOpen(BACKEND_HOST, BACKEND_PORT)) break;
    await new Promise((r) => setTimeout(r, 250));
  }
}

/** 启动内置本地静态与 /api（含 SSE 流式）反向代理服务，监听随机空闲端口。 */
function startLocalAppServer() {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      const reqUrl = req.url || "/";
      // /api/* 完整流式反代到本地 FastAPI 后端
      if (reqUrl.startsWith("/api")) {
        const proxyReq = http.request(
          {
            hostname: BACKEND_HOST,
            port: BACKEND_PORT,
            path: reqUrl,
            method: req.method,
            headers: {
              ...req.headers,
              host: `${BACKEND_HOST}:${BACKEND_PORT}`,
            },
          },
          (proxyRes) => {
            res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
            proxyRes.pipe(res, { end: true });
          },
        );
        proxyReq.on("error", () => {
          if (!res.headersSent) {
            res.writeHead(502, { "Content-Type": "application/json; charset=utf-8" });
            res.end(JSON.stringify({ detail: "无法连接到本地 ExplainLab 后端引擎" }));
          }
        });
        req.pipe(proxyReq, { end: true });
        return;
      }

      // 静态资源托管（frontend/dist）
      const cleanPath = decodeURIComponent(reqUrl.split("?")[0]);
      let filePath = path.join(FRONTEND_DIST, cleanPath === "/" ? "index.html" : cleanPath);
      if (!filePath.startsWith(FRONTEND_DIST) || !fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
        filePath = path.join(FRONTEND_DIST, "index.html");
      }
      const ext = path.extname(filePath).toLowerCase();
      res.writeHead(200, {
        "Content-Type": MIME_TYPES[ext] || "application/octet-stream",
        "Cache-Control": "no-store, no-cache, must-revalidate",
      });
      fs.createReadStream(filePath).pipe(res);
    });

    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const addr = server.address();
      resolve({ server, port: addr.port });
    });
  });
}

function createWindow(appPort) {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 680,
    title: "Nesti · AI 工作空间",
    icon: fs.existsSync(ICON_PATH) ? ICON_PATH : undefined,
    backgroundColor: "#eef3fa",
    titleBarStyle: IS_MAC ? "hiddenInset" : "hidden",
    ...(IS_WIN
      ? {
          titleBarOverlay: {
            color: "#00000000",
            symbolColor: "#243247",
            height: 44,
          },
        }
      : {}),
    autoHideMenuBar: true,
    show: !START_SILENT,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  // 点击右上角关闭按钮时最小化到系统托盘后台继续监听任务；托盘菜单可彻底退出
  mainWindow.on("close", (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  // 外部链接用系统默认浏览器打开，内部保持在原生窗口内
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http://") || url.startsWith("https://")) {
      void shell.openExternal(url);
    }
    return { action: "deny" };
  });

  void mainWindow.loadURL(`http://127.0.0.1:${appPort}/`);
}

// 响应前端浅色/深色主题切换，实时更新原生 Windows 11 右上角窗口按钮颜色
ipcMain.on("nesti-theme-changed", (_event, theme) => {
  currentTheme = theme === "dark" ? "dark" : "light";
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const isDark = currentTheme === "dark";
  try {
    if (IS_WIN && typeof mainWindow.setTitleBarOverlay === "function") {
      mainWindow.setTitleBarOverlay({
        color: "#00000000",
        symbolColor: isDark ? "#e7effa" : "#243247",
        height: 44,
      });
    }
    mainWindow.setBackgroundColor(isDark ? "#0b1019" : "#eef3fa");
  } catch {
    // 忽略旧版系统不支持
  }
});

ipcMain.on("explainlab-reveal-path", (_event, filePath) => {
  if (typeof filePath !== "string" || !filePath.trim()) return;
  const normalized = path.normalize(filePath.trim());
  if (fs.existsSync(normalized)) {
    shell.showItemInFolder(normalized);
  } else if (fs.existsSync(path.dirname(normalized))) {
    void shell.openPath(path.dirname(normalized));
  }
});

// 原生 Windows 另存为对话框：让用户自选目录保存 Word (.docx) / PPT (.pptx)
ipcMain.handle("explainlab-save-binary", async (_event, payload) => {
  const { defaultFilename, filterName, extensions, base64 } = payload || {};
  const res = await dialog.showSaveDialog(mainWindow || undefined, {
    title: "选择保存位置",
    defaultPath: path.join(app.getPath("documents"), defaultFilename || "Nesti-Export.bin"),
    filters: [{ name: filterName || "文档", extensions: extensions || ["*"] }],
  });
  if (res.canceled || !res.filePath) return { saved: false, canceled: true };
  fs.writeFileSync(res.filePath, Buffer.from(base64, "base64"));
  return { saved: true, path: res.filePath };
});

// 原生离屏 Chromium printToPDF：用户自选保存目录后渲染高清 A4 中文 PDF
ipcMain.handle("explainlab-export-pdf", async (_event, payload) => {
  const { defaultFilename, html } = payload || {};
  const res = await dialog.showSaveDialog(mainWindow || undefined, {
    title: "选择 PDF 总结报告保存位置",
    defaultPath: path.join(app.getPath("documents"), defaultFilename || "Nesti-总结报告.pdf"),
    filters: [{ name: "PDF 文档", extensions: ["pdf"] }],
  });
  if (res.canceled || !res.filePath) return { saved: false, canceled: true };

  const win = new BrowserWindow({
    show: false,
    width: 1024,
    height: 1400,
    webPreferences: { sandbox: true, contextIsolation: true },
  });
  try {
    await win.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`);
    await new Promise((r) => setTimeout(r, 350));
    const pdfBuf = await win.webContents.printToPDF({
      printBackground: true,
      pageSize: "A4",
      margins: { top: 0.45, bottom: 0.45, left: 0.45, right: 0.45 },
    });
    fs.writeFileSync(res.filePath, pdfBuf);
    return { saved: true, path: res.filePath };
  } finally {
    if (!win.isDestroyed()) win.destroy();
  }
});

// 原生离屏高清知识卡片长图 (.png)：用户自选保存目录后按内容实际高度截图保存
ipcMain.handle("explainlab-export-png", async (_event, payload) => {
  const { defaultFilename, html } = payload || {};
  const res = await dialog.showSaveDialog(mainWindow || undefined, {
    title: "选择知识卡片长图保存位置",
    defaultPath: path.join(app.getPath("pictures"), defaultFilename || "Nesti-知识卡片.png"),
    filters: [{ name: "PNG 图片", extensions: ["png"] }],
  });
  if (res.canceled || !res.filePath) return { saved: false, canceled: true };

  const win = new BrowserWindow({
    show: false,
    width: 860,
    height: 1200,
    useContentSize: true,
    webPreferences: { sandbox: true, contextIsolation: true },
  });
  try {
    await win.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`);
    await new Promise((r) => setTimeout(r, 350));
    const h = await win.webContents.executeJavaScript(
      "Math.min(4800, Math.max(600, document.documentElement.scrollHeight + 24))",
    );
    win.setContentSize(860, Math.ceil(Number(h) || 1200));
    await new Promise((r) => setTimeout(r, 200));
    const image = await win.webContents.capturePage();
    fs.writeFileSync(res.filePath, image.toPNG());
    return { saved: true, path: res.filePath };
  } finally {
    if (!win.isDestroyed()) win.destroy();
  }
});

/** 向本地 FastAPI 后端发起轻量 JSON 请求（不走浏览器、不占焦点）。 */
function backendJsonRequest(method, apiPath, bodyObj) {
  return new Promise((resolve, reject) => {
    const bodyStr = bodyObj ? JSON.stringify(bodyObj) : null;
    const req = http.request(
      {
        hostname: BACKEND_HOST,
        port: BACKEND_PORT,
        path: apiPath,
        method,
        headers: {
          "Content-Type": "application/json",
          ...(bodyStr ? { "Content-Length": Buffer.byteLength(bodyStr) } : {}),
        },
        timeout: 60000,
      },
      (res) => {
        let data = "";
        res.on("data", (chunk) => {
          data += chunk;
        });
        res.on("end", () => {
          try {
            const parsed = data ? JSON.parse(data) : {};
            if (res.statusCode && res.statusCode >= 400) {
              reject(new Error(parsed.detail || `HTTP ${res.statusCode}`));
            } else {
              resolve(parsed);
            }
          } catch (err) {
            reject(err);
          }
        });
      },
    );
    req.on("error", reject);
    req.on("timeout", () => {
      req.destroy();
      reject(new Error("请求超时"));
    });
    if (bodyStr) req.write(bodyStr);
    req.end();
  });
}

function closeToastWindow() {
  if (toastWindow && !toastWindow.isDestroyed()) {
    toastWindow.close();
  }
  toastWindow = null;
}

function hideQuickNoteWindow() {
  if (quickNoteWindow && !quickNoteWindow.isDestroyed()) {
    quickNoteWindow.hide();
  }
}

function toggleQuickNoteWindow() {
  if (quickNoteWindow && !quickNoteWindow.isDestroyed()) {
    if (quickNoteWindow.isVisible()) {
      quickNoteWindow.hide();
      return;
    }
    const display = screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
    const wa = display.workArea;
    const width = 560;
    const height = 228;
    quickNoteWindow.setBounds({
      x: Math.round(wa.x + (wa.width - width) / 2),
      y: Math.round(wa.y + Math.max(48, Math.round(wa.height * 0.2))),
      width,
      height,
    });
    quickNoteWindow.show();
    quickNoteWindow.focus();
    quickNoteWindow.webContents.send("quick-note-focus", { theme: currentTheme });
    return;
  }

  const display = screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
  const wa = display.workArea;
  const width = 560;
  const height = 228;
  quickNoteWindow = new BrowserWindow({
    width,
    height,
    x: Math.round(wa.x + (wa.width - width) / 2),
    y: Math.round(wa.y + Math.max(48, Math.round(wa.height * 0.2))),
    frame: false,
    transparent: true,
    resizable: false,
    minimizable: false,
    maximizable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "quick-note-preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  quickNoteWindow.setAlwaysOnTop(true, "floating");
  quickNoteWindow.on("blur", () => {
    if (quickNoteWindow && !quickNoteWindow.isDestroyed()) {
      quickNoteWindow.hide();
    }
  });
  quickNoteWindow.on("closed", () => {
    quickNoteWindow = null;
  });
  quickNoteWindow.webContents.once("did-finish-load", () => {
    if (!quickNoteWindow || quickNoteWindow.isDestroyed()) return;
    quickNoteWindow.show();
    quickNoteWindow.focus();
    quickNoteWindow.webContents.send("quick-note-focus", { theme: currentTheme });
  });
  void quickNoteWindow.loadFile(path.join(__dirname, "quick-note.html"));
}

function backendUploadMedia(itemId, filename, mimeType, rawBuffer) {
  return new Promise((resolve, reject) => {
    const boundary = `----NestiQuickNote${Date.now()}`;
    const head = Buffer.from(
      `--${boundary}\r\n` +
        `Content-Disposition: form-data; name="file"; filename="${filename}"\r\n` +
        `Content-Type: ${mimeType || "image/png"}\r\n\r\n`,
      "utf-8",
    );
    const tail = Buffer.from(`\r\n--${boundary}--\r\n`, "utf-8");
    const body = Buffer.concat([head, rawBuffer, tail]);
    const req = http.request(
      {
        hostname: BACKEND_HOST,
        port: BACKEND_PORT,
        path: `/api/knowledge/${itemId}/media`,
        method: "POST",
        headers: {
          "Content-Type": `multipart/form-data; boundary=${boundary}`,
          "Content-Length": body.length,
        },
        timeout: 15000,
      },
      (res) => {
        const chunks = [];
        res.on("data", (c) => chunks.push(c));
        res.on("end", () => {
          if ((res.statusCode || 500) >= 400) {
            reject(new Error(`HTTP ${res.statusCode}`));
          } else {
            resolve(true);
          }
        });
      },
    );
    req.on("error", reject);
    req.on("timeout", () => req.destroy(new Error("upload timeout")));
    req.write(body);
    req.end();
  });
}

/** 弹出非常驻、不抢焦点的右下角临时悬浮窗，倒计时结束后自动消失。 */
function showCaptureToast(suggestion) {
  closeToastWindow();
  const display = screen.getPrimaryDisplay();
  const wa = display.workArea;
  const width = 396;
  const height = 172;
  const x = Math.round(wa.x + wa.width - width - 14);
  const y = Math.round(wa.y + wa.height - height - 14);

  toastWindow = new BrowserWindow({
    width,
    height,
    x,
    y,
    frame: false,
    transparent: true,
    resizable: false,
    movable: false,
    minimizable: false,
    maximizable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    focusable: false,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "toast-preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  toastWindow.setAlwaysOnTop(true, "floating");
  toastWindow.on("closed", () => {
    toastWindow = null;
  });

  toastWindow.webContents.once("did-finish-load", () => {
    if (!toastWindow || toastWindow.isDestroyed()) return;
    toastWindow.webContents.send("toast-init", {
      suggestion,
      theme: currentTheme,
    });
    toastWindow.showInactive();
  });

  void toastWindow.loadFile(path.join(__dirname, "capture-toast.html"));
}

async function pollCompletedAgentTasks(includeLatest = false) {
  if (!includeLatest && (!taskCaptureEnabled || toastWindow)) return;
  try {
    const list = await backendJsonRequest(
      "GET",
      `/api/agents/completed-suggestions?include_latest=${includeLatest ? "true" : "false"}`,
    );
    if (Array.isArray(list) && list.length > 0) {
      showCaptureToast(list[0]);
    }
  } catch {
    // 后端未就绪或网络波动时静默跳过
  }
}

function isAutoStartEnabled() {
  try {
    if (IS_WIN) {
      return fs.existsSync(STARTUP_SHORTCUT_PATH);
    }
    return Boolean(app.getLoginItemSettings().openAtLogin);
  } catch {
    return false;
  }
}

function setAutoStartEnabled(enabled) {
  try {
    if (!IS_WIN) {
      app.setLoginItemSettings({
        openAtLogin: Boolean(enabled),
        openAsHidden: true,
        args: ["--silent"],
      });
    } else if (enabled) {
      const startupDir = path.dirname(STARTUP_SHORTCUT_PATH);
      if (!fs.existsSync(startupDir)) {
        fs.mkdirSync(startupDir, { recursive: true });
      }
      shell.writeShortcutLink(STARTUP_SHORTCUT_PATH, "create", {
        target: process.execPath,
        args: `"${__dirname}" --silent`,
        cwd: __dirname,
        icon: fs.existsSync(ICON_PATH) ? ICON_PATH : process.execPath,
        iconIndex: 0,
        description: "ExplainLab 个人知识库（开机静默进系统托盘）",
      });
    } else if (fs.existsSync(STARTUP_SHORTCUT_PATH)) {
      fs.unlinkSync(STARTUP_SHORTCUT_PATH);
    }
  } catch (err) {
    log(`AUTOSTART_ERR: ${err && err.message ? err.message : err}`);
  }
  const actual = isAutoStartEnabled();
  refreshTrayMenu();
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("explainlab-autostart-changed", actual);
  }
  return actual;
}

function showMainWindow() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
}

function refreshTrayMenu() {
  if (!tray) return;
  const menu = Menu.buildFromTemplate([
    {
      label: "打开 ExplainLab 主窗口",
      click: () => showMainWindow(),
    },
    {
      label: "一键闪记 (Alt+Shift+Space)",
      click: () => toggleQuickNoteWindow(),
    },
    {
      label: "测试任务入库弹窗",
      click: () => void pollCompletedAgentTasks(true),
    },
    { type: "separator" },
    {
      label: "开机静默自启动",
      type: "checkbox",
      checked: isAutoStartEnabled(),
      click: (item) => {
        setAutoStartEnabled(item.checked);
      },
    },
    {
      label: "Agent 完成任务自动弹窗",
      type: "checkbox",
      checked: taskCaptureEnabled,
      click: (item) => {
        taskCaptureEnabled = item.checked;
        refreshTrayMenu();
      },
    },
    { type: "separator" },
    {
      label: "彻底退出 ExplainLab",
      click: () => {
        isQuitting = true;
        closeToastWindow();
        app.quit();
      },
    },
  ]);
  tray.setContextMenu(menu);
}

function createTray() {
  if (tray) return;
  const icon = fs.existsSync(ICON_PATH)
    ? nativeImage.createFromPath(ICON_PATH)
    : nativeImage.createEmpty();
  tray = new Tray(icon);
  tray.setToolTip("ExplainLab 个人知识库（后台监听中）");
  tray.on("click", () => showMainWindow());
  tray.on("double-click", () => showMainWindow());
  refreshTrayMenu();
}

ipcMain.handle("explainlab-get-autostart", () => isAutoStartEnabled());
ipcMain.handle("explainlab-set-autostart", (_event, enabled) =>
  setAutoStartEnabled(Boolean(enabled)),
);

ipcMain.on("explainlab-set-capture-enabled", (_event, enabled) => {
  taskCaptureEnabled = Boolean(enabled);
  refreshTrayMenu();
});

ipcMain.on("explainlab-test-capture-popup", () => {
  void pollCompletedAgentTasks(true);
});

ipcMain.on("toast-close", () => {
  closeToastWindow();
});

ipcMain.on("quick-note-close", () => {
  hideQuickNoteWindow();
});

ipcMain.handle("quick-note-submit", async (_event, payload) => {
  try {
    const rawText = String((payload && payload.text) || "").trim();
    const img = payload && payload.image ? payload.image : null;

    // 如果是纯网页链接且没有附带图片，直接走一键网址剪藏接口！
    if (!img && /^https?:\/\/\S+$/i.test(rawText) && !rawText.includes("\n")) {
      const clipped = await backendJsonRequest("POST", "/api/export/clip-url", {
        url: rawText,
      });
      return { ok: true, id: clipped.id, message: `已剪藏网页：${(clipped.title || "").slice(0, 26)}` };
    }

    const firstLine = rawText
      .split(/\r?\n/)
      .map((s) => s.replace(/^#+\s*/, "").trim())
      .find(Boolean);
    const title = firstLine ? firstLine.slice(0, 48) : `闪记截图 ${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`;
    const content = rawText || "（一键闪记粘贴的截图，详见下方附件）";

    const created = await backendJsonRequest("POST", "/api/knowledge", {
      title,
      content,
    });
    if (img && img.base64 && created && created.id) {
      const rawBuf = Buffer.from(img.base64, "base64");
      await backendUploadMedia(created.id, img.filename || "quick-capture.png", img.mimeType || "image/png", rawBuf);
    }
    return { ok: true, id: created.id, message: img ? "已秒存文字与截图到知识库" : "已秒存至个人知识库" };
  } catch (err) {
    return { ok: false, error: err && err.message ? err.message : "存入失败" };
  }
});

ipcMain.on("toast-dismiss", (_event, suggestion) => {
  closeToastWindow();
  if (suggestion && suggestion.file_path && suggestion.signature) {
    void backendJsonRequest("POST", "/api/agents/dismiss-suggestion", {
      file_path: suggestion.file_path,
      signature: suggestion.signature,
    }).catch(() => {});
  }
});

ipcMain.on("toast-accept", async (_event, suggestion) => {
  if (!suggestion || !suggestion.file_path) {
    closeToastWindow();
    return;
  }
  try {
    const res = await backendJsonRequest("POST", "/api/agents/vacuum", {
      agent_name: suggestion.agent_name,
      session_files: [suggestion.file_path],
      max_sessions: 1,
    });
    const created = Array.isArray(res.created_items) ? res.created_items : [];
    const targetSpaceId = (created[0] && created[0].space_id) || suggestion.space_id || "";
    if (toastWindow && !toastWindow.isDestroyed()) {
      toastWindow.webContents.send("toast-result", {
        ok: true,
        createdCount: created.length,
        spaceId: targetSpaceId,
      });
    }
  } catch (err) {
    if (toastWindow && !toastWindow.isDestroyed()) {
      toastWindow.webContents.send("toast-result", {
        ok: false,
        error: err && err.message ? err.message : "入库失败",
      });
    }
  }
});

ipcMain.on("toast-open-space", (_event, spaceId) => {
  closeToastWindow();
  if (mainWindow && !mainWindow.isDestroyed()) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
    if (spaceId) {
      mainWindow.webContents.send("explainlab-open-space", spaceId);
    }
  }
});

const LOG_FILE = path.join(__dirname, "startup.log");
function log(msg) {
  try {
    fs.appendFileSync(LOG_FILE, `[${new Date().toISOString()}] ${msg}\n`, "utf-8");
  } catch {}
}
process.on("uncaughtException", (err) => log(`UNCAUGHT: ${err.stack || err}`));
process.on("unhandledRejection", (err) => log(`REJECTION: ${err && err.stack ? err.stack : err}`));

// 单实例锁：重复双击桌面快捷方式时直接唤起已有窗口
const gotLock = app.requestSingleInstanceLock();
log(`gotLock=${gotLock}`);
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    showMainWindow();
  });

  app.on("before-quit", () => {
    isQuitting = true;
    globalShortcut.unregisterAll();
  });

  app.whenReady().then(async () => {
    log(`app.whenReady fired (silent=${START_SILENT})`);
    await ensureBackendRunning();
    log("backend ready");
    const started = await startLocalAppServer();
    log(`local server on port ${started.port}`);
    localServer = started.server;
    createWindow(started.port);
    createTray();
    try {
      const ok = globalShortcut.register("Alt+Shift+Space", () => {
        toggleQuickNoteWindow();
      });
      log(`globalShortcut Alt+Shift+Space registered=${ok}`);
    } catch (err) {
      log(`SHORTCUT_ERR: ${err && err.message ? err.message : err}`);
    }
    log("window and tray created");
    // 每 10 秒零 Token 轮询一次已完成的 Agent 任务，仅在完成瞬间弹出临时悬浮窗
    capturePollTimer = setInterval(() => {
      void pollCompletedAgentTasks(false);
    }, 10000);
  }).catch((err) => log(`READY_ERR: ${err.stack || err}`));
}

app.on("window-all-closed", () => {
  if (!isQuitting) return;
  if (capturePollTimer) {
    clearInterval(capturePollTimer);
    capturePollTimer = null;
  }
  closeToastWindow();
  if (tray) {
    tray.destroy();
    tray = null;
  }
  if (localServer) {
    localServer.close();
    localServer = null;
  }
  if (startedBackendByUs && backendProc && !backendProc.killed) {
    backendProc.kill();
    backendProc = null;
  }
  app.quit();
});
