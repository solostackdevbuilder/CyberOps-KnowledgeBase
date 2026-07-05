// Service worker: handles the Alt+S quick-capture shortcut.
// Popup-initiated captures go through popup.js so the user can pick a session.

const DEFAULTS = { backendUrl: "http://localhost:8000", token: "", lastSessionId: "" };

async function getConfig() {
  return new Promise((resolve) => {
    chrome.storage.local.get(DEFAULTS, (items) => resolve(items));
  });
}

async function captureActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) throw new Error("No active tab");
  const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "png" });
  return { tab, dataUrl };
}

function dataUrlToBlob(dataUrl) {
  const [meta, b64] = dataUrl.split(",");
  const mime = meta.match(/:(.*?);/)[1];
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}

async function uploadCapture({ backendUrl, token, sessionId, url, title, blob }) {
  const form = new FormData();
  form.append("session_id", sessionId);
  form.append("url", url || "");
  form.append("title", title || "");
  form.append("file", blob, `capture-${Date.now()}.png`);

  const res = await fetch(`${backendUrl}/api/plugins/browser_extension/captures`, {
    method: "POST",
    headers: { "X-Plugin-Token": token },
    body: form,
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`Upload failed: ${res.status} ${detail}`);
  }
  return res.json();
}

async function quickCapture() {
  const cfg = await getConfig();
  if (!cfg.token) {
    notify("CyOps Capture", "No pairing token. Open extension options to configure.");
    return;
  }
  if (!cfg.lastSessionId) {
    notify("CyOps Capture", "No last-used session. Open the popup and capture once first.");
    return;
  }

  try {
    const { tab, dataUrl } = await captureActiveTab();
    const blob = dataUrlToBlob(dataUrl);
    await uploadCapture({
      backendUrl: cfg.backendUrl,
      token: cfg.token,
      sessionId: cfg.lastSessionId,
      url: tab.url,
      title: tab.title,
      blob,
    });
    notify("CyOps Capture", `Attached to session ${cfg.lastSessionId.slice(0, 8)}…`);
  } catch (err) {
    notify("CyOps Capture - error", err.message || String(err));
  }
}

function notify(title, message) {
  // Use a badge instead of chrome.notifications to avoid another permission.
  chrome.action.setBadgeText({ text: "!" });
  chrome.action.setBadgeBackgroundColor({ color: title.includes("error") ? "#c00" : "#080" });
  chrome.action.setTitle({ title: `${title}\n${message}` });
  setTimeout(() => chrome.action.setBadgeText({ text: "" }), 3000);
}

chrome.commands.onCommand.addListener((cmd) => {
  if (cmd === "quick-capture") quickCapture();
});
