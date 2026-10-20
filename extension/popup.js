const app = document.getElementById("app");
let tab, key, cfg, st = {};

function h(tag, props = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "style") e.style.cssText = v;
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const k of kids.flat()) { if (k == null || k === false) continue; e.append(k.nodeType ? k : document.createTextNode(String(k))); }
  return e;
}
const send = (m) => chrome.runtime.sendMessage(m);
const color = (v, invert) => `hsl(${Math.round((invert ? 100 - v : v) * 1.2)},70%,45%)`;
const tile = (label, v, invert) => h("div", { class: "tile" }, h("div", { class: "n" }, v == null ? "–" : v), h("div", { class: "l" }, label),
  h("div", { class: "bar" }, h("i", { style: `width:${v || 0}%;background:${color(v || 0, invert)}` })));
const list = (items) => items && items.length ? h("ul", {}, items.map((x) => h("li", {}, x))) : h("div", { class: "muted" }, "None");
const copy = async (t, btn) => { await navigator.clipboard.writeText(t); const o = btn.textContent; btn.textContent = "Copied ✓"; setTimeout(() => (btn.textContent = o), 1200); };

function header() {
  return h("div", { class: "top" }, h("div", { class: "brand" }, "🎯 Upwork Job Copilot"),
    h("button", { class: "ghost small", onclick: () => chrome.runtime.openOptionsPage() }, "⚙ Settings"));
}

function render() {
  app.replaceChildren(header());
  if (!isConfigured(cfg)) {
    app.append(h("p", {}, "Finish setup first: backend URL, backend token and your profile."),
      h("button", { onclick: () => chrome.runtime.openOptionsPage() }, "Open settings"));
    return;
  }
  if (!isUpworkUrl(tab.url)) { app.append(h("p", { class: "muted" }, "Open an Upwork job page, then click the icon again.")); return; }

  const running = st.status === "running";
  app.append(h("button", { style: "width:100%", disabled: running, onclick: start },
    running ? [h("span", { class: "spin" }), st.step || "Working…"] : st.result ? "↻ Re-analyze this job" : "▶ Start: analyze this job"));
  if (st.status === "error") app.append(h("div", { class: "err" }, st.error));
  if (st.result) renderResult(st.result);
}

function renderResult(r) {
  const a = r.analysis || {}, ru = r.rules || {}, p = r.parsed || {};
  app.append(
    h("div", { class: "title", style: "margin-top:12px" }, r.title || "Job"),
    h("div", { class: `banner ${a.verdict}` },
      h("div", { class: "v" }, `${a.verdict === "APPLY" ? "✅ APPLY" : a.verdict === "MAYBE" ? "🤔 MAYBE" : "⛔ SKIP"}  ·  ${a.overall}/100`),
      h("div", {}, a.summary), a.verdict_override && h("div", { class: "muted", style: "margin-top:4px" }, "Override: " + a.verdict_override)),
    h("div", { class: "grid" },
      tile("Reply chance", a.response_chance), tile("Win chance", a.win_chance), tile("Profile fit", a.profile_fit),
      tile("Competition", ru.competition), tile("Client quality", ru.client_quality), tile("Fake risk", ru.fake_risk, true)),
    h("details", { open: true }, h("summary", {}, "Why apply"), list(a.reasons_apply), a.best_angle && h("p", {}, h("b", {}, "Angle: "), a.best_angle),
      a.suggested_bid && h("p", {}, h("b", {}, "Bid: "), a.suggested_bid)),
    h("details", { open: (a.red_flags || []).length > 0 }, h("summary", {}, `Red flags (${(a.red_flags || []).length})`), list(a.red_flags)),
    h("details", {}, h("summary", {}, `Signals checked (${(ru.signals || []).length})`),
      h("ul", { class: "sig" }, (ru.signals || []).map((s) => h("li", {}, h("span", { class: `dot ${s.level}` }), h("div", {}, h("b", {}, s.name), s.detail ? " – " + s.detail : ""))))),
    h("details", {}, h("summary", {}, "Couldn't verify"), list(a.missing_info)),
    r.research && h("details", {}, h("summary", {}, "Web research"), h("div", { style: "white-space:pre-wrap;margin-top:6px" }, r.research)),
    h("details", {}, h("summary", {}, "Your history"),
      h("p", {}, `Applied: ${r.stats.applied} · Hired: ${r.stats.hired} · Win rate: ${r.stats.win_rate_pct ?? "–"}% · Reply rate: ${r.stats.reply_rate_pct ?? "–"}%`),
      list((r.similar || []).map((s) => `${s.title} → ${s.status}`)))
  );
  renderProposal(r);
  renderOutcome(r);
}

