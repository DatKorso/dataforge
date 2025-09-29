module.exports = {
  apps: [
    {
      name: "dataforge",
      script: "scripts/start_dataforge.sh",
      interpreter: "/bin/bash",
      cwd: __dirname,
      autorestart: true,
      watch: false,
      max_memory_restart: "1G",
      env: {
        NODE_ENV: "production",
      },
      time: true,
    },
  ],
};

