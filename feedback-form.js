/**
 * Feedback social thread for street-intelligence/.
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
  const REPLY_DRAFT_PREFIX = "jalanlens_reply_draft_";
  const AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1";
  const AGNES_TRANSLATION_MODEL = "agnes-2.5-flash";
  const AGNES_TRANSCRIPTION_MODEL = "agnes-2.5-flash";
  const AGNES_KEY_STORAGE = "jalanlens_agnes_api_key";
  const SUPPORTED_FEEDBACK_LANGUAGES = ["en", "zh-Hant", "zh-Hans", "ms", "ta", "bn", "gu"];
  const languageLabels = {
    en: "English",
    "zh-Hant": "Traditional Chinese",
    "zh-Hans": "Simplified Chinese",
    ms: "Malay",
    ta: "Tamil",
    bn: "Bengali",
    gu: "Gujarati",
    unknown: "Unknown",
  };
  let translationState = { language: "en", english: "", status: "not_required", provider: null, model: null };
  let translationTimer = null;
  let mediaRecorder = null;
  let audioChunks = [];
  let speechRecognition = null;
  let speechTranscriptOriginal = "";
  let inputModality = "typed";
  let activeSpeechTarget = null;
  let browserFinalTranscripts = new Map();
  let browserInterimTranscript = "";

  function micIconSvg() {
    return '<svg viewBox="0 0 24 24" role="img" focusable="false"><path d="M12 14.5a3.2 3.2 0 0 0 3.2-3.2V6.2a3.2 3.2 0 1 0-6.4 0v5.1a3.2 3.2 0 0 0 3.2 3.2Zm5.6-3.2a.9.9 0 0 0-1.8 0 3.8 3.8 0 0 1-7.6 0 .9.9 0 0 0-1.8 0 5.6 5.6 0 0 0 4.7 5.52v2.08H8.9a.9.9 0 1 0 0 1.8h6.2a.9.9 0 1 0 0-1.8h-2.2v-2.08a5.6 5.6 0 0 0 4.7-5.52Z"/></svg>';
  }

  function setSpeechIcon(recording = false) {
    if (!els?.speechLabel) return;
    els.speechLabel.innerHTML = recording ? "⏹" : micIconSvg();
  }

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
    const role = authorRole();
    if (!els.meta) return;
    if (role === "authority") {
      els.meta.textContent = persona ? `Posting as ${publicUserName()} · persona ${persona.replaceAll("_", " ")}` : `Posting as ${publicUserName()}`;
    } else {
      els.meta.textContent = `Posting as ${publicUserName()}`;
    }
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
    els.body.focus();
  }

  function onContextChange(changed) {
    updateMeta();
    if (changed) {
      els.status.textContent = "";
      els.status.className = "";
      fillTitleFromContext();
      els.body.value = "";
      els.body.dataset.detectedLanguage = "";
      speechTranscriptOriginal = "";
      inputModality = "typed";
      translationState = { language: "en", english: "", status: "not_required", provider: null, model: null };
      renderTranslationBox();
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
      "select=id,title,body,status,priority_score,created_at,updated_at,feature_id,street_part_id,source,public_user_external_id,public_user_name,persona_type,original_language,english_translation,translation_provider,translation_model,input_modality",
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

  async function fetchUserVoteThreadIds(rows) {
    const ids = rows.filter((row) => row.source !== "agent_simulation" && isUuid(row.id)).map((row) => row.id);
    if (!ids.length) return new Set();
    const r = await fetch(`${supabaseUrl}/rest/v1/feedback_votes?select=thread_id&thread_id=in.(${ids.map(encodeURIComponent).join(",")})&user_id=eq.${encodeURIComponent(voterId())}`, { headers: headers() });
    if (!r.ok) return new Set();
    return new Set((await r.json()).map((row) => row.thread_id));
  }

  async function fetchFeedbackReplies(rows) {
    const publicIds = rows.filter((r) => r.source !== "agent_simulation" && isUuid(r.id)).map((r) => r.id);
    const agentIds = rows.filter((r) => r.source === "agent_simulation" && isUuid(r.id)).map((r) => r.id);
    if (!publicIds.length && !agentIds.length) return new Map();
    const queries = [];
    const select = "select=id,parent_source,parent_thread_id,parent_agent_thread_id,author_role,author_external_id,author_name,body,original_language,english_translation,translation_status,input_modality,created_at&order=created_at.asc&limit=500";
    if (publicIds.length) queries.push(fetch(`${supabaseUrl}/rest/v1/feedback_replies?${select}&parent_thread_id=in.(${publicIds.map(encodeURIComponent).join(",")})`, { headers: headers() }));
    if (agentIds.length) queries.push(fetch(`${supabaseUrl}/rest/v1/feedback_replies?${select}&parent_agent_thread_id=in.(${agentIds.map(encodeURIComponent).join(",")})`, { headers: headers() }));
    const settled = await Promise.allSettled(queries);
    const replies = [];
    for (const result of settled) {
      if (result.status !== "fulfilled") continue;
      if (!result.value.ok) continue;
      replies.push(...await result.value.json());
    }
    const byParent = new Map();
    for (const reply of replies) {
      const key = `${reply.parent_source === "agent_simulation" ? "agent_simulation" : "public"}:${reply.parent_source === "agent_simulation" ? reply.parent_agent_thread_id : reply.parent_thread_id}`;
      if (!byParent.has(key)) byParent.set(key, []);
      byParent.get(key).push(reply);
    }
    return byParent;
  }

  function friendlyDate(value) {
    if (!value) return "recent";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "recent";
    const weekday = d.toLocaleDateString("en-SG", { weekday: "short" });
    const day = d.getDate();
    const month = d.toLocaleDateString("en-SG", { month: "long" });
    const year = d.getFullYear();
    const hour24 = d.getHours();
    const hour = hour24 % 12 || 12;
    const minute = String(d.getMinutes()).padStart(2, "0");
    const suffix = hour24 >= 12 ? "pm" : "am";
    return `${weekday}, ${day} ${month} ${year}, ${hour}.${minute}${suffix}`;
  }

  function publicLabelText(value) {
    return String(value || "").replace(/Footpath\s+(\d{4})\b/g, (_, n) => `Footpath ${Number(n) + 1}`);
  }

  function cleanThreadTitle(value) {
    return publicLabelText(value)
      .replace(/\s*[·•-]\s*Footpath\s+\d+\b/gi, "")
      .replace(/\s*\(?(?:near\s+)?Footpath\s+\d+\)?\s*$/gi, "")
      .trim();
  }

  function isAuthorityUser() { return authorRole() === "authority"; }

  function writerNameForRow(row) {
    if (row.source === "agent_simulation") return row.agent_name || "Agent";
    if (row.source === "authority") return row.public_user_name || row.author_name || "Authority";
    return row.public_user_name || row.author_name || "Public";
  }

  function writerNameForReply(reply) {
    const role = reply.author_role || "public";
    return reply.author_name || (role === "authority" ? "Authority" : "Public");
  }

  function sourceLabel(source) {
    if (source === "authority") return "Authority";
    if (source === "agent_simulation") return "Agent";
    if (source === "agent") return "Agent";
    if (source === "system") return "System";
    return "Public";
  }

  function authorRole() {
    const user = getCurrentUser?.() || {};
    return user.role === "authority" ? "authority" : "public";
  }

  function threadKey(row) {
    return `${row.source === "agent_simulation" ? "agent_simulation" : "public"}:${row.id}`;
  }

  function isUuid(value) {
    return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(String(value || ""));
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
    if (els.filters) {
      els.filters.hidden = !isAuthorityUser();
      return;
    }
    const wrap = document.createElement("div");
    wrap.id = "feedbackFilters";
    wrap.className = "feedback-filters";
    wrap.innerHTML = `
      <label>Source <select id="feedbackSourceFilter"><option value="all">All</option><option value="public">Public</option><option value="authority">Authority</option><option value="agent_simulation">Agents</option></select></label>
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
    els.filters.hidden = !isAuthorityUser();
  }

  let lastRows = [];
  let lastRepliesByParent = new Map();

  function updatePersonaFilter(rows) {
    ensureFilters();
    if (!isAuthorityUser() || !els.personaFilter) {
      filters.source = "all"; filters.recency = "all"; filters.persona = "all";
      return;
    }
    const current = els.personaFilter.value || "all";
    const personas = [...new Set(rows.map((r) => r.persona_type).filter(Boolean))].sort();
    els.personaFilter.innerHTML = `<option value="all">All personas</option>` + personas.map((p) => `<option value="${escapeHtml(p)}">${escapeHtml(p.replaceAll("_", " "))}</option>`).join("");
    els.personaFilter.value = personas.includes(current) ? current : "all";
    filters.persona = els.personaFilter.value;
  }

  function renderRows(rows, repliesByParent = new Map()) {
    ensureFilters();
    updatePersonaFilter(rows);
    const roleRows = isAuthorityUser() ? rows : rows.filter((row) => row.source !== "agent_simulation");
    const visibleRows = isAuthorityUser() ? applyFilters(roleRows) : roleRows;
    if (!visibleRows.length) {
      setHistory(`<div class="feedback-thread-head"><b>Feedback threads</b><button type="button" class="feedback-refresh" title="Refresh feedback" aria-label="Refresh feedback">↻</button><small>0 shown / ${roleRows.length} total</small></div><div class="feedback-item"><span>No matching feedback for this filter.</span></div>`, true);
      bindHistoryControls();
      return;
    }
    const liked = localLikes();
    const sourceCounts = roleRows.reduce((acc, row) => { acc[row.source] = (acc[row.source] || 0) + 1; return acc; }, {});
    const headerStats = isAuthorityUser()
      ? `${visibleRows.length} shown · public ${sourceCounts.public || 0} · authority ${sourceCounts.authority || 0} · agents ${sourceCounts.agent_simulation || 0}`
      : `${visibleRows.length} shown`;
    const header = `<div class="feedback-thread-head"><b>Feedback threads</b><button type="button" class="feedback-refresh" title="Refresh feedback" aria-label="Refresh feedback">↻</button><small>${headerStats}</small></div>`;
    const items = visibleRows.map((row) => {
      const date = friendlyDate(row.created_at);
      const count = Math.max(0, Math.round(Number(row.priority_score || 0)));
      const isLiked = liked.has(row.id) || row.user_has_vote === true;
      const isAgent = row.source === "agent_simulation";
      const isAuthority = row.source === "authority";
      const who = writerNameForRow(row);
      const badge = isAgent ? "agent" : (isAuthority ? "authority" : "public");
      const titleText = cleanThreadTitle(row.title);
      const language = row.original_language ? languageLabels[row.original_language] || row.original_language : "";
      const translation = row.english_translation && row.english_translation !== row.body
        ? `<div class="feedback-row-translation"><b>English:</b> ${escapeHtml(publicLabelText(row.english_translation))}</div>`
        : "";
      const parentKey = threadKey(row);
      const replies = repliesByParent.get(parentKey) || [];
      const replyItems = replies.map((reply) => {
        const role = reply.author_role || "public";
        const rTranslation = reply.english_translation && reply.english_translation !== reply.body
          ? `<div class="feedback-row-translation"><b>English:</b> ${escapeHtml(publicLabelText(reply.english_translation))}</div>`
          : "";
        const replyLang = reply.original_language ? languageLabels[reply.original_language] || reply.original_language : "";
        const replyMeta = [replyLang, friendlyDate(reply.created_at)].filter(Boolean).join(" · ");
        return `<div class="feedback-reply ${escapeHtml(role)}"><b><em>${escapeHtml(sourceLabel(role))}</em> ${escapeHtml(writerNameForReply(reply))}</b><span>${escapeHtml(publicLabelText(reply.body))}</span>${rTranslation}<small>${escapeHtml(replyMeta)}</small></div>`;
      }).join("");
      const canPersistReply = isUuid(row.id);
      const replyBox = `<div class="feedback-replies" data-parent-key="${escapeHtml(parentKey)}">${replyItems || ""}</div><div class="feedback-reply-box" data-parent-key="${escapeHtml(parentKey)}" hidden><div class="feedback-reply-composer-line"><textarea rows="2" maxlength="1200" placeholder="${authorRole() === "authority" ? "Reply as authority…" : "Reply to this feedback…"}"></textarea><button type="button" class="feedback-reply-speech" data-parent-key="${escapeHtml(parentKey)}" aria-label="Speech to text for reply" title="Speech to text"><span class="mic-pulse" aria-hidden="true"></span><span class="feedback-reply-speech-label" aria-hidden="true">${micIconSvg()}</span></button></div><div class="feedback-reply-translation"></div><div class="feedback-actions"><button type="button" class="feedback-reply-submit" data-parent-key="${escapeHtml(parentKey)}" ${canPersistReply ? "" : "disabled"}>Reply</button><button type="button" class="feedback-reply-cancel" data-parent-key="${escapeHtml(parentKey)}">Cancel</button></div><small class="feedback-reply-status"></small></div>`;
      const meta = [language, date].filter(Boolean).join(" · ");
      return `<div class="feedback-item ${escapeHtml(badge)}" data-thread-id="${escapeHtml(row.id)}" data-thread-source="${escapeHtml(row.source)}"><b><em>${escapeHtml(sourceLabel(row.source))}</em> ${escapeHtml(who)}</b>${titleText ? `<strong class="feedback-thread-title">${escapeHtml(titleText)}</strong>` : ""}<span>${escapeHtml(publicLabelText(row.body))}</span>${translation}<div class="feedback-social-row"><button type="button" class="feedback-like${isLiked ? " liked" : ""}" data-thread-id="${escapeHtml(row.id)}" data-count="${count}">${isLiked ? "♥" : "♡"} ${count}</button><button type="button" class="feedback-reply-open" data-parent-key="${escapeHtml(parentKey)}">Reply</button><small>${escapeHtml(meta)}</small></div>${replyBox}</div>`;
    }).join("");
    setHistory(`${header}${items}`, true);
    bindHistoryControls();
  }

  function bindHistoryControls() {
    els.history.querySelectorAll(".feedback-refresh").forEach((button) => {
      button.onclick = () => loadHistory({ manual: true });
    });
    els.history.querySelectorAll(".feedback-like").forEach((button) => {
      button.onclick = () => likeThread(button.dataset.threadId, button);
    });
    els.history.querySelectorAll(".feedback-reply-open").forEach((button) => {
      button.onclick = () => toggleReplyBox(button.dataset.parentKey, true);
    });
    els.history.querySelectorAll(".feedback-reply-cancel").forEach((button) => {
      button.onclick = () => toggleReplyBox(button.dataset.parentKey, false);
    });
    els.history.querySelectorAll(".feedback-reply-submit").forEach((button) => {
      button.onclick = () => submitReply(button.dataset.parentKey, button);
    });
    els.history.querySelectorAll(".feedback-reply-speech").forEach((button) => {
      button.onclick = () => startSpeechCapture(speechTargetForReply(button.dataset.parentKey));
    });
    els.history.querySelectorAll(".feedback-reply-box textarea").forEach((textarea) => {
      textarea.addEventListener("input", () => {
        textarea.dataset.inputModality = "typed";
        textarea.dataset.speechTranscriptOriginal = "";
        textarea.dataset.detectedLanguage = "";
        const box = textarea.closest(".feedback-reply-box");
        const parentKey = box?.dataset.parentKey || "";
        if (parentKey) scheduleReplyTranslation(parentKey);
      });
    });
  }

  function renderLastRows() { renderRows(lastRows, lastRepliesByParent); }

  function voteDeleteUrl(threadId) {
    return `${supabaseUrl}/rest/v1/feedback_votes?thread_id=eq.${encodeURIComponent(threadId)}&user_id=eq.${encodeURIComponent(voterId())}`;
  }

  async function likeThread(threadId, button) {
    const liked = localLikes();
    const wasLiked = liked.has(threadId) || button.classList.contains("liked");
    const nextLiked = !wasLiked;
    const current = Number(button.dataset.count || 0);
    const next = Math.max(0, current + (nextLiked ? 1 : -1));
    button.disabled = true;
    button.dataset.count = String(next);
    button.classList.toggle("liked", nextLiked);
    button.textContent = `${nextLiked ? "♥" : "♡"} ${next}`;
    if (nextLiked) liked.add(threadId);
    else liked.delete(threadId);
    saveLocalLikes(liked);
    try {
      if (nextLiked) {
        await fetch(`${supabaseUrl}/rest/v1/feedback_votes`, {
          method: "POST",
          headers: headers({ "Content-Type": "application/json", Prefer: "resolution=ignore-duplicates,return=minimal" }),
          body: JSON.stringify({ thread_id: threadId, user_id: voterId(), vote_type: "upvote" }),
        });
      } else {
        await fetch(voteDeleteUrl(threadId), {
          method: "DELETE",
          headers: headers({ Prefer: "return=minimal" }),
        });
      }
    } catch (e) {
      // Keep the visible unlike/like toggle responsive even if the demo backend is offline.
    } finally {
      button.disabled = false;
    }
  }

  function toggleReplyBox(parentKey, open) {
    const box = els.history?.querySelector(`.feedback-reply-box[data-parent-key="${CSS.escape(parentKey)}"]`);
    if (!box) return;
    box.hidden = !open;
    if (open) box.querySelector("textarea")?.focus();
  }

  const replyTranslationTimers = new Map();

  function renderReplyTranslation(parentKey, state = null, node = null) {
    const box = els.history?.querySelector(`.feedback-reply-box[data-parent-key="${CSS.escape(parentKey)}"]`);
    const el = node || box?.querySelector(".feedback-reply-translation");
    if (!el) return;
    const tr = state || JSON.parse(box?.dataset.translationState || "null");
    if (!tr || tr.language === "en") {
      el.classList.remove("visible");
      el.textContent = "";
      return;
    }
    el.classList.add("visible");
    const label = languageLabels[tr.language] || tr.language;
    if (tr.status === "translating") el.textContent = `Detected ${label}. Translating to English…`;
    else if (tr.status === "error") el.textContent = `Detected ${label}. English translation unavailable: ${tr.error || "Agnes AI request failed."}`;
    else el.textContent = tr.english || `Detected ${label}. English translation will appear here.`;
  }

  async function refreshReplyTranslationNow(parentKey) {
    const box = els.history?.querySelector(`.feedback-reply-box[data-parent-key="${CSS.escape(parentKey)}"]`);
    const textarea = box?.querySelector("textarea");
    const body = textarea?.value.trim() || "";
    const lang = normalizeSpeechLanguage(textarea?.dataset.detectedLanguage || "", body);
    let state = { language: lang, english: "", status: lang === "en" ? "not_required" : "translating", provider: null, model: null };
    if (box) box.dataset.translationState = JSON.stringify(state);
    renderReplyTranslation(parentKey, state);
    if (!body || lang === "en") return state;
    try {
      const english = await translateFeedback(body, lang);
      state = { language: lang, english, status: "translated", provider: translationState.provider || "browser_fallback", model: translationState.model || null };
    } catch (err) {
      state = { language: lang, english: "", status: "error", provider: translationState.provider || "browser_fallback", model: translationState.model || null, error: err.message || String(err) };
    }
    if (box) box.dataset.translationState = JSON.stringify(state);
    renderReplyTranslation(parentKey, state);
    return state;
  }

  function scheduleReplyTranslation(parentKey) {
    clearTimeout(replyTranslationTimers.get(parentKey));
    replyTranslationTimers.set(parentKey, setTimeout(() => refreshReplyTranslationNow(parentKey), 650));
  }

  async function translateTextForStorage(text, languageHint = "") {
    const lang = normalizeSpeechLanguage(languageHint, text);
    if (!text || lang === "en") return { language: lang, english: "", status: "not_required", provider: null, model: null };
    try {
      const english = await translateFeedback(text, lang);
      return { language: lang, english, status: english ? "translated" : "error", provider: translationState.provider || "browser_fallback", model: translationState.model || null };
    } catch (err) {
      return { language: lang, english: "", status: "error", provider: translationState.provider || "browser_fallback", model: translationState.model || null, error: err.message || String(err) };
    }
  }

  async function submitReply(parentKey, button) {
    const [source, id] = String(parentKey || "").split(":");
    const box = els.history?.querySelector(`.feedback-reply-box[data-parent-key="${CSS.escape(parentKey)}"]`);
    const textarea = box?.querySelector("textarea");
    const status = box?.querySelector(".feedback-reply-status");
    const body = textarea?.value.trim() || "";
    if (!body || !isUuid(id)) return;
    const user = getCurrentUser?.() || {};
    const role = authorRole();
    button.disabled = true;
    if (status) status.textContent = "Posting reply…";
    try {
      const tr = await translateTextForStorage(body, textarea?.dataset.detectedLanguage || "");
      const payload = {
        parent_source: source === "agent_simulation" ? "agent_simulation" : "public",
        parent_thread_id: source === "agent_simulation" ? null : id,
        parent_agent_thread_id: source === "agent_simulation" ? id : null,
        author_role: role,
        author_external_id: user.external_id || voterId(),
        author_name: user.display_name || user.username || (role === "authority" ? "Authority user" : "Public user"),
        body,
        original_language: tr.language || "en",
        original_text: body,
        english_translation: tr.language !== "en" ? tr.english || null : null,
        translation_status: tr.status || "not_required",
        translation_provider: tr.provider,
        translation_model: tr.model,
        input_modality: textarea?.dataset.inputModality || "typed",
      };
      const r = await fetch(`${supabaseUrl}/rest/v1/feedback_replies`, {
        method: "POST",
        headers: headers({ "Content-Type": "application/json", Prefer: "return=representation" }),
        body: JSON.stringify(payload),
      });
      if (!r.ok) throw new Error(`Supabase reply ${r.status}: ${await r.text()}`);
      textarea.value = "";
      if (status) status.textContent = "Reply posted.";
      await loadHistory();
    } catch (err) {
      if (status) status.textContent = err.message || String(err);
    } finally {
      button.disabled = false;
    }
  }

  async function loadHistory(options = {}) {
    if (!els?.history || !supabaseUrl || !supabaseKey) return;
    ensureFilters();
    const requestId = ++historyRequestId;
    const ctx = getDetailContext() || {};
    if (options.manual || !lastRows.length) setHistory("Loading feedback threads…", true);
    try {
      const { streetPartId, featureId } = await resolveContextIds(ctx);
      if (requestId !== historyRequestId) return;
      if (!streetPartId && !ctx.streetPartExternalId) {
        setHistory("Feedback thread appears once this footpath is linked to Supabase.", true);
        return;
      }
      const [publicResult, agentResult] = await Promise.allSettled([
        fetchPublicFeedbackRows(streetPartId, featureId),
        isAuthorityUser() ? fetchAgentFeedbackRows(streetPartId, ctx.streetPartExternalId, featureId) : Promise.resolve([]),
      ]);
      if (requestId !== historyRequestId) return;
      const publicRowsRaw = publicResult.status === "fulfilled" ? publicResult.value : [];
      const userVoteIds = await fetchUserVoteThreadIds(publicRowsRaw);
      if (requestId !== historyRequestId) return;
      const publicRows = publicRowsRaw.map((row) => ({ ...row, user_has_vote: userVoteIds.has(row.id) }));
      const localAgentRows = (global.__EARTH_ACCESSIBILITY_STATE?.liveAgentSnapshot?.agent_feedback_threads || [])
        .filter((row) => row.street_part_external_id === ctx.streetPartExternalId)
        .map((row, index) => ({ ...row, id: row.id || `local-agent-${ctx.streetPartExternalId}-${index}`, source: "agent_simulation" }));
      const agentRows = isAuthorityUser() && agentResult.status === "fulfilled" && agentResult.value.length ? agentResult.value : (isAuthorityUser() ? localAgentRows : []);
      lastRows = [...publicRows, ...agentRows].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
      lastRepliesByParent = await fetchFeedbackReplies(lastRows);
      onFeedbackRowsLoaded(lastRows, ctx);
      if (!lastRows.length) {
        const errors = [publicResult, agentResult].filter((r) => r.status === "rejected").map((r) => r.reason?.message || String(r.reason));
        setHistory(`<div class="feedback-thread-head"><b>Feedback threads</b><button type="button" class="feedback-refresh" title="Refresh feedback" aria-label="Refresh feedback">↻</button><small>0 posts</small></div><div class="feedback-item"><span>No reports yet.${errors.length ? " Some live tables may not be migrated yet." : " Be the first to post feedback for this footpath."}</span></div>`, true);
        bindHistoryControls();
        return;
      }
      renderRows(lastRows, lastRepliesByParent);
    } catch (err) {
      if (requestId !== historyRequestId) return;
      setHistory(`Could not load feedback threads: ${escapeHtml(err.message || String(err))}`, true);
    }
  }

  function publicUserName() {
    const user = getCurrentUser?.() || {};
    return user.display_name || user.username || user.external_id || "Public user";
  }


  function agnesApiKey() {
    return global.JALANLENS_AGNES_API_KEY || localStorage.getItem(AGNES_KEY_STORAGE) || "";
  }

  function setFeedbackStatus(message, cls = "") {
    if (!els?.status) return;
    els.status.className = cls;
    els.status.textContent = message;
  }

  function detectFeedbackLanguage(text) {
    const value = String(text || "").trim();
    if (!value) return "en";
    if (/[஀-௿]/.test(value)) return "ta";
    if (/[઀-૿]/.test(value)) return "gu";
    if (/[一-鿿]/.test(value)) {
      return /[後這個門開關會讓無障礙臺灣繁體國裏]/.test(value) ? "zh-Hant" : "zh-Hans";
    }
    if (/\b(saya|jalan|laluan|kaki lima|pejalan kaki|kerusi roda|terima kasih|tidak|boleh|bahaya|rosak|sempit|licin|halang|terhalang|longkang|rata|tak rata|orang awam)\b/i.test(value)) return "ms";
    return "en";
  }

  function normalizeSpeechLanguage(value, text = "") {
    const raw = String(value || "").toLowerCase();
    if (raw.startsWith("zh") || raw.includes("chinese") || raw.includes("mandarin")) return detectFeedbackLanguage(text).startsWith("zh") ? detectFeedbackLanguage(text) : "zh-Hans";
    if (raw.startsWith("ms") || raw.startsWith("may") || raw.includes("malay")) return "ms";
    if (raw.startsWith("ta") || raw.includes("tamil")) return "ta";
    if (raw.startsWith("gu") || raw.includes("gujarati")) return "gu";
    if (raw.startsWith("en") || raw.includes("english")) return detectFeedbackLanguage(text);
    return detectFeedbackLanguage(text);
  }

  function normalizeTranscriptText(text) {
    return String(text || "").replace(/\s+/g, " ").trim();
  }

  function dedupeTranscriptText(text) {
    const value = normalizeTranscriptText(text);
    if (!value) return "";
    const sentenceParts = value.match(/[^.!?。！？]+[.!?。！？]?/g) || [value];
    const kept = [];
    const seen = new Set();
    for (const part of sentenceParts) {
      const clean = normalizeTranscriptText(part);
      const key = clean.toLowerCase().replace(/[\s,.;:!?。！？，、]+/g, " ").trim();
      if (!key || seen.has(key)) continue;
      seen.add(key);
      kept.push(clean);
    }
    let output = kept.join(" ").trim();
    const words = output.split(/\s+/);
    if (words.length % 2 === 0) {
      const mid = words.length / 2;
      const left = words.slice(0, mid).join(" ").toLowerCase();
      const right = words.slice(mid).join(" ").toLowerCase();
      if (left && left === right) output = words.slice(0, mid).join(" ");
    }
    return output;
  }

  function translationPrompt(text, lang) {
    return `Translate this public accessibility feedback into clear English. Preserve place names and issue details. Return only the English translation. Source language: ${languageLabels[lang] || lang}. Text:\n${text}`;
  }

  async function translateFeedbackWithAgnes(text, lang) {
    const key = agnesApiKey();
    if (!key) throw new Error("Agnes API key unavailable in this browser. Add it to localStorage as jalanlens_agnes_api_key.");
    const r = await fetch(`${AGNES_BASE_URL}/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + key },
      body: JSON.stringify({
        model: AGNES_TRANSLATION_MODEL,
        temperature: 0,
        messages: [
          { role: "system", content: "You are a careful civic feedback translator. Translate to English only." },
          { role: "user", content: translationPrompt(text, lang) },
        ],
      }),
    });
    if (!r.ok) throw new Error(`Agnes translation ${r.status}`);
    const data = await r.json();
    return String(data.choices?.[0]?.message?.content || "").trim();
  }

  function myMemoryLang(lang) {
    if (lang === "zh-Hant") return "zh-TW";
    if (lang === "zh-Hans") return "zh-CN";
    return lang;
  }

  function localTranslationFallback(text, lang) {
    const value = String(text || "").trim();
    const phrases = [
      [/坡道|斜坡/i, "ramp"], [/坏|壞|rosak/i, "is damaged"], [/危险|危險|bahaya/i, "dangerous"], [/路|jalan|சாலை/i, "path/road"], [/轮椅|輪椅|kerusi roda/i, "wheelchair"], [/blocked|halang|阻/i, "blocked"], [/சாலை உடைந்துள்ளது/i, "The road is damaged"],
    ];
    const parts = phrases.filter(([re]) => re.test(value)).map(([, en]) => en);
    if (parts.length) return `Approximate translation: ${parts.join(" · ")}. Original: ${value}`;
    return `Translation pending. Original ${languageLabels[lang] || lang}: ${value}`;
  }

  async function translateFeedbackWithPublicFallback(text, lang) {
    const apiLang = myMemoryLang(lang);
    const url = "https://api.mymemory.translated.net/get?" + new URLSearchParams({ q: text, langpair: `${apiLang}|en` });
    const r = await fetch(url);
    if (!r.ok) throw new Error(`public translation ${r.status}`);
    const data = await r.json();
    const translated = String(data.responseData?.translatedText || "").trim();
    if (!translated || translated.length < 3 || translated.toLowerCase() === String(text).trim().toLowerCase()) throw new Error("public translation unavailable");
    return translated;
  }

  async function translateFeedback(text, lang) {
    if (agnesApiKey()) {
      try {
        const english = await translateFeedbackWithAgnes(text, lang);
        translationState.provider = "agnes";
        translationState.model = AGNES_TRANSLATION_MODEL;
        return english;
      } catch (err) {
        console.warn("Agnes translation unavailable; using public fallback", err);
      }
    }
    try {
      const english = await translateFeedbackWithPublicFallback(text, lang);
      translationState.provider = "mymemory";
      translationState.model = "public-web-translation";
      return english;
    } catch (err) {
      translationState.provider = "local_fallback";
      translationState.model = "jalanlens-keyword-fallback";
      return localTranslationFallback(text, lang);
    }
  }

  function renderTranslationBox() {
    if (!els?.translationBox || !els.translationText) return;
    const lang = translationState.language || "en";
    const needsTranslation = lang !== "en";
    els.translationBox.classList.toggle("visible", needsTranslation || translationState.status === "translating" || translationState.status === "error");
    if (!needsTranslation) {
      els.translationText.textContent = "";
      return;
    }
    const label = languageLabels[lang] || lang;
    if (translationState.status === "translating") {
      els.translationText.textContent = `Detected ${label}. Translating to English…`;
    } else if (translationState.status === "error") {
      els.translationText.textContent = `Detected ${label}. English translation unavailable: ${translationState.error || "Agnes AI request failed."}`;
    } else {
      els.translationText.textContent = translationState.english || `Detected ${label}. English translation will appear here.`;
    }
  }

  async function refreshTranslationNow() {
    const body = els.body.value.trim();
    const lang = normalizeSpeechLanguage(els.body.dataset.detectedLanguage || "", body);
    translationState = { language: lang, english: "", status: lang === "en" ? "not_required" : "translating", provider: null, model: null };
    renderTranslationBox();
    if (!body || lang === "en") return translationState;
    try {
      const english = await translateFeedback(body, lang);
      translationState = { language: lang, english, status: "translated", provider: translationState.provider || "browser_fallback", model: translationState.model || null };
    } catch (err) {
      translationState = { language: lang, english: "", status: "error", provider: translationState.provider || "browser_fallback", model: translationState.model || null, error: err.message || String(err) };
    }
    renderTranslationBox();
    return translationState;
  }

  function scheduleTranslation() {
    inputModality = inputModality === "speech" ? "speech" : "typed";
    clearTimeout(translationTimer);
    translationTimer = setTimeout(refreshTranslationNow, 650);
  }

  async function transcribeAudioWithAgnes(blob) {
    const key = agnesApiKey();
    if (!key) throw new Error("Agnes API key unavailable in this browser. Add it to localStorage as jalanlens_agnes_api_key.");
    const data = new FormData();
    data.append("model", AGNES_TRANSCRIPTION_MODEL);
    data.append("file", blob, "feedback.webm");
    data.append("response_format", "json");
    data.append("prompt", "Transcribe exactly what the speaker says for JalanLens civic feedback. Detect English, Mandarin Chinese, Malay, Tamil, or Gujarati automatically. Preserve the original language; do not translate in this transcription step.");
    const r = await fetch(`${AGNES_BASE_URL}/audio/transcriptions`, {
      method: "POST",
      headers: { Authorization: "Bearer " + key },
      body: data,
    });
    if (!r.ok) throw new Error(`Agnes transcription ${r.status}`);
    const result = await r.json();
    const text = dedupeTranscriptText(result.text || result.transcript || "");
    return { text, language: normalizeSpeechLanguage(result.language || result.detected_language || result.source_language || "", text), raw: result };
  }

  function speechTargetForMain() {
    return {
      kind: "feedback",
      textarea: els.body,
      button: els.speechBtn,
      label: els.speechLabel,
      status: els.speechStatus,
      setInputModality: (mode) => { inputModality = mode; },
      setTranscript: (text) => { speechTranscriptOriginal = text; },
      getTranscript: () => speechTranscriptOriginal,
      translateNow: () => refreshTranslationNow(),
      scheduleTranslate: () => scheduleTranslation(),
      renderTranslation: (state) => { translationState = state; renderTranslationBox(); },
    };
  }

  function speechTargetForReply(parentKey) {
    const box = els.history?.querySelector(`.feedback-reply-box[data-parent-key="${CSS.escape(parentKey)}"]`);
    const textarea = box?.querySelector("textarea");
    const button = box?.querySelector(".feedback-reply-speech");
    const label = box?.querySelector(".feedback-reply-speech-label");
    const status = box?.querySelector(".feedback-reply-status");
    const translation = box?.querySelector(".feedback-reply-translation");
    return {
      kind: `reply:${parentKey}`,
      textarea,
      button,
      label,
      status,
      setInputModality: (mode) => { if (textarea) textarea.dataset.inputModality = mode; },
      setTranscript: (text) => { if (textarea) textarea.dataset.speechTranscriptOriginal = text; },
      getTranscript: () => textarea?.dataset.speechTranscriptOriginal || "",
      translateNow: () => refreshReplyTranslationNow(parentKey),
      scheduleTranslate: () => scheduleReplyTranslation(parentKey),
      renderTranslation: (state) => renderReplyTranslation(parentKey, state, translation),
    };
  }

  function setTargetSpeechIcon(target, recording = false) {
    if (!target?.label) return;
    target.label.innerHTML = recording ? "⏹" : micIconSvg();
  }

  function startBrowserSpeechRecognition(target) {
    const SpeechRecognition = global.SpeechRecognition || global.webkitSpeechRecognition;
    if (!SpeechRecognition || !target?.textarea) return null;
    const rec = new SpeechRecognition();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-SG";
    browserFinalTranscripts = new Map();
    browserInterimTranscript = "";
    const base = normalizeTranscriptText(target.textarea.value);
    rec.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const chunk = normalizeTranscriptText(event.results[i][0]?.transcript || "");
        if (event.results[i].isFinal) browserFinalTranscripts.set(i, chunk);
        else browserInterimTranscript = chunk;
      }
      const finalText = [...browserFinalTranscripts.keys()].sort((a, b) => a - b).map((k) => browserFinalTranscripts.get(k)).filter(Boolean).join(" ");
      const text = dedupeTranscriptText([base, finalText, browserInterimTranscript].filter(Boolean).join(" "));
      if (text) {
        target.setTranscript(text);
        target.textarea.value = text;
        target.scheduleTranslate();
      }
    };
    rec.onerror = () => {};
    rec.start();
    return rec;
  }

  async function startSpeechCapture(target = speechTargetForMain()) {
    if (!target?.button || !target.textarea) return;
    if (activeSpeechTarget && activeSpeechTarget.kind !== target.kind) {
      if (mediaRecorder && mediaRecorder.state === "recording") mediaRecorder.stop();
      if (speechRecognition) { try { speechRecognition.stop(); } catch (e) {} }
      activeSpeechTarget.button?.classList.remove("recording");
      setTargetSpeechIcon(activeSpeechTarget, false);
      mediaRecorder = null;
      speechRecognition = null;
    }
    if (mediaRecorder && mediaRecorder.state === "recording" && activeSpeechTarget?.kind === target.kind) {
      mediaRecorder.stop();
      return;
    }
    if (speechRecognition && !mediaRecorder && activeSpeechTarget?.kind === target.kind) {
      try { speechRecognition.stop(); } catch (e) {}
      speechRecognition = null;
      target.button.classList.remove("recording");
      setTargetSpeechIcon(target, false);
      if (target.status) target.status.textContent = target.getTranscript() ? "Browser speech transcript captured." : "Speech capture stopped.";
      await target.translateNow();
      activeSpeechTarget = null;
      return;
    }
    activeSpeechTarget = target;
    target.setInputModality("speech");
    audioChunks = [];
    const startingText = normalizeTranscriptText(target.textarea.value);
    target.setTranscript(startingText);
    target.button.classList.add("recording");
    setTargetSpeechIcon(target, true);
    const canUseAgnes = !!global.JALANLENS_USE_AGNES_SPEECH && !!agnesApiKey() && !!navigator.mediaDevices?.getUserMedia && !!global.isSecureContext;
    if (canUseAgnes) {
      if (target.status) target.status.textContent = "Recording for Agnes AI… tap Stop when done.";
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        mediaRecorder.ondataavailable = (event) => { if (event.data?.size) audioChunks.push(event.data); };
        mediaRecorder.onstop = async () => {
          stream.getTracks().forEach((track) => track.stop());
          target.button.classList.remove("recording");
          setTargetSpeechIcon(target, false);
          if (target.status) target.status.textContent = "Transcribing with Agnes AI…";
          try {
            const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
            const result = await transcribeAudioWithAgnes(blob);
            if (result.text) {
              target.setTranscript(result.text);
              target.textarea.value = result.text;
              target.textarea.dataset.detectedLanguage = result.language || detectFeedbackLanguage(result.text);
            }
            if (target.status) target.status.textContent = `Transcription complete${target.textarea.dataset.detectedLanguage && target.textarea.dataset.detectedLanguage !== "en" ? ` · detected ${languageLabels[target.textarea.dataset.detectedLanguage] || target.textarea.dataset.detectedLanguage}` : ""}.`;
          } catch (err) {
            if (target.status) target.status.textContent = err.message || "Speech transcription failed.";
          }
          await target.translateNow();
          mediaRecorder = null;
          activeSpeechTarget = null;
        };
        mediaRecorder.start();
        return;
      } catch (err) {
        if (target.status) target.status.textContent = "Agnes microphone unavailable; using browser speech-to-text fallback. Tap Stop when done.";
      }
    }
    speechRecognition = startBrowserSpeechRecognition(target);
    if (target.status) {
      target.status.textContent = speechRecognition
        ? "Using browser speech-to-text fallback. Tap Stop when done."
        : "Speech-to-text needs microphone permission in a secure browser.";
    }
    if (!speechRecognition) {
      target.button.classList.remove("recording");
      setTargetSpeechIcon(target, false);
      activeSpeechTarget = null;
    }
  }

  async function submit(title, body) {
    const ctx = getDetailContext() || {};
    const { streetPartId, featureId } = await resolveContextIds(ctx);
    if (!streetPartId) throw new Error("No street_part match yet. Open a seeded demo corridor segment first.");
    const user = getCurrentUser?.() || {};
    const translation = await refreshTranslationNow();
    const englishTranslation = translation.language !== "en" ? translation.english : "";
    const payload = {
      street_part_id: streetPartId,
      feature_id: featureId,
      title,
      body,
      original_language: translation.language || "en",
      original_text: body,
      english_translation: englishTranslation || null,
      translation_status: translation.status || (translation.language === "en" ? "not_required" : "error"),
      translation_provider: translation.provider || null,
      translation_model: translation.model || null,
      speech_transcript_original: inputModality === "speech" ? (speechTranscriptOriginal || body) : null,
      input_modality: inputModality,
      created_by: null,
      source: user.role === "authority" ? "authority" : "public",
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
    if (els.openBtn) els.openBtn.onclick = () => open();
    els.cancelBtn.onclick = () => { els.body.value = ""; close(true); };
    els.body.addEventListener("input", () => { inputModality = "typed"; speechTranscriptOriginal = ""; els.body.dataset.detectedLanguage = ""; scheduleTranslation(); });
    if (els.speechBtn) els.speechBtn.onclick = () => startSpeechCapture();
    els.form.onsubmit = async (e) => {
      e.preventDefault();
      const title = els.title.value.trim();
      const body = els.body.value.trim();
      if (!body) return;
      els.submitBtn.disabled = true;
      els.status.className = "";
      els.status.textContent = "Submitting…";
      try {
        const rows = await submit(title, body);
        const row = Array.isArray(rows) ? rows[0] : rows;
        els.status.className = "ok";
        els.status.textContent = row?.feature_id ? `Feedback posted to feature thread.` : `Feedback posted.`;
        els.title.value = "";
        els.body.value = "";
        els.body.dataset.detectedLanguage = "";
        speechTranscriptOriginal = "";
        inputModality = "typed";
        translationState = { language: "en", english: "", status: "not_required", provider: null, model: null };
        renderTranslationBox();
        await loadHistory({ manual: true });
        close(false);
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
      languageHint: "feedbackLanguageHint",
      speechBtn: "feedbackSpeechBtn",
      speechLabel: "feedbackSpeechLabel",
      speechStatus: "feedbackSpeechStatus",
      translationBox: "feedbackTranslationBox",
      translationText: "feedbackTranslationText",
    };
    els = {};
    for (const [key, id] of Object.entries(ids)) {
      const el = $(id);
      if (!el && !["openBtn", "languageHint"].includes(key)) throw new Error(`EquirouteFeedback: missing #${id}`);
      els[key] = el;
    }
    bindEvents();
    ensureFilters();
    setSpeechIcon(false);
    els.form.classList.add("open");
    updateMeta();
    fillTitleFromContext();
    return api;
  }

  const api = { init, open, close, onContextChange, updateMeta, loadHistory, detectFeedbackLanguage, refreshTranslationNow };
  global.EquirouteFeedback = api;
})(typeof window !== "undefined" ? window : globalThis);
