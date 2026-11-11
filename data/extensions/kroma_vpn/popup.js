document.addEventListener('DOMContentLoaded', () => {
  const dot = document.getElementById('dot');
  const statusTitle = document.getElementById('statusTitle');
  const protoBadge = document.getElementById('protoBadge');
  const serverInfo = document.getElementById('serverInfo');
  const countryInfo = document.getElementById('countryInfo');
  const btnReconnect = document.getElementById('btnReconnect');

  function updateUI() {
    chrome.runtime.sendMessage({ action: "getStatus" }, (config) => {
      if (config && config.enabled && config.server && config.server.host) {
        dot.className = "pulse-dot";
        statusTitle.textContent = "Connected (Auto-VPN)";
        protoBadge.textContent = (config.server.type || "HTTP").toUpperCase();
        serverInfo.textContent = `${config.server.host}:${config.server.port}`;
        countryInfo.textContent = config.server.country || "Active Tunnel";
      } else {
        dot.className = "pulse-dot off";
        statusTitle.textContent = "Disabled";
        protoBadge.textContent = "NONE";
        serverInfo.textContent = "Direct Connection";
        countryInfo.textContent = "Local Network";
      }
    });
  }

  btnReconnect?.addEventListener('click', () => {
    btnReconnect.textContent = "Connecting...";
    chrome.runtime.sendMessage({ action: "reconnect" }, () => {
      setTimeout(() => {
        btnReconnect.textContent = "⚡ Reconnect";
        updateUI();
      }, 500);
    });
  });

  updateUI();
});

