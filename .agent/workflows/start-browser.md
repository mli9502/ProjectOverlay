---
description: Start headless Chromium browser for browser subagent
---

# Start Browser

This workflow starts a headless Chromium browser instance that the browser subagent can connect to.

## Steps

1. Check if Chromium is already running on port 9222:
```bash
pgrep -f "remote-debugging-port=9222" > /dev/null && echo "Browser already running" || echo "Browser not running"
```

// turbo
2. If not running, start headless Chromium:
```bash
~/.local/bin/chromium --headless --remote-debugging-port=9222 --disable-gpu --no-sandbox about:blank &
```

3. Wait 2 seconds for browser to initialize, then verify it's running:
```bash
sleep 2 && curl -s http://127.0.0.1:9222/json/version | head -1
```
