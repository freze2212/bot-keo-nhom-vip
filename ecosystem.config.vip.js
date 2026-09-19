/**
 * PM2 VIP — chỉ 2 nhóm Tele (thật + ảo) + server.
 * Capture ảnh: vision Windows hoặc 1 session (tùy máy).
 * pm2 start ecosystem.config.vip.js
 */
const path = require("path");
const pythonInterpreter =
  process.platform === "win32"
    ? process.env.PYTHON_PATH || "python"
    : "./venv/bin/python";

const dotenv = { DOTENV_CONFIG_PATH: path.join(__dirname, ".env") };

module.exports = {
  apps: [
    {
      name: "server_vip",
      script: "./server.js",
      cwd: __dirname,
      node_args: "--max-old-space-size=1024",
      interpreter_args: "-r dotenv/config",
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      watch: false,
      max_memory_restart: "1024M",
      env: { ...dotenv, SERVER_VERBOSE_LOG: "false" },
    },
    {
      name: "forward_vip",
      script: "bot_forward_runner.py",
      interpreter: pythonInterpreter,
      cwd: __dirname,
      args: "--run-now",
      instances: 1,
      autorestart: true,
      watch: false,
      max_restarts: 20,
      restart_delay: 15000,
      env: { PYTHONUNBUFFERED: "1" },
    },
  ],
};
