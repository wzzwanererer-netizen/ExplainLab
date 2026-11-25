const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("explainlabDesktop", {
  isDesktop: true,
  setTheme: (theme) => {
    ipcRenderer.send("nesti-theme-changed", theme);
  },
});
