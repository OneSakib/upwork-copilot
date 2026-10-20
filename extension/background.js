importScripts("common.js");

chrome.runtime.onInstalled.addListener((d) => {
  if (d.reason === "install") chrome.runtime.openOptionsPage();
  updateBadge();
});
chrome.runtime.onStartup.addListener(updateBadge);
chrome.storage.onChanged.addListener((c) => { if (c.cfg) updateBadge(); });

async function getCfg() { return (await chrome.storage.local.get("cfg")).cfg || {}; }
async function updateBadge() {
  const ok = isConfigured(await getCfg());
  chrome.action.setBadgeText({ text: ok ? "" : "!" });
  chrome.action.setBadgeBackgroundColor({ color: "#f59e0b" });
}

async function patch(key, p) {
  const k = "st_" + key;
  const cur = (await chrome.storage.local.get(k))[k] || {};
  await chrome.storage.local.set({ [k]: { ...cur, ...p } });
}

async function api(cfg, path, method, body) {
  const res = await fetch(cfg.apiBase.replace(/\/$/, "") + "/api" + path, {
    method,
    headers: { "Content-Type": "application/json", "X-API-Token": cfg.apiToken },
    body: body ? JSON.stringify(body) : undefined
  });
  if (!res.ok) {
    let detail = await res.text();
    try { detail = JSON.parse(detail).detail || detail; } catch (e) {}
    throw new Error(`${res.status}: ${String(detail).slice(0, 300)}`);
  }
  return res.json();
}

async function scrapeTab(tabId) {
  const ask = () => chrome.tabs.sendMessage(tabId, { type: "SCRAPE" });
  try { return await ask(); }
  catch (e) {   // tab was open before the extension loaded: inject then retry
    await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] });
    return await ask();
  }
}

async function analyze(tabId, url) {
  const key = jobKeyFromUrl(url), cfg = await getCfg();
  await patch(key, { status: "running", step: "Reading the page (scrolling to load client history)…", error: null });
  try {
    const r = await scrapeTab(tabId);
    if (!r || !r.ok) throw new Error((r && r.error) || "Could not read the page");
    await patch(key, { step: "Running AI agent: rules, history, web research, verdict…" });
    const result = await api(cfg, "/analyze", "POST", { job: r.data, profile: cfg.profile, deep_research: cfg.deepResearch !== false });
    await patch(key, { status: "done", step: "", result, url });
  } catch (e) {
    await patch(key, { status: "error", error: String(e.message || e) });
  }
}

async function proposal(key, jobId, extra) {
  const cfg = await getCfg();
  await patch(key, { proposalStatus: "running", proposalError: null });
  try {
    const p = await api(cfg, `/jobs/${jobId}/proposal`, "POST", { profile: cfg.profile, extra_instructions: extra || "", deep_research: false });
    const cur = (await chrome.storage.local.get("st_" + key))["st_" + key] || {};
    const result = cur.result || {};
    result.proposals = [...(result.proposals || []), p];
    await patch(key, { proposalStatus: "done", result });
  } catch (e) {
    await patch(key, { proposalStatus: "error", proposalError: String(e.message || e) });
  }
}

async function outcome(key, jobId, status, notes) {
  const cfg = await getCfg();
  try {
    await api(cfg, `/jobs/${jobId}/outcome`, "POST", { status, notes: notes || "" });
    const cur = (await chrome.storage.local.get("st_" + key))["st_" + key] || {};
    if (cur.result) { cur.result.status = status; await patch(key, { result: cur.result, outcomeMsg: "Saved: " + status.replace("_", " ") }); }
  } catch (e) { await patch(key, { outcomeMsg: "Failed: " + e.message }); }
}

chrome.runtime.onMessage.addListener((msg, _sender, send) => {
  if (msg.type === "ANALYZE") { analyze(msg.tabId, msg.url); send({ started: true }); }
  else if (msg.type === "PROPOSAL") { proposal(msg.key, msg.jobId, msg.extra); send({ started: true }); }
  else if (msg.type === "OUTCOME") { outcome(msg.key, msg.jobId, msg.status, msg.notes); send({ started: true }); }
  return false;
});
