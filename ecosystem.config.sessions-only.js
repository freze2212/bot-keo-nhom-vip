/**
 * PM2 — chỉ server + 4 session gốc (không bot, không forward)
 */
const path = require("path");
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
  ],
};
