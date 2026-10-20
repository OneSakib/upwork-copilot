const $ = (id) => document.getElementById(id);
const csv = (s) => s.split(",").map((x) => x.trim()).filter(Boolean);
const lines = (s) => s.split("\n").map((x) => x.trim()).filter(Boolean);
const num = (s) => (s === "" ? null : Number(s));
const msg = (t, ok) => { const m = $("msg"); m.textContent = t; m.className = ok ? "ok" : "err"; };

const LIST_CSV = ["skills", "tools", "preferred_countries", "banned_words"];
const LIST_LINES = ["past_projects", "case_study_links", "portfolio_links", "hooks"];
const TEXT = ["name", "title", "country", "summary", "niche", "tone_notes", "signature"];
const NUM = ["years_experience", "hourly_rate", "min_fixed_budget"];

(async function load() {
  const cfg = (await chrome.storage.local.get("cfg")).cfg || {};
  const p = cfg.profile || {};
  $("apiBase").value = cfg.apiBase || "http://localhost:8000";
  $("apiToken").value = cfg.apiToken || "";
  $("deepResearch").checked = cfg.deepResearch !== false;
  TEXT.forEach((k) => ($(k).value = p[k] || ""));
  NUM.forEach((k) => ($(k).value = p[k] ?? ""));
  LIST_CSV.forEach((k) => ($(k).value = (p[k] || (k === "banned_words" ? DEFAULT_BANNED : k === "preferred_countries" ? ["United States"] : [])).join(", ")));
  LIST_LINES.forEach((k) => ($(k).value = (p[k] || (k === "hooks" ? DEFAULT_HOOKS : [])).join("\n")));
})();

$("save").onclick = async () => {
  const profile = {};
  TEXT.forEach((k) => (profile[k] = $(k).value.trim()));
  NUM.forEach((k) => (profile[k] = num($(k).value)));
  profile.min_fixed_budget = profile.min_fixed_budget || 0;
  LIST_CSV.forEach((k) => (profile[k] = csv($(k).value)));
  LIST_LINES.forEach((k) => (profile[k] = lines($(k).value)));
  const cfg = { apiBase: $("apiBase").value.trim().replace(/\/$/, ""), apiToken: $("apiToken").value.trim(),
    deepResearch: $("deepResearch").checked, profile };
  if (!isConfigured(cfg)) return msg("Please fill backend URL, backend token, summary and at least one skill.", false);
  try {   // ask Chrome for permission to call a non-localhost backend
    const origin = new URL(cfg.apiBase).origin + "/*";
    if (!/localhost|127\.0\.0\.1/.test(origin)) await chrome.permissions.request({ origins: [origin] });
  } catch (e) { return msg("Backend URL is not valid.", false); }
  await chrome.storage.local.set({ cfg });
  msg("Saved ✓  Setup complete. Pin the extension icon (puzzle piece → pin), open an Upwork job and click Start.", true);
};

$("test").onclick = async () => {
  try {
    const r = await fetch($("apiBase").value.trim().replace(/\/$/, "") + "/api/ping", { headers: { "X-API-Token": $("apiToken").value.trim() } });
    msg(r.ok ? "Backend and database reachable ✓" : `Backend answered ${r.status} (check the token)`, r.ok);
  } catch (e) { msg("Cannot reach the backend. Is it running, and did you allow its URL?", false); }
};
