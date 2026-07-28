/**
 * Feedback form for earth_accessibility.html.
 * Bind with EquirouteFeedback.init({ getDetailContext, supabaseUrl, supabaseKey, capitalizeKind }).
 */
(function (global) {
  "use strict";

  let els = null;
  let getDetailContext = () => null;
  let supabaseUrl = "";
  let supabaseKey = "";
  let capitalizeKind = (kind) => String(kind || "");
  let historyRequestId = 0;

  function $(id) {
    return document.getElementById(id);
  }

  function headers(extra = {}) {
    return {
      apikey: supabaseKey,
      Authorization: "Bearer " + supabaseKey,
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

  function fillTitleFromContext() {
    const ctx = getDetailContext() || {};
    const label = capitalizeKind(ctx.kind) || "Accessibility";
    els.title.value = `${label} issue${ctx.name ? ": " + ctx.name : ""}`;
  }

  function updateMeta() {
    // Public scorecard should not expose internal IDs like
    // "street part street_part_0000 · feature covered_linkway_3399".
    // IDs are still kept in detailContext for feedback submission.
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

  /** Call when detailContext changes. If `changed`, resets draft fields. */
  function onContextChange(changed) {
    updateMeta();
    if (changed) {
      els.status.textContent = "";
      els.status.className = "";
      fillTitleFromContext();
      els.body.value = "";
      loadHistory();
    }
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
      "select=id,title,body,status,priority_score,created_at,feature_id,street_part_id",
      `street_part_id=eq.${encodeURIComponent(streetPartId)}`,
      "order=created_at.desc",
      "limit=20",
    ];
    if (featureId) filters.push(`or=(feature_id.eq.${encodeURIComponent(featureId)},feature_id.is.null)`);
    const url = `${supabaseUrl}/rest/v1/feedback_threads?${filters.join("&")}`;
    const r = await fetch(url, { headers: headers() });
    if (!r.ok) throw new Error(`Supabase feedback history ${r.status}`);
    return r.json();
  }

  async function loadHistory() {
    if (!els?.history || !supabaseUrl || !supabaseKey) return;
    const requestId = ++historyRequestId;
    const ctx = getDetailContext() || {};
    setHistory("Loading past feedback…", true);
    try {
      const { streetPartId, featureId } = await resolveContextIds(ctx);
      if (requestId !== historyRequestId) return;
      if (!streetPartId) {
        setHistory("Past feedback appears once this street part is linked to Supabase.", true);
        return;
      }
      const rows = await fetchFeedbackRows(streetPartId, featureId);
      if (requestId !== historyRequestId) return;
      if (!rows.length) {
        setHistory("No past feedback for this selected feature/street part yet.", true);
        return;
      }
      const featureSpecific = rows.filter((row) => featureId && row.feature_id === featureId).length;
      const header = featureId
        ? `<b>Past feedback</b> · ${featureSpecific} feature-specific · ${rows.length} total on this street part`
        : `<b>Past feedback</b> · ${rows.length} thread${rows.length === 1 ? "" : "s"} on this street part`;
      const items = rows
        .map((row) => {
          const date = row.created_at ? new Date(row.created_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "recent";
          const scope = row.feature_id ? "feature" : "street part";
          return `<div class="feedback-item"><b>${escapeHtml(row.title)}</b><span>${escapeHtml(row.body)}</span><small>${escapeHtml(scope)} · ${escapeHtml(row.status)} · ${escapeHtml(date)}</small></div>`;
        })
        .join("");
      setHistory(`${header}${items}`, true);
    } catch (err) {
      if (requestId !== historyRequestId) return;
      setHistory(`Could not load past feedback: ${escapeHtml(err.message || String(err))}`, true);
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
          ? `Feedback saved and linked to feature.`
          : `Feedback saved on street part${ctx.featureExternalId ? " (feature not found in DB yet)" : ""}.`;
        els.title.value = "";
        els.body.value = "";
        await loadHistory();
        setTimeout(() => close(false), 1200);
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
