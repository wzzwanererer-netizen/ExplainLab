const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("explainlabDesktop", {
  isDesktop: true,
  setTheme: (theme) => {
    ipcRenderer.send("nesti-theme-changed", theme);
  },
  showItemInFolder: (filePath) => {
    ipcRenderer.send("explainlab-reveal-path", filePath);
  },
  saveBinaryFile: (payload) => ipcRenderer.invoke("explainlab-save-binary", payload),
  exportHtmlToPdf: (payload) => ipcRenderer.invoke("explainlab-export-pdf", payload),
  exportHtmlToPng: (payload) => ipcRenderer.invoke("explainlab-export-png", payload),
  setTaskCaptureEnabled: (enabled) => {
    ipcRenderer.send("explainlab-set-capture-enabled", Boolean(enabled));
  },
  testTaskCapturePopup: () => {
    ipcRenderer.send("explainlab-test-capture-popup");
  },
  getAutoStart: () => ipcRenderer.invoke("explainlab-get-autostart"),
  setAutoStart: (enabled) =>
    ipcRenderer.invoke("explainlab-set-autostart", Boolean(enabled)),
  onAutoStartChanged: (cb) => {
    const handler = (_event, enabled) => cb(Boolean(enabled));
    ipcRenderer.on("explainlab-autostart-changed", handler);
    return () => ipcRenderer.removeListener("explainlab-autostart-changed", handler);
  },
  onNavigateSpace: (cb) => {
    const handler = (_event, spaceId) => cb(spaceId);
    ipcRenderer.on("explainlab-open-space", handler);
    return () => ipcRenderer.removeListener("explainlab-open-space", handler);
  },
});
