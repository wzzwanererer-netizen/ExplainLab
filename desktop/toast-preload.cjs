const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("captureToastApi", {
  onInit: (cb) => {
    ipcRenderer.on("toast-init", (_event, payload) => cb(payload));
  },
  onResult: (cb) => {
    ipcRenderer.on("toast-result", (_event, result) => cb(result));
  },
  accept: (payload) => ipcRenderer.send("toast-accept", payload),
  dismiss: (payload) => ipcRenderer.send("toast-dismiss", payload),
  openSpace: (spaceId) => ipcRenderer.send("toast-open-space", spaceId),
  close: () => ipcRenderer.send("toast-close"),
});
