/**
 * PM2 — server + 4 session + 4 bot hô + forward (chạy forward riêng nếu cần)
 * pm2 start ecosystem.config.js
 */
const path = require("path");
const pythonInterpreter =
  process.platform === "win32"
    ? process.env.PYTHON_PATH || "python"
    : "./venv/bin/python";

const dotenv = { DOTENV_CONFIG_PATH: path.join(__dirname, ".env") };

function sessionApp(index, table) {
  return {
    name: `session_sexy_${index}`,
    script: "./servicePuppeteer/session.js",
    cwd: __dirname,
    node_args: "--max-old-space-size=1536",
    interpreter_args: "-r dotenv/config",
    instances: 1,
    exec_mode: "fork",
    autorestart: true,
    watch: false,
    min_uptime: "60s",
    max_restarts: 10,
    restart_delay: 10000,
    max_memory_restart: "1536M",
    env: { ...dotenv, ACCOUNT_INDEX: String(index), PREFERRED_TABLE: table },
  };
}

function botApp(ns) {
  return {
    name: `bot_sexy_${ns.replace("NS", "")}`,
    script: "bot.py",
    interpreter: pythonInterpreter,
    cwd: __dirname,
    instances: 1,
    autorestart: true,
    watch: false,
    max_restarts: 10,
    restart_delay: 8000,
    env: { PYTHONUNBUFFERED: "1", NAME_SERVICE: ns },
  };
}

module.exports = {
  apps: [
    {
      name: "server_sexy",
      script: "./server.js",
      cwd: __dirname,
      node_args: "--max-old-space-size=1536",
      interpreter_args: "-r dotenv/config",
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      watch: false,
      min_uptime: "30s",
      max_restarts: 15,
      restart_delay: 8000,
      max_memory_restart: "1536M",
      env: { ...dotenv, SERVER_VERBOSE_LOG: "false" },
    },
    sessionApp(1, "C01"),
    sessionApp(2, "C02"),
    sessionApp(3, "C05"),
    sessionApp(4, "C08"),
    botApp("NS1"),
    botApp("NS2"),
    botApp("NS3"),
    botApp("NS4"),
  ],
};
