const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("nestiQuickNote", {
  submit: (payload) => ipcRenderer.invoke("quick-note-submit", payload),
  close: () => ipcRenderer.send("quick-note-close"),
  onFocusInput: (cb) => {
    ipcRenderer.on("quick-note-focus", (_event, data) => cb(data));
  },
});
