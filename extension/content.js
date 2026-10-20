// Runs on upwork.com. Reads the job page the USER is viewing; never clicks Apply or submits anything.
(() => {
  if (window.__ujcLoaded) return;
  window.__ujcLoaded = true;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const text = (n) => (n && n.innerText ? n.innerText.trim() : "");
  const first = (sels, root = document) => {
    for (const s of sels) { const n = root.querySelector(s); if (n && text(n)) return n; }
    return null;
  };

  // Smallest element whose text matches ALL regexes: robust against Upwork renaming data-test attributes.
  function smallestContaining(regexes, root, maxLen = 5000) {
    let best = null, bestLen = Infinity;
    for (const el of root.querySelectorAll("section, div, ul, aside")) {
      const t = el.innerText || "";
      if (t.length < 20 || t.length > maxLen || t.length >= bestLen) continue;
      if (regexes.every((r) => r.test(t))) { best = el; bestLen = t.length; }
    }
    return best;
  }

  function scrollables() {
    return [...document.querySelectorAll("div, section, main")].filter(
      (e) => e.scrollHeight > e.clientHeight + 300 && /(auto|scroll)/.test(getComputedStyle(e).overflowY));
  }

  // Scroll so lazily loaded parts (client history, reviews) render, then restore position.
  async function loadEverything() {
    const boxes = [document.scrollingElement, ...scrollables()].filter(Boolean);
    const saved = boxes.map((b) => b.scrollTop);
    for (let i = 1; i <= 8; i++) {
      boxes.forEach((b) => (b.scrollTop = (b.scrollHeight / 8) * i));
      await sleep(250);
    }
    for (const b of document.querySelectorAll("button")) {   // expand truncated text only (buttons, never links)
      if (/^\s*(more|show more|view more|see more)\s*$/i.test(b.innerText || "")) { try { b.click(); } catch (e) {} await sleep(120); }
    }
    await sleep(300);
    boxes.forEach((b, i) => (b.scrollTop = saved[i]));
  }

  async function scrape() {
    await loadEverything();
    const root = first(['[data-test="job-details-slider"]', ".air3-slider-body", '[data-test="JobDetails"]', "main"]) || document.body;

    const title = text(first(["h1", '[data-test="job-title"]'], root)) || document.title.replace(/\s*-\s*Upwork.*$/i, "");
    const desc = text(first(['[data-test="Description"]', '[data-test="job-description-text"]', '[data-test="description"]'], root));
    const activity = smallestContaining([/Proposals/i, /Interviewing|Invites sent|Last viewed/i], root);
    const client = smallestContaining([/About the client/i, /total spent|jobs? posted|Member since/i], root, 6000)
      || smallestContaining([/total spent/i], root, 6000);
    const skills = [...new Set([...root.querySelectorAll('[data-test="Skill"], [data-test="skill-badge"], .air3-token, .skills-list a')]
      .map((n) => n.innerText.trim()).filter((t) => t && t.length < 40))].slice(0, 25);
    const loc = first(['[data-qa="client-location"] strong', '[data-test="LocationLabel"]'], root);
    const path = location.pathname;

    return {
      url: location.href,
      title,
      description: desc,
      raw_text: (root.innerText || "").slice(0, 24000),
      activity_text: text(activity),
      client_text: text(client),
      skills,
      country: text(loc),
      page_type: /\/apply/.test(path) ? "apply" : /\/search\/jobs|\/find-work/.test(path) ? "search" : "job",
      scraped_at: new Date().toISOString()
    };
  }

  function setValue(el, value) {
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set;
    setter.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  // Fills the cover letter box (and screening answers when the counts line up). The user reviews and clicks Send.
  function fill(coverLetter, answers) {
    const areas = [...document.querySelectorAll("textarea")].filter((t) => t.offsetParent !== null);
    if (!areas.length) return { ok: false, error: "No proposal form found. Open the Apply page for this job first." };
    const cover = areas.find((t) => /cover/i.test([t.getAttribute("aria-labelledby"), t.name, t.id, t.placeholder].join(" ")))
      || [...areas].sort((a, b) => b.offsetHeight - a.offsetHeight)[0];
    setValue(cover, coverLetter);
    const others = areas.filter((t) => t !== cover);
    let filled = 0;
    if (answers && answers.length && others.length === answers.length) {
      answers.forEach((a, i) => { setValue(others[i], a); filled++; });
    }
    return { ok: true, answers_filled: filled };
  }

  chrome.runtime.onMessage.addListener((msg, _s, send) => {
    if (msg.type === "SCRAPE") { scrape().then((d) => send({ ok: true, data: d })).catch((e) => send({ ok: false, error: String(e) })); return true; }
    if (msg.type === "FILL") { send(fill(msg.text, msg.answers)); }
  });
})();
