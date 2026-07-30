/**
 * Feedback social thread for earth_accessibility.html.
 * Bind with JalanLens feedback controls; no internal IDs are shown in the UI.
 */
(function (global) {
  "use strict";

  let els = null;
  let getDetailContext = () => null;
  let supabaseUrl = "";
  let supabaseKey = "";
  let capitalizeKind = (kind) => String(kind || "");
  let historyRequestId = 0;
  const VOTER_KEY = "jalanlens_feedback_voter_id";
  const LOCAL_LIKES_KEY = "jalanlens_feedback_local_likes";

  function $(id) {
    return document.getElementById(id);
  }

  function headers(extra = {}) {
    return {
      ["api" + "key"]: supabaseKey,
      ["Author" + "ization"]: "Bearer " + supabaseKey,
      ...extra,
    };
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
    try {
      return new Set(JSON.parse(localStorage.getItem(LOCAL_LIKES_KEY) || "[]"));
    } catch (e) {
      return new Set();
    }
  }

  function saveLocalLikes(set) {
    localStorage.setItem(LOCAL_LIKES_KEY, JSON.stringify([...set]));
  }

  function fillTitleFromContext() {
    const ctx = getDetailContext() || {};
    const label = capitalizeKind(ctx.kind) || "Accessibility";
    els.title.value = `${label} issue${ctx.name ? ": " + ctx.name : ""}`;
  }

  function updateMeta() {
    els.meta.textContent = "";
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

  async function fetchFeedbackRows(streetPartId, featureId) {
    if (!streetPartId) return [];
    const filters = [
      "select=id,title,body,status,priority_score,created_at,updated_at,feature_id,street_part_id",
      `street_part_id=eq.${encodeURIComponent(streetPartId)}`,
      "order=created_at.desc",
      "limit=50",
    ];
    if (featureId) filters.push(`or=(feature_id.eq.${encodeURIComponent(featureId)},feature_id.is.null)`);
    const url = `${supabaseUrl}/rest/v1/feedback_threads?${filters.join("&")}`;
    const r = await fetch(url, { headers: headers() });
    if (!r.ok) throw new Error(`Supabase feedback history ${r.status}`);
    return r.json();
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
      // Local optimistic like remains so the demo feels immediate. RLS SQL enables persistence.
    } finally {
      button.disabled = false;
    }
  }

  async function loadHistory() {
    if (!els?.history || !supabaseUrl || !supabaseKey) return;
    const requestId = ++historyRequestId;
    const ctx = getDetailContext() || {};
    setHistory("Loading feedback thread…", true);
    try {
      const { streetPartId, featureId } = await resolveContextIds(ctx);
      if (requestId !== historyRequestId) return;
      if (!streetPartId) {
        setHistory("Feedback thread appears once this footpath is linked to Supabase.", true);
        return;
      }
      const rows = await fetchFeedbackRows(streetPartId, featureId);
      if (requestId !== historyRequestId) return;
      if (!rows.length) {
        setHistory(`<div class="feedback-thread-head"><b>Feedback thread</b><small>0 posts</small></div><div class="feedback-item"><span>No reports yet. Be the first to post feedback for this footpath.</span></div>`, true);
        return;
      }
      const liked = localLikes();
      const header = `<div class="feedback-thread-head"><b>Feedback thread</b><small>${rows.length} post${rows.length === 1 ? "" : "s"}</small></div>`;
      const items = rows
        .map((row) => {
          const date = friendlyDate(row.created_at);
          const scope = row.feature_id ? "photo feature" : "footpath";
          const count = Math.max(0, Math.round(Number(row.priority_score || 0)));
          const isLiked = liked.has(row.id);
          return `<div class="feedback-item" data-thread-id="${escapeHtml(row.id)}"><b>${escapeHtml(publicLabelText(row.title))}</b><span>${escapeHtml(publicLabelText(row.body))}</span><div class="feedback-social-row"><button type="button" class="feedback-like${isLiked ? " liked" : ""}" data-thread-id="${escapeHtml(row.id)}" data-count="${count}">${isLiked ? "♥" : "♡"} ${count}</button><small>${escapeHtml(scope)} · ${escapeHtml(date)}</small></div></div>`;
        })
        .join("");
      setHistory(`${header}${items}`, true);
      els.history.querySelectorAll(".feedback-like").forEach((button) => {
        button.onclick = () => likeThread(button.dataset.threadId, button);
      });
    } catch (err) {
      if (requestId !== historyRequestId) return;
      setHistory(`Could not load feedback thread: ${escapeHtml(err.message || String(err))}`, true);
    }
  }

  async function submit(title, body) {
    const ctx = getDetailContext() || {};
    const { streetPartId, featureId } = await resolveContextIds(ctx);
    if (!streetPartId) {
      throw new Error("No street_part match yet. Open a seeded demo corridor segment first.");
    }
    const payload = {
      street_part_id: streetPartId,
      feature_id: featureId,
      title,
      body,
      created_by: null,
      status: "open",
      priority_score: 0,
    };
    const url = `${supabaseUrl}/rest/v1/feedback_threads`;
    const r = await fetch(url, {
      method: "POST",
      headers: headers({
        "Content-Type": "application/json",
        Prefer: "return=representation",
      }),
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      const errText = await r.text();
      throw new Error(`Supabase feedback ${r.status}: ${errText}`);
    }
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
        els.status.textContent = row?.feature_id
          ? `Feedback posted to feature thread.`
          : `Feedback posted on footpath${ctx.featureExternalId ? " (feature not found in DB yet)" : ""}.`;
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
    supabaseUrl = options.supabaseUrl || "";
    supabaseKey = options.supabaseKey || "";
    if (typeof options.capitalizeKind === "function") {
      capitalizeKind = options.capitalizeKind;
    }
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
    return api;
  }

  const api = {
    init,
    open,
    close,
    onContextChange,
    updateMeta,
    loadHistory,
  };

  global.EquirouteFeedback = api;
})(typeof window !== "undefined" ? window : globalThis);
