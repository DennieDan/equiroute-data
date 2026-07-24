/**
 * Feedback form for EquiRoute Earth (shared UI).
 * Bind with EquirouteFeedback.init({ getDetailContext, supabaseUrl, supabaseKey, capitalizeKind }).
 */
(function (global) {
  "use strict";

  let els = null;
  let getDetailContext = () => null;
  let supabaseUrl = "";
  let supabaseKey = "";
  let capitalizeKind = (kind) => String(kind || "");

  function $(id) {
    return document.getElementById(id);
  }

  function fillTitleFromContext() {
    const ctx = getDetailContext() || {};
    const label = capitalizeKind(ctx.kind) || "Accessibility";
    els.title.value = `${label} issue${ctx.name ? ": " + ctx.name : ""}`;
  }

  function updateMeta() {
    const ctx = getDetailContext() || {};
    const bits = [];
    if (ctx.streetPartExternalId)
      bits.push(`street part ${ctx.streetPartExternalId}`);
    if (ctx.featureExternalId) bits.push(`feature ${ctx.featureExternalId}`);
    else if (ctx.kind) bits.push(`${ctx.kind} (street-part only)`);
    else bits.push("street-part only");
    els.meta.textContent = bits.join(" · ");
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
    }
  }

  async function lookupByExternalId(table, externalId) {
    if (!externalId) return null;
    const url = `${supabaseUrl}/rest/v1/${table}?select=id,external_id&external_id=eq.${encodeURIComponent(externalId)}&limit=1`;
    const r = await fetch(url, {
      headers: {
        apikey: supabaseKey,
        Authorization: "Bearer " + supabaseKey,
      },
    });
    if (!r.ok) throw new Error(`Supabase ${table} ${r.status}`);
    const rows = await r.json();
    return rows?.[0] || null;
  }

  async function submit(title, body) {
    const ctx = getDetailContext() || {};
    let streetPartId = ctx.streetPartDbId;
    if (!streetPartId && ctx.streetPartExternalId) {
      const part = await lookupByExternalId(
        "street_parts",
        ctx.streetPartExternalId,
      );
      streetPartId = part?.id || null;
    }
    if (!streetPartId) {
      throw new Error(
        "No street_part match yet. Open a seeded demo corridor segment first.",
      );
    }
    let featureId = null;
    if (ctx.featureExternalId) {
      const feat = await lookupByExternalId(
        "accessibility_features",
        ctx.featureExternalId,
      );
      featureId = feat?.id || null;
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
      headers: {
        apikey: supabaseKey,
        Authorization: "Bearer " + supabaseKey,
        "Content-Type": "application/json",
        Prefer: "return=representation",
      },
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
  };

  global.EquirouteFeedback = api;
})(typeof window !== "undefined" ? window : globalThis);
