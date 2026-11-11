// Kroma Auto-VPN Background Service Worker
// Automatically sets proxy settings on startup without any user interaction

async function loadConfig() {
  try {
    const res = await fetch(chrome.runtime.getURL('config.json'));
    return await res.json();
  } catch (e) {
    return {
      enabled: true,
      server: { type: "http", host: "", port: 0 }
    };
  }
}

async function applyProxy() {
  const config = await loadConfig();
  if (!config || !config.enabled || !config.server || !config.server.host || !config.server.port) {
    chrome.action.setBadgeText({ text: "OFF" });
    chrome.action.setBadgeBackgroundColor({ color: "#64748b" });
    chrome.action.setTitle({ title: "Kroma VPN: Disabled" });
    return;
  }

  const s = config.server;
  const ptype = (s.type || "http").toLowerCase();
  const phost = s.host.trim();
  const pport = parseInt(s.port, 10);

  const proxySettings = {
    mode: "fixed_servers",
    rules: {
      singleProxy: {
        scheme: ptype,
        host: phost,
        port: pport
      },
      bypassList: ["<local>", "127.0.0.1", "localhost"]
    }
  };

  chrome.proxy.settings.set(
    { value: proxySettings, scope: "regular" },
    () => {
      if (chrome.runtime.lastError) {
        console.warn("[Kroma VPN] Proxy set error:", chrome.runtime.lastError.message);
        chrome.action.setBadgeText({ text: "ERR" });
        chrome.action.setBadgeBackgroundColor({ color: "#ef4444" });
      } else {
        console.log(`[Kroma VPN] Connected to ${ptype}://${phost}:${pport}`);
        chrome.action.setBadgeText({ text: "ON" });
        chrome.action.setBadgeBackgroundColor({ color: "#10b981" });
        chrome.action.setTitle({ title: `Kroma VPN: Connected to ${s.country || phost} (${phost}:${pport})` });
      }
    }
  );
}

// Handle authentication if username/password present
chrome.webRequest.onAuthRequired.addListener(
  async (details, callback) => {
    const config = await loadConfig();
    if (config?.server?.username && config?.server?.password) {
      callback({
        authCredentials: {
          username: config.server.username,
          password: config.server.password
        }
      });
    } else {
      callback({});
    }
  },
  { urls: ["<all_urls>"] },
  ["asyncBlocking"]
);

// Apply immediately on worker load and startup
applyProxy();
chrome.runtime.onStartup.addListener(applyProxy);
chrome.runtime.onInstalled.addListener(applyProxy);

// Listen for messages from popup
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "getStatus") {
    loadConfig().then(cfg => sendResponse(cfg));
    return true;
  } else if (msg.action === "reconnect") {
    applyProxy().then(() => sendResponse({ ok: true }));
    return true;
  }
});

