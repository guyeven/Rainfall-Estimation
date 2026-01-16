const { app, BrowserWindow } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const net = require("net");

let backendProcess;

function waitForPort(port, host = "127.0.0.1", timeoutMs = 20000) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const tryConnect = () => {
      const socket = new net.Socket();
      socket.once("error", () => {
        socket.destroy();
        if (Date.now() - start > timeoutMs) {
          reject(new Error("Backend did not start"));
        } else {
          setTimeout(tryConnect, 250);
        }
      });
      socket.connect(port, host, () => {
        socket.end();
        resolve();
      });
    };
    tryConnect();
  });
}

app.whenReady().then(async () => {
  const backendPath = app.isPackaged
    ? path.join(process.resourcesPath, "dist", "backend", "backend")
    : path.join(__dirname, "..", "dist", "backend", "backend");

  backendProcess = spawn(backendPath, [], { stdio: "ignore" });

  await waitForPort(8000);

  const indexHtml = app.isPackaged
    ? path.join(process.resourcesPath, "ui", "index.html")
    : path.join(__dirname, "..", "frontend", "dist", "index.html");

  const win = new BrowserWindow({
    width: 1200,
    height: 800
  });

  win.loadFile(indexHtml);
});

app.on("will-quit", () => {
  if (backendProcess) backendProcess.kill();
});
