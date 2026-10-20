// Shared by popup, options and the service worker.
const DEFAULT_HOOKS = [
  "Let's make this the last proposal you need to read today. I have attached a work sample that matches what you're looking for.",
  "I believe a good proposal should make sense, not noise. So let's get straight to the point.",
  "If you are tired of long explanations, you will love how simple I make it."
];
const DEFAULT_BANNED = ["tailored", "deliver", "ensuring", "embrace", "data-driven"];

function jobKeyFromUrl(url) {
  const m = /~(0\d{15,})/.exec(url || "");
  return m ? "job_" + m[1] : "url_" + (url || "").split(/[?#]/)[0];
}
function isConfigured(cfg) {
  const p = (cfg && cfg.profile) || {};
  return !!(cfg && cfg.apiBase && cfg.apiToken && p.summary && (p.skills || []).length);
}
function isUpworkUrl(url) { return /^https:\/\/www\.upwork\.com\//.test(url || ""); }
