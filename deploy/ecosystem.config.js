// pm2 start deploy/ecosystem.config.js && pm2 save
module.exports = {
  apps: [{
    name: "atlas",
    cwd: __dirname + "/..",
    script: ".venv/bin/python",
    args: "-m atlas",
    interpreter: "none",
    autorestart: true,
    max_restarts: 20,
    restart_delay: 5000,
    env: { TZ: "America/Toronto" },
  }],
};
