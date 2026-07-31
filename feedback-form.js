/**
 * Feedback social thread for earth_accessibility.html.
 * Human public feedback stays in feedback_threads; synthetic agent feedback stays
 * in agent_feedback_threads. The UI merges both for review and filters.
 */
(function (global) {
  "use strict";

  let els = null;
  let getDetailContext = () => null;
  let getCurrentUser = () => null;
  let supabaseUrl = "";
  let supabaseKey = "";
  let capitalizeKind = (kind) => String(kind || "");
  let onFeedbackRowsLoaded = () => {};
  let historyRequestId = 0;
  const VOTER_KEY = "jalanlens_feedback_voter_id";
  const LOCAL_LIKES_KEY = "jalanlens_feedback_local_likes";
  const filters = { source: "all", recency: "all", persona: "all" };

  function $(id) { return document.getElementById(id); }

  function headers(extra = {}) {
    return { ["api" + "key"]: supabaseKey, ["Author" + "ization"]: "Bearer " + supabaseKey, ...extra };
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function uuid() {
    if (global.crypto?.randomUUID) return global.crypto.randomUUID();
    return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) =>
      (Number(c) ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (Number(c) / 4)))).toString(16),
    );
  }

  function voterId() {
    let id = localStorage.getItem(VOTER_KEY);
    if (!id) {
      id = uuid();
      localStorage.setItem(VOTER_KEY, id);
    }
    return id;
  }

  function localLikes() {
    try { return new Set(JSON.parse(localStorage.getItem(LOCAL_LIKES_KEY) || "[]")); }
    catch (e) { return new Set(); }
  }

  function saveLocalLikes(set) { localStorage.setItem(LOCAL_LIKES_KEY, JSON.stringify([...set])); }

  function currentPersonaType() {
    const user = getCurrentUser?.() || {};
    return user.public_persona_type || user.persona_hint || user.metadata?.persona_type || user.metadata?.access_persona || "";
  }

  function fillTitleFromContext() {
    const ctx = getDetailContext() || {};
    const label = capitalizeKind(ctx.kind) || "Accessibility";
    els.title.value = `${label} issue${ctx.name ? ": " + ctx.name : ""}`;
  }

  function updateMeta() {
    const persona = currentPersonaType();
    els.meta.textContent = persona ? `Posting as ${publicUserName()} · persona ${persona.replaceAll("_", " ")}` : "";
  }

  function setHistory(message = "", visible = false) {
    if (!els.history) return;
    els.history.innerHTML = message;
    els.history.classList.toggle("visible", visible && !!message);
  }

  function close(clearStatus = false) {
    els.form.classList.remove("open");
    if (clearStatus) {
      els.status.textContent = "";
      els.status.className = "";
    }
  }

  function open() {
    els.form.classList.add("open");
    els.status.textContent = "";
    els.status.className = "";
    updateMeta();
    fillTitleFromContext();
    loadHistory();
    els.title.focus();
  }

  function onContextChange(changed) {
    updateMeta();
    if (changed) {
      els.status.textContent = "";
      els.status.className = "";
      fillTitleFromContext();
      els.body.value = "";
    }
    loadHistory();
  }

  async function lookupByExternalId(table, externalId) {
    if (!externalId) return null;
    const url = `${supabaseUrl}/rest/v1/${table}?select=id,external_id&external_id=eq.${encodeURIComponent(externalId)}&limit=1`;
    const r = await fetch(url, { headers: headers() });
    if (!r.ok) throw new Error(`Supabase ${table} ${r.status}`);
    const rows = await r.json();
    return rows?.[0] || null;
  }

  async function resolveContextIds(ctx) {
    let streetPartId = ctx.streetPartDbId;
    if (!streetPartId && ctx.streetPartExternalId) {
      const part = await lookupByExternalId("street_parts", ctx.streetPartExternalId);
      streetPartId = part?.id || null;
    }
    let featureId = null;
    if (ctx.featureExternalId) {
      const feat = await lookupByExternalId("accessibility_features", ctx.featureExternalId);
      featureId = feat?.id || null;
    }
    return { streetPartId, featureId };
  }

  async function fetchPublicFeedbackRows(streetPartId, featureId) {
    if (!streetPartId) return [];
    const filters = [
      "select=id,title,body,status,priority_score,created_at,updated_at,feature_id,street_part_id,source,public_user_external_id,public_user_name,persona_type",
      `street_part_id=eq.${encodeURIComponent(streetPartId)}`,
      "order=created_at.desc",
      "limit=80",
    ];
    if (featureId) filters.push(`or=(feature_id.eq.${encodeURIComponent(featureId)},feature_id.is.null)`);
    const r = await fetch(`${supabaseUrl}/rest/v1/feedback_threads?${filters.join("&")}`, { headers: headers() });
    if (!r.ok) throw new Error(`Supabase public feedback ${r.status}`);
    return (await r.json()).map((row) => ({ ...row, source: row.source || "public" }));
  }

  async function fetchAgentFeedbackRows(streetPartId, streetPartExternalId, featureId) {
    const idFilter = streetPartId
      ? `street_part_id=eq.${encodeURIComponent(streetPartId)}`
      : `street_part_external_id=eq.${encodeURIComponent(streetPartExternalId || "")}`;
    if (!streetPartId && !streetPartExternalId) return [];
    const parts = [
      "select=id,title,body,status,priority_score,severity,created_at,updated_at,feature_id,street_part_id,street_part_external_id,agent_external_id,agent_name,persona_type,event_type",
      idFilter,
      "order=created_at.desc",
      "limit=80",
    ];
    if (featureId) parts.push(`or=(feature_id.eq.${encodeURIComponent(featureId)},feature_id.is.null)`);
    const r = await fetch(`${supabaseUrl}/rest/v1/agent_feedback_threads?${parts.join("&")}`, { headers: headers() });
    if (!r.ok) throw new Error(`Supabase agent feedback ${r.status}`);
    return (await r.json()).map((row) => ({ ...row, source: "agent_simulation" }));
  }

  function friendlyDate(value) {
    if (!value) return "recent";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "recent";
    return d.toLocaleDateString([], { month: "short", day: "numeric" }) + " · " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function publicLabelText(value) {
    return String(value || "").replace(/Footpath\s+(\d{4})\b/g, (_, n) => `Footpath ${Number(n) + 1}`);
  }

  function recencyCutoff() {
    const now = Date.now();
    if (filters.recency === "today") return now - 24 * 60 * 60 * 1000;
    if (filters.recency === "3d") return now - 3 * 24 * 60 * 60 * 1000;
    if (filters.recency === "week") return now - 7 * 24 * 60 * 60 * 1000;
    return 0;
  }

  function applyFilters(rows) {
    const cutoff = recencyCutoff();
    return rows.filter((row) => {
      if (filters.source !== "all" && row.source !== filters.source) return false;
      if (filters.persona !== "all" && row.persona_type !== filters.persona) return false;
      if (cutoff) {
        const t = new Date(row.created_at || 0).getTime();
        if (!t || t < cutoff) return false;
      }
      return true;
    });
  }

  function ensureFilters() {
    if (els.filters) return;
    const wrap = document.createElement("div");
    wrap.id = "feedbackFilters";
    wrap.className = "feedback-filters";
    wrap.innerHTML = `
      <label>Source <select id="feedbackSourceFilter"><option value="all">All</option><option value="public">Public</option><option value="agent_simulation">Agents</option></select></label>
      <label>Recency <select id="feedbackRecencyFilter"><option value="all">All time</option><option value="today">Today</option><option value="3d">Past 3 days</option><option value="week">Past week</option></select></label>
      <label>Persona <select id="feedbackPersonaFilter"><option value="all">All personas</option></select></label>
    `;
    els.history.parentNode.insertBefore(wrap, els.history);
    els.filters = wrap;
    els.sourceFilter = wrap.querySelector("#feedbackSourceFilter");
    els.recencyFilter = wrap.querySelector("#feedbackRecencyFilter");
    els.personaFilter = wrap.querySelector("#feedbackPersonaFilter");
    els.sourceFilter.onchange = () => { filters.source = els.sourceFilter.value; renderLastRows(); };
    els.recencyFilter.onchange = () => { filters.recency = els.recencyFilter.value; renderLastRows(); };
    els.personaFilter.onchange = () => { filters.persona = els.personaFilter.value; renderLastRows(); };
  }

  let lastRows = [];

  function updatePersonaFilter(rows) {
    ensureFilters();
    const current = els.personaFilter.value || "all";
    const personas = [...new Set(rows.map((r) => r.persona_type).filter(Boolean))].sort();
    els.personaFilter.innerHTML = `<option value="all">All personas</option>` + personas.map((p) => `<option value="${escapeHtml(p)}">${escapeHtml(p.replaceAll("_", " "))}</option>`).join("");
    els.personaFilter.value = personas.includes(current) ? current : "all";
    filters.persona = els.personaFilter.value;
  }

  function renderRows(rows) {
    ensureFilters();
    updatePersonaFilter(rows);
    const visibleRows = applyFilters(rows);
    if (!visibleRows.length) {
      setHistory(`<div class="feedback-thread-head"><b>Feedback threads</b><small>0 shown / ${rows.length} total</small></div><div class="feedback-item"><span>No matching feedback for this filter.</span></div>`, true);
      return;
    }
    const liked = localLikes();
    const sourceCounts = rows.reduce((acc, row) => { acc[row.source] = (acc[row.source] || 0) + 1; return acc; }, {});
    const header = `<div class="feedback-thread-head"><b>Feedback threads</b><small>${visibleRows.length} shown · public ${sourceCounts.public || 0} · agents ${sourceCounts.agent_simulation || 0}</small></div>`;
    const items = visibleRows.map((row) => {
      const date = friendlyDate(row.created_at);
      const count = Math.max(0, Math.round(Number(row.priority_score || 0)));
      const isLiked = liked.has(row.id);
      const isAgent = row.source === "agent_simulation";
      const who = isAgent ? `${row.agent_name || "Agent"} · ${row.agent_external_id || "agent"}` : `${row.public_user_name || "Public user"}`;
      const persona = row.persona_type ? ` · ${row.persona_type.replaceAll("_", " ")}` : "";
      const badge = isAgent ? "agent" : "public";
      return `<div class="feedback-item ${escapeHtml(badge)}" data-thread-id="${escapeHtml(row.id)}"><b><em>${escapeHtml(badge)}</em> ${escapeHtml(publicLabelText(row.title))}</b><span>${escapeHtml(publicLabelText(row.body))}</span><div class="feedback-social-row"><button type="button" class="feedback-like${isLiked ? " liked" : ""}" data-thread-id="${escapeHtml(row.id)}" data-count="${count}">${isLiked ? "♥" : "♡"} ${count}</button><small>${escapeHtml(who)}${escapeHtml(persona)} · ${escapeHtml(date)}</small></div></div>`;
    }).join("");
    setHistory(`${header}${items}`, true);
    els.history.querySelectorAll(".feedback-like").forEach((button) => {
      button.onclick = () => likeThread(button.dataset.threadId, button);
    });
  }

  function renderLastRows() { renderRows(lastRows); }

  async function likeThread(threadId, button) {
    const liked = localLikes();
    if (liked.has(threadId)) return;
    const current = Number(button.dataset.count || 0);
    button.disabled = true;
    button.dataset.count = String(current + 1);
    button.classList.add("liked");
    button.textContent = `♥ ${current + 1}`;
    liked.add(threadId);
    saveLocalLikes(liked);
    try {
      await fetch(`${supabaseUrl}/rest/v1/feedback_votes`, {
        method: "POST",
        headers: headers({ "Content-Type": "application/json", Prefer: "return=minimal" }),
        body: JSON.stringify({ thread_id: threadId, user_id: voterId(), vote_type: "upvote" }),
      });
    } catch (e) {
      // Agent-feedback likes may not map to feedback_votes yet; keep local optimistic state.
    } finally {
      button.disabled = false;
    }
  }

  async function loadHistory() {
    if (!els?.history || !supabaseUrl || !supabaseKey) return;
    ensureFilters();
    const requestId = ++historyRequestId;
    const ctx = getDetailContext() || {};
    setHistory("Loading feedback threads…", true);
    try {
      const { streetPartId, featureId } = await resolveContextIds(ctx);
      if (requestId !== historyRequestId) return;
      if (!streetPartId && !ctx.streetPartExternalId) {
        setHistory("Feedback thread appears once this footpath is linked to Supabase.", true);
        return;
      }
      const [publicResult, agentResult] = await Promise.allSettled([
        fetchPublicFeedbackRows(streetPartId, featureId),
        fetchAgentFeedbackRows(streetPartId, ctx.streetPartExternalId, featureId),
      ]);
      if (requestId !== historyRequestId) return;
      const publicRows = publicResult.status === "fulfilled" ? publicResult.value : [];
      const localAgentRows = (global.__EARTH_ACCESSIBILITY_STATE?.liveAgentSnapshot?.agent_feedback_threads || [])
        .filter((row) => row.street_part_external_id === ctx.streetPartExternalId)
        .map((row, index) => ({ ...row, id: row.id || `local-agent-${ctx.streetPartExternalId}-${index}`, source: "agent_simulation" }));
      const agentRows = agentResult.status === "fulfilled" && agentResult.value.length ? agentResult.value : localAgentRows;
      lastRows = [...publicRows, ...agentRows].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
      onFeedbackRowsLoaded(lastRows, ctx);
      if (!lastRows.length) {
        const errors = [publicResult, agentResult].filter((r) => r.status === "rejected").map((r) => r.reason?.message || String(r.reason));
        setHistory(`<div class="feedback-thread-head"><b>Feedback threads</b><small>0 posts</small></div><div class="feedback-item"><span>No reports yet.${errors.length ? " Some live tables may not be migrated yet." : " Be the first to post feedback for this footpath."}</span></div>`, true);
        return;
      }
      renderRows(lastRows);
    } catch (err) {
      if (requestId !== historyRequestId) return;
      setHistory(`Could not load feedback threads: ${escapeHtml(err.message || String(err))}`, true);
    }
  }

  function publicUserName() {
    const user = getCurrentUser?.() || {};
    return user.display_name || user.username || user.external_id || "Public user";
  }

  async function submit(title, body) {
    const ctx = getDetailContext() || {};
    const { streetPartId, featureId } = await resolveContextIds(ctx);
    if (!streetPartId) throw new Error("No street_part match yet. Open a seeded demo corridor segment first.");
    const user = getCurrentUser?.() || {};
    const payload = {
      street_part_id: streetPartId,
      feature_id: featureId,
      title,
      body,
      created_by: null,
      source: "public",
      public_user_external_id: user.external_id || null,
      public_user_name: publicUserName(),
      persona_type: currentPersonaType() || null,
      status: "open",
      priority_score: 0,
    };
    const r = await fetch(`${supabaseUrl}/rest/v1/feedback_threads`, {
      method: "POST",
      headers: headers({ "Content-Type": "application/json", Prefer: "return=representation" }),
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(`Supabase feedback ${r.status}: ${await r.text()}`);
    return r.json();
  }

  function bindEvents() {
    els.openBtn.onclick = () => open();
    els.cancelBtn.onclick = () => close(true);
    els.form.onsubmit = async (e) => {
      e.preventDefault();
      const title = els.title.value.trim();
      const body = els.body.value.trim();
      if (!title || !body) return;
      els.submitBtn.disabled = true;
      els.status.className = "";
      els.status.textContent = "Submitting…";
      try {
        const rows = await submit(title, body);
        const row = Array.isArray(rows) ? rows[0] : rows;
        const ctx = getDetailContext() || {};
        els.status.className = "ok";
        els.status.textContent = row?.feature_id ? `Public feedback posted to feature thread.` : `Public feedback posted on footpath${ctx.featureExternalId ? " (feature not found in DB yet)" : ""}.`;
        els.title.value = "";
        els.body.value = "";
        await loadHistory();
        setTimeout(() => close(false), 900);
      } catch (err) {
        els.status.className = "err";
        els.status.textContent = err.message || String(err);
      } finally {
        els.submitBtn.disabled = false;
      }
    };
  }

  function init(options = {}) {
    getDetailContext = options.getDetailContext || (() => null);
    getCurrentUser = options.getCurrentUser || (() => null);
    supabaseUrl = options.supabaseUrl || "";
    supabaseKey = options.supabaseKey || "";
    if (typeof options.capitalizeKind === "function") capitalizeKind = options.capitalizeKind;
    if (typeof options.onFeedbackRowsLoaded === "function") onFeedbackRowsLoaded = options.onFeedbackRowsLoaded;
    const ids = {
      openBtn: "feedbackBtn",
      meta: "feedbackMeta",
      form: "feedbackForm",
      title: "feedbackTitle",
      body: "feedbackBody",
      submitBtn: "feedbackSubmitBtn",
      cancelBtn: "feedbackCancelBtn",
      status: "feedbackStatus",
      history: "feedbackHistory",
    };
    els = {};
    for (const [key, id] of Object.entries(ids)) {
      const el = $(id);
      if (!el) throw new Error(`EquirouteFeedback: missing #${id}`);
      els[key] = el;
    }
    bindEvents();
    ensureFilters();
    return api;
  }

  const api = { init, open, close, onContextChange, updateMeta, loadHistory };
  global.EquirouteFeedback = api;
})(typeof window !== "undefined" ? window : globalThis);
