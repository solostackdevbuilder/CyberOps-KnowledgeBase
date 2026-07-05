const DEFAULTS = { backendUrl: "http://localhost:8000", token: "" };

const backendUrlEl = document.getElementById("backendUrl");
const tokenEl = document.getElementById("token");
const statusEl = document.getElementById("status");

function setStatus(text, kind) {
  statusEl.className = `status ${kind || ""}`;
  statusEl.textContent = text || "";
}

function load() {
  chrome.storage.local.get(DEFAULTS, (items) => {
    backendUrlEl.value = items.backendUrl;
    tokenEl.value = items.token;
  });
}

document.getElementById("save").addEventListener("click", () => {
  const backendUrl = backendUrlEl.value.trim().replace(/\/$/, "");
  const token = tokenEl.value.trim();
  chrome.storage.local.set({ backendUrl, token }, () => setStatus("Saved.", "ok"));
});

document.getElementById("test").addEventListener("click", async () => {
  const backendUrl = backendUrlEl.value.trim().replace(/\/$/, "");
  const token = tokenEl.value.trim();
  setStatus("Testing…");
  try {
    const res = await fetch(`${backendUrl}/api/plugins/browser_extension/health`, {
      headers: { "X-Plugin-Token": token },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const body = await res.json();
    setStatus(
      `OK. Token configured on server: ${body.token_configured}. Captures so far: ${body.captures_total}.`,
      "ok"
    );
  } catch (err) {
    setStatus(`Failed: ${err.message}`, "error");
  }
});

load();
