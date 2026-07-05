const DEFAULTS = { backendUrl: "http://localhost:8000", token: "", lastSessionId: "" };

function getConfig() {
  return new Promise((resolve) => chrome.storage.local.get(DEFAULTS, resolve));
}

function setStatus(text, kind) {
  const el = document.getElementById("status");
  el.className = kind || "";
  el.textContent = text || "";
}

function dataUrlToBlob(dataUrl) {
  const [meta, b64] = dataUrl.split(",");
  const mime = meta.match(/:(.*?);/)[1];
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}

async function loadSessions(cfg) {
  const res = await fetch(`${cfg.backendUrl}/api/plugins/browser_extension/sessions`, {
    headers: { "X-Plugin-Token": cfg.token },
  });
  if (!res.ok) throw new Error(`Session list failed: ${res.status}`);
  return res.json();
}

async function main() {
  const cfg = await getConfig();
  const select = document.getElementById("session");
  const captureBtn = document.getElementById("capture");
  const descriptionEl = document.getElementById("description");

  if (!cfg.token) {
    setStatus("No pairing token. Open Options to configure.", "error");
    return;
  }

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  descriptionEl.placeholder = tab ? tab.title : descriptionEl.placeholder;

  try {
    const sessions = await loadSessions(cfg);
    select.innerHTML = "";
    if (sessions.length === 0) {
      select.innerHTML = '<option value="">No sessions - create one in the app first</option>';
      return;
    }
    for (const s of sessions) {
      const opt = document.createElement("option");
      opt.value = s.id;
      opt.textContent = s.title;
      if (s.id === cfg.lastSessionId) opt.selected = true;
      select.appendChild(opt);
    }
    captureBtn.disabled = false;
  } catch (err) {
    setStatus(err.message, "error");
    return;
  }

  captureBtn.addEventListener("click", async () => {
    captureBtn.disabled = true;
    setStatus("Capturing…");
    try {
      const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "png" });
      const blob = dataUrlToBlob(dataUrl);

      const form = new FormData();
      form.append("session_id", select.value);
      form.append("url", tab.url || "");
      form.append("title", tab.title || "");
      if (descriptionEl.value) form.append("description", descriptionEl.value);
      form.append("file", blob, `capture-${Date.now()}.png`);

      const res = await fetch(`${cfg.backendUrl}/api/plugins/browser_extension/captures`, {
        method: "POST",
        headers: { "X-Plugin-Token": cfg.token },
        body: form,
      });
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(`Upload failed: ${res.status} ${text}`);
      }
      const body = await res.json();
      await chrome.storage.local.set({ lastSessionId: select.value });
      setStatus(`Attached. Extraction: ${body.extraction_status || "n/a"}`, "ok");
    } catch (err) {
      setStatus(err.message, "error");
      captureBtn.disabled = false;
    }
  });

  document.getElementById("open-options").addEventListener("click", (e) => {
    e.preventDefault();
    chrome.runtime.openOptionsPage();
  });
}

main();
