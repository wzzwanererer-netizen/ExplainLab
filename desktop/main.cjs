/**
 * ExplainLab Native Windows Desktop Shell (Electron)
 *
 * - 原生无边框集成标题栏（titleBarStyle: hidden + titleBarOverlay + Windows 11 Mica）
 * - 彻底脱离浏览器，无 Edge 快捷键劫持、无 Bing 弹窗
 * - 内置静态资源服务与 /api（含 SSE 流式）反向代理，无需 vite preview
 * - 自动托管本地 ExplainLab Python 后端生命周期
 */

const { app, BrowserWindow, shell, ipcMain } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");

const ROOT_DIR = path.resolve(__dirname, "..");
const FRONTEND_DIST = path.join(ROOT_DIR, "frontend", "dist");
const BACKEND_DIR = path.join(ROOT_DIR, "backend");
const PYTHON_EXE = path.join(ROOT_DIR, ".venv", "Scripts", "python.exe");
const ICON_PATH = path.join(ROOT_DIR, "scripts", "explainlab.ico");

const BACKEND_HOST = "127.0.0.1";
const BACKEND_PORT = 8000;

let mainWindow = null;
let localServer = null;
let backendProc = null;
let startedBackendByUs = false;

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
      res.writeHead(200, { "Content-Type": MIME_TYPES[ext] || "application/octet-stream" });
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
    title: "ExplainLab",
    icon: fs.existsSync(ICON_PATH) ? ICON_PATH : undefined,
    backgroundColor: "#eef3fa",
    titleBarStyle: "hidden",
    titleBarOverlay: {
      color: "#00000000",
      symbolColor: "#243247",
      height: 38,
    },
    autoHideMenuBar: true,
    show: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
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
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const isDark = theme === "dark";
  try {
    mainWindow.setTitleBarOverlay({
      color: "#00000000",
      symbolColor: isDark ? "#e7effa" : "#243247",
      height: 38,
    });
    mainWindow.setBackgroundColor(isDark ? "#0b1019" : "#eef3fa");
  } catch {
    // 忽略旧版系统不支持
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
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    log("app.whenReady fired");
    await ensureBackendRunning();
    log("backend ready");
    const started = await startLocalAppServer();
    log(`local server on port ${started.port}`);
    localServer = started.server;
    createWindow(started.port);
    log("window created");
  }).catch((err) => log(`READY_ERR: ${err.stack || err}`));
}

app.on("window-all-closed", () => {
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