function renderProposal(r) {
  const props = r.proposals || [], last = props[props.length - 1];
  const busy = st.proposalStatus === "running";
  const box = h("div", { style: "margin-top:12px" }, h("h3", {}, "Proposal"));
  const extra = h("input", { placeholder: "Optional note, e.g. 'mention my Django project' / 'shorter'" });
  box.append(h("div", { class: "row" }, h("button", { disabled: busy, onclick: () => genProposal(r.job_id, extra.value) },
    busy ? [h("span", { class: "spin" }), "Writing…"] : last ? (["rejected", "no_response"].includes(last.outcome) ? "↻ Improve (learn from last result)" : "↻ New version") : "✍ Write proposal")));
  box.append(h("div", { style: "margin-top:6px" }, extra));
  if (st.proposalStatus === "error") box.append(h("div", { class: "err" }, st.proposalError));
  if (last) {
    const ta = h("textarea", { rows: 14 }); ta.value = last.text;
    const cnt = h("div", { class: "cnt" }, `${last.text.length} chars · v${last.version} · hook: ${(last.hook || "").slice(0, 50)}…`);
    ta.addEventListener("input", () => (cnt.textContent = `${ta.value.length} chars (edited)`));
    box.append(h("div", { style: "margin-top:8px" }, ta, cnt),
      h("div", { class: "row" },
        h("button", { class: "small", onclick: (e) => copy(ta.value, e.target) }, "Copy"),
        h("button", { class: "small ghost", onclick: () => fillForm(ta.value, last) }, "Insert into Apply form")),
      last.meta?.what_changed && h("p", { class: "muted" }, "Changed: " + last.meta.what_changed),
      (last.meta?.quality_issues || []).length ? h("div", { class: "err" }, "Quality checks still failing: " + last.meta.quality_issues.join(" | ")) : null,
      last.meta?.suggested_bid && h("p", {}, h("b", {}, "Suggested bid: "), last.meta.suggested_bid));
    (last.answers || []).forEach((qa) => box.append(h("div", { class: "qa" }, h("b", {}, qa.question), h("div", { style: "margin:4px 0" }, qa.answer),
      h("button", { class: "small ghost", onclick: (e) => copy(qa.answer, e.target) }, "Copy answer"))));
  }
  app.append(box);
}

function renderOutcome(r) {
  const opts = [["applied", "I applied"], ["interviewing", "Got interview"], ["hired", "Hired 🎉"], ["rejected", "Rejected"], ["no_response", "No reply"], ["skipped", "Skipped"]];
  app.append(h("div", { style: "margin-top:12px" }, h("h3", {}, "Track result"), h("div", { class: "muted" }, "Current: " + (r.status || "analyzed").replace("_", " ")),
    h("div", { class: "row" }, opts.map(([s, l]) => h("button", { class: `small ${r.status === s ? "" : "ghost"}`, onclick: () => send({ type: "OUTCOME", key, jobId: r.job_id, status: s }) }, l))),
    st.outcomeMsg && h("div", { class: "muted", style: "margin-top:4px" }, st.outcomeMsg),
    h("div", { class: "muted", style: "margin-top:4px" }, "Rejected / no reply makes the next proposal for similar jobs learn from this one.")));
}

async function start() { await send({ type: "ANALYZE", tabId: tab.id, url: tab.url }); }
async function genProposal(jobId, extra) { await send({ type: "PROPOSAL", key, jobId, extra }); }
async function fillForm(text, p) {
  try {
    const r = await chrome.tabs.sendMessage(tab.id, { type: "FILL", text, answers: (p.answers || []).map((a) => a.answer) });
    alert(r.ok ? "Inserted. Review it and press Send yourself." + (r.answers_filled ? ` (${r.answers_filled} answers filled)` : "") : r.error);
  } catch (e) { alert("Open the job's Apply page first (the proposal form must be visible)."); }
}

(async function init() {
  cfg = (await chrome.storage.local.get("cfg")).cfg || {};
  [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  key = jobKeyFromUrl(tab.url);
  st = (await chrome.storage.local.get("st_" + key))["st_" + key] || {};
  render();
  chrome.storage.onChanged.addListener((c) => {
    if (c["st_" + key]) { st = c["st_" + key].newValue || {}; render(); }
  });
})();
