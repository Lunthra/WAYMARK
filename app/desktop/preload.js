const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("waymark", {
    invoke: async (action, payload = {}) => {
        if (typeof action !== "string" || !action.trim()) {
            throw new TypeError("WAYMARK action must be a non-empty string.");
        }
        if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
            throw new TypeError("WAYMARK payload must be an object.");
        }
        return ipcRenderer.invoke("waymark:invoke", { action, payload });
    }
});
