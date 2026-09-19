const { app, BrowserWindow, ipcMain, dialog, Menu } = require("electron");
const path = require("path");
const { spawn } = require("child_process");
const net = require("net");
const crypto = require("crypto");

let bridgeProcess = null;
let bridgePort = null;
let bridgeToken = null;
let quitting = false;

function projectRoot() {
    if (app.isPackaged) {
        return process.resourcesPath;
    }

    return path.resolve(__dirname, "..", "..");
}

function rendererPath() {
    if (app.isPackaged) {
        return path.join(process.resourcesPath, "frontend", "index.html");
    }

    return path.join(projectRoot(), "app", "frontend", "index.html");
}

function appIconPath() {
    if (app.isPackaged) {
        return path.join(process.resourcesPath, "waymark.ico");
    }

    return path.join(projectRoot(), "app", "desktop", "assets", "waymark.ico");
}

function backendExecutable() {
    if (process.env.WAYMARK_BACKEND_EXECUTABLE) {
        return process.env.WAYMARK_BACKEND_EXECUTABLE;
    }

    if (app.isPackaged) {
        return path.join(process.resourcesPath, "WAYMARK-backend.exe");
    }

    return path.join(projectRoot(), ".venv", "Scripts", "python.exe");
}

function bridgeScript() {
    return path.join(projectRoot(), "app", "backend", "core", "bridge_server.py");
}

function rendererUrl() {
    return require("url").pathToFileURL(rendererPath()).href;
}

function findFreePort(preferred = 8765) {
    return new Promise((resolve, reject) => {
        const listen = (port) => {
            const server = net.createServer();

            server.once("error", () => {
                if (port !== 0) return listen(0);
                reject(new Error("Could not allocate a local WAYMARK bridge port."));
            });

            server.listen(port, "127.0.0.1", () => {
                const actual = server.address().port;
                server.close((error) => error ? reject(error) : resolve(actual));
            });
        };

        listen(preferred);
    });
}

function startBackendBridge() {
    const root = projectRoot();

    bridgeToken = crypto.randomBytes(32).toString("hex");

    return findFreePort().then((port) => {
        bridgePort = port;

        const args = app.isPackaged ? [] : [bridgeScript()];

        const env = {
            ...process.env,
            WAYMARK_BRIDGE_PORT: String(port),
            WAYMARK_BRIDGE_TOKEN: bridgeToken,
            WAYMARK_PROJECT_ROOT: root,
            WAYMARK_DATA_DIR: app.getPath("userData"),
            WAYMARK_LEGACY_DATA_DIR: app.isPackaged
                ? path.join(process.resourcesPath, "data")
                : path.join(root, "app", "backend", "data")
        };

        const packaged = app.isPackaged;

        bridgeProcess = spawn(backendExecutable(), args, {
            cwd: root,
            env,
            windowsHide: true,
            detached: packaged,
            stdio: packaged ? "ignore" : ["ignore", "pipe", "pipe"]
        });

        if (packaged) {
            bridgeProcess.unref();
        } else {
            bridgeProcess.stdout.on("data", (data) => {
                console.log(`[WAYMARK backend] ${data.toString().trim()}`);
            });

            bridgeProcess.stderr.on("data", (data) => {
                console.error(`[WAYMARK backend] ${data.toString().trim()}`);
            });
        }

        bridgeProcess.on("error", (error) => {
            console.error("[WAYMARK backend] process error", error);
        });

        bridgeProcess.on("exit", (code, signal) => {
            console.log(
                `[WAYMARK backend] exited with code ${code}, signal ${signal || "none"}`
            );

            bridgeProcess = null;

            if (!quitting) {
                console.error("[WAYMARK backend] unexpected exit");
            }
        });
    });
}

function stopBackendBridge() {
    quitting = true;

    if (!bridgeProcess) return;

    try {
        bridgeProcess.kill();
    } catch (_) {}

    bridgeProcess = null;
}

async function bridgeRequest(pathname, options = {}) {
    if (!bridgePort || !bridgeToken) {
        throw new Error("WAYMARK backend bridge is not initialized.");
    }

    const response = await fetch(
        `http://127.0.0.1:${bridgePort}${pathname}`,
        {
            ...options,
            headers: {
                "X-WAYMARK-Bridge-Token": bridgeToken,
                ...(options.headers || {})
            }
        }
    );

    return response;
}

async function waitForBridge(timeoutMs = 20000) {
    const deadline = Date.now() + timeoutMs;
    let lastError = null;

    while (Date.now() < deadline) {
        try {
            const response = await bridgeRequest("/health");

            if (response.ok) return;

            lastError = new Error(
                `Bridge returned HTTP ${response.status}`
            );
        } catch (error) {
            lastError = error;
        }

        await new Promise((resolve) => setTimeout(resolve, 150));
    }

    throw (
        lastError ||
        new Error("WAYMARK backend bridge did not start in time.")
    );
}

async function invokeBackend(action, payload = {}) {
    const response = await bridgeRequest("/api/invoke", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ action, payload })
    });

    let data;

    try {
        data = await response.json();
    } catch (_) {
        throw new Error(
            `WAYMARK bridge returned an invalid response (HTTP ${response.status}).`
        );
    }

    if (!response.ok || !data.ok) {
        throw new Error(
            data.error ||
            `WAYMARK bridge request failed (HTTP ${response.status}).`
        );
    }

    return data;
}

function assertTrustedSender(event) {
    const expected = rendererUrl();
    const actual =
        event.senderFrame?.url ||
        event.sender?.getURL?.() ||
        "";

    if (actual !== expected) {
        throw new Error("Untrusted IPC sender.");
    }
}

ipcMain.handle("waymark:invoke", async (event, request = {}) => {
    assertTrustedSender(event);

    const action = request?.action;
    const payload = request?.payload ?? {};

    if (typeof action !== "string" || !action.trim()) {
        throw new Error("WAYMARK action is required.");
    }

    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
        throw new Error("WAYMARK payload must be an object.");
    }

    return invokeBackend(action, payload);
});

function createWindow() {
    const win = new BrowserWindow({
        width: 1280,
        height: 800,
        minWidth: 1000,
        minHeight: 650,
        backgroundColor: "#0f1115",
        icon: appIconPath(),
        webPreferences: {
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: true,
            preload: path.join(__dirname, "preload.js")
        }
    });

    win.webContents.setWindowOpenHandler(() => ({
        action: "deny"
    }));

    win.webContents.on("will-navigate", (event, url) => {
        if (url !== rendererUrl()) {
            event.preventDefault();
        }
    });

    win.webContents.on("will-attach-webview", (event) => {
        event.preventDefault();
    });

    win.loadFile(rendererPath());

    return win;
}

app.whenReady().then(async () => {
    // WAYMARK is a focused desktop application; hide Electron's generic
    // File/Edit/View/Window application menu.
    Menu.setApplicationMenu(null);

    try {
        await startBackendBridge();
        await waitForBridge();
        createWindow();
    } catch (error) {
        console.error("[WAYMARK] startup failed", error);

        await dialog.showMessageBox({
            type: "error",
            title: "WAYMARK could not start",
            message: String(error.message || error)
        });

        stopBackendBridge();
        app.quit();
        return;
    }

    app.on("activate", () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
});

app.on("window-all-closed", () => {
    stopBackendBridge();

    if (process.platform !== "darwin") {
        app.quit();
    }
});

app.on("before-quit", () => {
    stopBackendBridge();
});
