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
      const translation = row.english_translation && row.english_translation !== row.body
        ? `<div class="feedback-row-translation"><b>English:</b> ${escapeHtml(publicLabelText(row.english_translation))}</div>`
        : "";
      return `<div class="feedback-item ${escapeHtml(badge)}" data-thread-id="${escapeHtml(row.id)}"><b><em>${escapeHtml(badge)}</em> ${escapeHtml(publicLabelText(row.title))}</b><span>${escapeHtml(publicLabelText(row.body))}</span>${translation}<div class="feedback-social-row"><button type="button" class="feedback-like${isLiked ? " liked" : ""}" data-thread-id="${escapeHtml(row.id)}" data-count="${count}">${isLiked ? "♥" : "♡"} ${count}</button><small>${escapeHtml(who)}${escapeHtml(persona)} · ${escapeHtml(row.input_modality || "typed")} · ${escapeHtml(row.original_language ? languageLabels[row.original_language] || row.original_language : "")}${row.original_language ? " · " : ""}${escapeHtml(date)}</small></div></div>`;
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
    if (/[80-FF]/.test(value)) return "ta";
    if (/[	80-	FF]/.test(value)) return "bn";
    if (/[
80-
FF]/.test(value)) return "gu";
    if (/[00-7F]/.test(value)) return "th";
    if (/[E00-	FFF]/.test(value)) {
      return /[後這個門開關會讓無障礙臺灣繁體國裏]/.test(value) ? "zh-Hant" : "zh-Hans";
    }
    if (/[à-ž]/i.test(value) || /\b(saya|jalan|kerusi roda|terima kasih|tidak|boleh|laluan|bahaya|rosak)\b/i.test(value)) return "ms";
    return "en";
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
      els.translationText.textContent = `Detected ${label}. Translating to English with Agnes AI…`;
    } else if (translationState.status === "error") {
      els.translationText.textContent = `Detected ${label}. English translation unavailable: ${translationState.error || "Agnes AI request failed."}`;
    } else {
      els.translationText.textContent = translationState.english || `Detected ${label}. English translation will appear here.`;
    }
  }

  async function refreshTranslationNow() {
    const body = els.body.value.trim();
    const lang = detectFeedbackLanguage(body);
    translationState = { language: lang, english: "", status: lang === "en" ? "not_required" : "translating", provider: null, model: null };
    renderTranslationBox();
    if (!body || lang === "en") return translationState;
    try {
      const english = await translateFeedbackWithAgnes(body, lang);
      translationState = { language: lang, english, status: "translated", provider: "agnes", model: AGNES_TRANSLATION_MODEL };
    } catch (err) {
      translationState = { language: lang, english: "", status: "error", provider: "agnes", model: AGNES_TRANSLATION_MODEL, error: err.message || String(err) };
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
    const r = await fetch(`${AGNES_BASE_URL}/audio/transcriptions`, {
      method: "POST",
      headers: { Authorization: "Bearer " + key },
      body: data,
    });
    if (!r.ok) throw new Error(`Agnes transcription ${r.status}`);
    const result = await r.json();
    return String(result.text || result.transcript || "").trim();
  }

  function startBrowserSpeechRecognition() {
    const SpeechRecognition = global.SpeechRecognition || global.webkitSpeechRecognition;
    if (!SpeechRecognition) return null;
    const rec = new SpeechRecognition();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-SG";
    rec.onresult = (event) => {
      let finalText = "";
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const chunk = event.results[i][0]?.transcript || "";
        if (event.results[i].isFinal) finalText += chunk;
        else interim += chunk;
      }
      const text = (finalText || interim).trim();
      if (text) {
        speechTranscriptOriginal = `${speechTranscriptOriginal} ${text}`.trim();
        els.body.value = speechTranscriptOriginal;
        scheduleTranslation();
      }
    };
    rec.onerror = () => {};
    rec.start();
    return rec;
  }

  async function startSpeechCapture() {
    if (!els.speechBtn) return;
    if (mediaRecorder && mediaRecorder.state === "recording") {
      mediaRecorder.stop();
      return;
    }
    inputModality = "speech";
    audioChunks = [];
    speechTranscriptOriginal = els.body.value.trim();
    els.speechBtn.classList.add("recording");
    els.speechLabel.textContent = "Stop transcribing";
    els.speechStatus.textContent = "Listening… mic is active and pulsing.";
    speechRecognition = startBrowserSpeechRecognition();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = (event) => { if (event.data?.size) audioChunks.push(event.data); };
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        if (speechRecognition) { try { speechRecognition.stop(); } catch (e) {} }
        els.speechBtn.classList.remove("recording");
        els.speechLabel.textContent = "Start speech to text";
        els.speechStatus.textContent = "Transcribing with Agnes AI…";
        try {
          const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
          const text = await transcribeAudioWithAgnes(blob);
          if (text) {
            speechTranscriptOriginal = text;
            els.body.value = text;
          }
          els.speechStatus.textContent = "Transcription complete.";
        } catch (err) {
          els.speechStatus.textContent = speechTranscriptOriginal ? "Agnes transcription unavailable; using browser speech transcript." : (err.message || "Speech transcription failed.");
        }
        await refreshTranslationNow();
      };
      mediaRecorder.start();
    } catch (err) {
      els.speechBtn.classList.remove("recording");
      els.speechLabel.textContent = "Start speech to text";
      els.speechStatus.textContent = err.message || "Microphone permission denied.";
      if (speechRecognition) { try { speechRecognition.stop(); } catch (e) {} }
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
      translation_provider: translation.language !== "en" ? "agnes" : null,
      translation_model: translation.language !== "en" ? AGNES_TRANSLATION_MODEL : null,
      speech_transcript_original: inputModality === "speech" ? (speechTranscriptOriginal || body) : null,
      input_modality: inputModality,
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
    els.body.addEventListener("input", () => { inputModality = "typed"; speechTranscriptOriginal = ""; scheduleTranslation(); });
    if (els.speechBtn) els.speechBtn.onclick = () => startSpeechCapture();
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
        speechTranscriptOriginal = "";
        inputModality = "typed";
        translationState = { language: "en", english: "", status: "not_required", provider: null, model: null };
        renderTranslationBox();
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
      if (!el) throw new Error(`EquirouteFeedback: missing #${id}`);
      els[key] = el;
    }
    bindEvents();
    ensureFilters();
    return api;
  }

  const api = { init, open, close, onContextChange, updateMeta, loadHistory, detectFeedbackLanguage, refreshTranslationNow };
  global.EquirouteFeedback = api;
})(typeof window !== "undefined" ? window : globalThis);
