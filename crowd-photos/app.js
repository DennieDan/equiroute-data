const SUPABASE_URL = "https://khddsjemkdcgumfvkraa.supabase.co";
const SUPABASE_PUBLISHABLE_KEY =
  "sb_publishable_lqGtwkNAOMV7qsYPKVZr8w_GytZx3Qm";
const USER_STORAGE_KEY = "jalanlens_user";
const ROLE_STORAGE_KEY = "jalanlens_role";

const state = {
  user: readJson(USER_STORAGE_KEY) || {},
  role: localStorage.getItem(ROLE_STORAGE_KEY) || "public",
  streetParts: [],
  liveStreetParts: new Map(),
  photos: [],
  jobs: [],
  comments: [],
  selectedJobId: null,
  activationCandidate: null,
  activePhotos: [],
  lastCv: null,
};

function readJson(key) {
  try {
    return JSON.parse(localStorage.getItem(key) || "null");
  } catch {
    return null;
  }
}

function apiHeaders(extra = {}) {
  return {
    apikey: SUPABASE_PUBLISHABLE_KEY,
    Authorization: `Bearer ${SUPABASE_PUBLISHABLE_KEY}`,
    ...extra,
  };
}

async function rest(table, query = "select=*") {
  const response = await fetch(`${SUPABASE_URL}/rest/v1/${table}?${query}`, {
    headers: apiHeaders(),
    signal: AbortSignal.timeout(6000),
  });
  if (!response.ok) {
    throw new Error(`Supabase ${table} ${response.status}: ${await response.text()}`);
  }
  return response.json();
}

async function insert(table, payload) {
  const response = await fetch(`${SUPABASE_URL}/rest/v1/${table}`, {
    method: "POST",
    headers: apiHeaders({
      "Content-Type": "application/json",
      Prefer: "return=representation",
    }),
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Could not save ${table}: ${await response.text()}`);
  }
  return (await response.json())[0] || null;
}

async function rpc(name, payload) {
  const response = await fetch(`${SUPABASE_URL}/rest/v1/rpc/${name}`, {
    method: "POST",
    headers: apiHeaders({
      "Content-Type": "application/json",
      Prefer: "return=representation",
    }),
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Could not complete review: ${await response.text()}`);
  }
  const body = await response.json();
  return Array.isArray(body) ? body[0] : body;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function prettyPart(value) {
  const match = String(value || "").match(/street_part_(\d+)$/);
  return match ? `Footpath ${Number(match[1]) + 1}` : "Unknown footpath";
}

function formatDate(value) {
  if (!value) return "Not recorded";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function setStatus(element, message, kind = "") {
  element.className = `status${kind ? ` ${kind}` : ""}`;
  element.textContent = message || "";
}

function selectStep(step) {
  document.querySelectorAll(".step-tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.step === step);
  });
  document.querySelectorAll(".step-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.panel === step);
  });
  if (step === "staff" && state.role === "authority") loadReviewQueue();
  if (step === "approved") loadApprovedPhotos();
}

async function loadStreetParts() {
  let local = [];
  try {
    const response = await fetch("../data/street_view_registry.json");
    if (response.ok) {
      const registry = await response.json();
      local = registry.street_parts || [];
    }
  } catch (error) {
    console.warn("Local street registry unavailable", error);
  }

  const merged = new Map();
  local.forEach((part) => merged.set(part.id, { ...part, external_id: part.id }));
  function renderOptions() {
    const selected = streetPartSelect.value;
    state.streetParts = [...merged.values()].sort((a, b) =>
      a.external_id.localeCompare(b.external_id),
    );
    if (!state.streetParts.length) return;
    streetPartSelect.innerHTML = state.streetParts
      .map(
        (part) =>
          `<option value="${escapeHtml(part.external_id)}">${escapeHtml(prettyPart(part.external_id))}</option>`,
      )
      .join("");
    if (selected && merged.has(selected)) streetPartSelect.value = selected;
    streetPartSelect.disabled = false;
    photoUploadBtn.disabled = false;
  }
  renderOptions();

  if (!local.length) {
    streetPartSelect.innerHTML = "<option>No Footpaths available</option>";
    setStatus(
      photoUploadStatus,
      "The bundled street registry is unavailable. Trying Supabase…",
      "warn",
    );
  } else {
    setStatus(
      photoUploadStatus,
      "Footpaths loaded. Connecting them to the live submission registry…",
    );
  }

  let live = [];
  try {
    live = await rest(
      "street_parts",
      "select=id,external_id,midpoint_lng,midpoint_lat,desired_orientation&order=external_id.asc",
    );
  } catch (error) {
    console.warn("Live Footpaths unavailable", error);
  }
  live.forEach((part) => {
    state.liveStreetParts.set(part.external_id, part);
    merged.set(part.external_id, {
      ...(merged.get(part.external_id) || {}),
      ...part,
    });
  });
  renderOptions();

  if (!state.streetParts.length) {
    setStatus(
      photoUploadStatus,
      "No Footpaths could be loaded from Supabase or the local registry.",
      "err",
    );
    return;
  }
  if (!live.length) {
    setStatus(
      photoUploadStatus,
      "Footpaths loaded from the local registry. A live Supabase connection is required when you submit.",
      "warn",
    );
  }
}

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Could not read this image file."));
    };
    image.src = url;
  });
}

async function analyzePhoto(file) {
  if (!file?.type?.startsWith("image/")) {
    throw new Error("Please choose an image file.");
  }
  if (file.size > 8 * 1024 * 1024) {
    throw new Error("Photo is too large. Keep uploads below 8 MB.");
  }
  const image = await loadImage(file);
  const width = 256;
  const height = 144;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  context.drawImage(image, 0, 0, width, height);
  const pixels = context.getImageData(0, 0, width, height).data;
  const luminance = new Float32Array(width * height);
  let sum = 0;
  let sumSq = 0;
  let saturated = 0;
  let edge = 0;
  for (let i = 0, pixel = 0; i < pixels.length; i += 4, pixel++) {
    const value =
      0.2126 * pixels[i] + 0.7152 * pixels[i + 1] + 0.0722 * pixels[i + 2];
    luminance[pixel] = value;
    sum += value;
    sumSq += value * value;
    if (value < 8 || value > 247) saturated++;
  }
  for (let y = 1; y < height; y++) {
    for (let x = 1; x < width; x++) {
      const index = y * width + x;
      edge +=
        Math.abs(luminance[index] - luminance[index - 1]) +
        Math.abs(luminance[index] - luminance[index - width]);
    }
  }
  const count = width * height;
  const brightness = sum / count;
  const contrast = Math.sqrt(Math.max(0, sumSq / count - brightness ** 2));
  const aspect = image.naturalWidth / Math.max(1, image.naturalHeight);
  const checks = [
    {
      label: "Resolution",
      pass: image.naturalWidth >= 900 && image.naturalHeight >= 500,
      detail: `${image.naturalWidth} × ${image.naturalHeight}`,
      points: 25,
    },
    {
      label: "Landscape framing",
      pass: aspect >= 1.05 && aspect <= 2.4,
      detail: `${aspect.toFixed(2)}:1`,
      points: 15,
    },
    {
      label: "Exposure",
      pass: brightness >= 42 && brightness <= 220 && saturated / count < 0.28,
      detail: `brightness ${brightness.toFixed(0)}`,
      points: 20,
    },
    {
      label: "Contrast",
      pass: contrast >= 18,
      detail: `contrast ${contrast.toFixed(0)}`,
      points: 20,
    },
    {
      label: "Visual detail",
      pass: edge / count >= 12,
      detail: `detail ${(edge / count).toFixed(0)}`,
      points: 20,
    },
  ];
  const score = checks.reduce((total, check) => total + (check.pass ? check.points : 0), 0);
  return {
    ok: score >= 75,
    score,
    width: image.naturalWidth,
    height: image.naturalHeight,
    checks,
    model: "jalanlens-browser-photo-quality-v1",
  };
}

function renderCv(result, message) {
  state.lastCv = result;
  scanMeter.style.width = `${result?.score || 0}%`;
  cvStatus.textContent = message;
  cvStatus.className = `status ${result?.ok ? "ok" : "err"}`;
  cvChecks.innerHTML = (result?.checks || [])
    .map(
      (check) => `
        <div class="check">
          <span>${escapeHtml(check.label)} · ${escapeHtml(check.detail)}</span>
          <b>${check.pass ? "Pass" : "Fail"} (+${check.pass ? check.points : 0})</b>
        </div>`,
    )
    .join("");
}

async function resolveLivePart(externalId) {
  if (state.liveStreetParts.has(externalId)) {
    return state.liveStreetParts.get(externalId);
  }
  const rows = await rest(
    "street_parts",
    `select=id,external_id,midpoint_lng,midpoint_lat,desired_orientation&external_id=eq.${encodeURIComponent(externalId)}&limit=1`,
  );
  const part = rows[0];
  if (!part) {
    throw new Error("This Footpath is not available in the live Supabase registry.");
  }
  state.liveStreetParts.set(externalId, part);
  return part;
}

async function uploadObject(file, storagePath) {
  const response = await fetch(
    `${SUPABASE_URL}/storage/v1/object/street-photos/${storagePath}`,
    {
      method: "POST",
      headers: apiHeaders({
        "Content-Type": file.type || "image/jpeg",
        "x-upsert": "false",
      }),
      body: file,
    },
  );
  if (!response.ok) {
    throw new Error(`Photo upload failed: ${await response.text()}`);
  }
  return `${SUPABASE_URL}/storage/v1/object/public/street-photos/${storagePath}`;
}

async function submitPhoto(file) {
  const externalPartId = streetPartSelect.value;
  const part = await resolveLivePart(externalPartId);
  const footpathLabel = prettyPart(externalPartId);
  setStatus(photoUploadStatus, `Running the CV scan for ${footpathLabel}…`);
  selectStep("cv");
  const cv = await analyzePhoto(file);
  renderCv(
    cv,
    cv.ok
      ? `${footpathLabel} passed CV scanning with ${cv.score}/100. Submitting for staff review…`
      : `${footpathLabel} was rejected by CV with ${cv.score}/100. This file was not uploaded.`,
  );
  if (!cv.ok) {
    throw new Error("The image did not pass CV scanning. Review the failed checks in step 2.");
  }

  const externalId = `crowd_${part.external_id}_${Date.now()}`;
  const safeName =
    file.name.replace(/[^a-z0-9._-]+/gi, "_").slice(-80) || "photo.jpg";
  const storagePath = `${part.external_id}/${externalId}_${safeName}`;
  const imageUrl = await uploadObject(file, storagePath);
  const photo = await insert("street_photos", {
    external_id: externalId,
    street_part_id: part.id,
    source: "crowd",
    source_image_id: externalId,
    image_url: imageUrl,
    storage_path: storagePath,
    lng: part.midpoint_lng,
    lat: part.midpoint_lat,
    desired_orientation: part.desired_orientation || "road_right",
    direction_valid: true,
    direction_confidence: Math.min(1, cv.score / 100),
    quality_score: cv.score,
    is_pano: false,
    is_active: false,
    validation_status: "needs_review",
    selected_reason: "crowd_upload_cv_passed_pending_staff",
    metadata: {
      cv_validation: cv,
      original_filename: file.name,
      file_size: file.size,
    },
  });
  await insert("photo_review_jobs", {
    photo_id: photo.id,
    submitted_by_user_external_id: state.user.external_id || "anonymous_public",
    company_external_id:
      state.user.company_external_id ||
      state.user.organization ||
      "jalanlens_demo_company",
    street_part_external_id: part.external_id,
    review_stage: "staff_review",
    cv_review_status: "passed",
    human_review_status: "pending",
    assigned_staff_external_ids: [],
    progress_payload: {
      cv,
      status_steps: ["Upload", "CV first review", "Staff review", "Approved"],
    },
  });
  renderCv(cv, `${footpathLabel} submitted successfully. CV passed (${cv.score}/100) and staff review is pending.`);
  setStatus(photoUploadStatus, `${footpathLabel} photo submitted and waiting for staff review.`, "ok");
  await loadMySubmissions();
  selectStep("upload");
}

function statusBadge(job) {
  const value =
    job.review_stage === "approved"
      ? "Approved"
      : job.review_stage === "rejected"
        ? "Rejected"
        : "Submitted";
  const className = value.toLowerCase();
  return `<span class="badge ${className}">${value}</span>`;
}

function submissionCard(job, selected = false) {
  const photo = state.photos.find((item) => item.id === job.photo_id) || {};
  return `
    <button type="button" class="submission${selected ? " selected" : ""}" data-job-id="${escapeHtml(job.id)}">
      <img src="${escapeHtml(photo.image_url || "")}" alt="" />
      <span>
        <b>${escapeHtml(prettyPart(job.street_part_external_id))}</b>
        <small>${escapeHtml(formatDate(job.created_at))}</small>
        ${statusBadge(job)}
      </span>
    </button>`;
}

async function loadWorkflowData() {
  const [jobs, photos, comments] = await Promise.all([
    rest("photo_review_jobs", "select=*&order=created_at.desc").catch(() => []),
    rest(
      "street_photos",
      "select=id,external_id,street_part_id,image_url,quality_score,is_active,validation_status,metadata,submitted_at&source=eq.crowd&order=submitted_at.desc",
    ).catch(() => []),
    rest("photo_review_comments", "select=*&order=created_at.asc").catch(() => []),
  ]);
  state.jobs = jobs;
  state.photos = photos;
  state.comments = comments;
}

async function loadMySubmissions() {
  await loadWorkflowData();
  const userId = state.user.external_id || "anonymous_public";
  const mine = state.jobs.filter(
    (job) =>
      job.submitted_by_user_external_id === userId ||
      (userId === "anonymous_public" &&
        job.submitted_by_user_external_id === "anonymous_public"),
  );
  mySubmissions.innerHTML = mine.length
    ? mine.map((job) => submissionCard(job)).join("")
    : '<div class="empty">No submitted photos yet.</div>';
}

async function loadReviewQueue() {
  if (state.role !== "authority") return;
  setStatus(reviewQueueStatus, "Loading review queue…");
  await loadWorkflowData();
  const pending = state.jobs.filter(
    (job) =>
      job.review_stage === "staff_review" &&
      job.cv_review_status === "passed" &&
      job.human_review_status === "pending",
  );
  reviewQueue.innerHTML = pending.length
    ? pending
        .map((job) => submissionCard(job, job.id === state.selectedJobId))
        .join("")
    : '<div class="empty">No photos are waiting for staff review.</div>';
  setStatus(
    reviewQueueStatus,
    `${pending.length} submission${pending.length === 1 ? "" : "s"} waiting.`,
    pending.length ? "warn" : "ok",
  );
  reviewQueue.querySelectorAll("[data-job-id]").forEach((button) => {
    button.onclick = () => showReviewDetail(button.dataset.jobId);
  });
  if (state.selectedJobId && !pending.some((job) => job.id === state.selectedJobId)) {
    state.selectedJobId = null;
    reviewDetail.innerHTML = '<div class="empty">Select a submission to review it.</div>';
  }
}

function showReviewDetail(jobId) {
  state.selectedJobId = jobId;
  const job = state.jobs.find((item) => item.id === jobId);
  const photo = state.photos.find((item) => item.id === job?.photo_id);
  if (!job || !photo) {
    reviewDetail.innerHTML = '<div class="empty">Submission details are unavailable.</div>';
    return;
  }
  const cv = job.progress_payload?.cv || photo.metadata?.cv_validation || {};
  const comments = state.comments.filter((comment) => comment.review_job_id === job.id);
  reviewDetail.innerHTML = `
    <h2>${escapeHtml(prettyPart(job.street_part_external_id))}</h2>
    <img class="detail-image" src="${escapeHtml(photo.image_url)}" alt="Submitted footpath photo" />
    <div class="meta-grid">
      <div>Submitted by<b>${escapeHtml(job.submitted_by_user_external_id || "Anonymous")}</b></div>
      <div>Submitted<b>${escapeHtml(formatDate(job.created_at))}</b></div>
      <div>CV score<b>${escapeHtml(cv.score ?? photo.quality_score ?? "—")}/100</b></div>
      <div>Image size<b>${escapeHtml(cv.width || "—")} × ${escapeHtml(cv.height || "—")}</b></div>
    </div>
    <h3>Review comments</h3>
    <div class="comments">
      ${
        comments.length
          ? comments
              .map(
                (comment) =>
                  `<div class="comment"><b>${escapeHtml(comment.author_external_id || "Staff")}</b><br>${escapeHtml(comment.body)}</div>`,
              )
              .join("")
          : '<div class="empty">No comments yet.</div>'
      }
    </div>
    <label for="staffComment">Comment</label>
    <textarea id="staffComment" maxlength="2000" placeholder="Explain the approval, rejection, or any issue staff noticed."></textarea>
    <div class="button-row">
      <button type="button" class="approve" id="approvePhotoBtn">Approve photo</button>
      <button type="button" class="reject" id="rejectPhotoBtn">Reject</button>
    </div>
    <div id="reviewDecisionStatus" class="status" role="status"></div>`;
  approvePhotoBtn.onclick = () => decideReview("approved");
  rejectPhotoBtn.onclick = () => decideReview("rejected");
  loadReviewQueue();
}

async function decideReview(decision) {
  const comment = staffComment.value.trim();
  if (decision === "rejected" && !comment) {
    setStatus(reviewDecisionStatus, "Add a comment explaining why the photo is rejected.", "err");
    staffComment.focus();
    return;
  }
  approvePhotoBtn.disabled = true;
  rejectPhotoBtn.disabled = true;
  setStatus(reviewDecisionStatus, `Saving ${decision} decision…`);
  try {
    await rpc("review_photo_submission", {
      p_job_id: state.selectedJobId,
      p_decision: decision,
      p_reviewer_external_id: state.user.external_id || "authority_staff",
      p_comment: comment || null,
    });
    setStatus(reviewDecisionStatus, `Photo ${decision}.`, "ok");
    state.selectedJobId = null;
    await loadReviewQueue();
    await loadApprovedPhotos();
  } catch (error) {
    setStatus(reviewDecisionStatus, error.message, "err");
    approvePhotoBtn.disabled = false;
    rejectPhotoBtn.disabled = false;
  }
}

async function loadApprovedPhotos() {
  setStatus(approvedStatus, "Loading approved photos by Footpath…");
  try {
    const [approved, active] = await Promise.all([
      rest(
        "street_photos",
        "select=id,external_id,street_part_id,image_url,quality_score,submitted_at,source,is_active,validation_status,street_parts!street_photos_street_part_id_fkey!inner(external_id)&source=eq.crowd&validation_status=eq.accepted&order=submitted_at.desc",
      ),
      rest(
        "street_photos",
        "select=id,external_id,street_part_id,image_url,quality_score,submitted_at,source,is_active,validation_status,street_parts!street_photos_street_part_id_fkey!inner(external_id)&is_active=eq.true&order=submitted_at.desc",
      ),
    ]);
    state.activePhotos = active;
    const footpathGroups = new Map();
    approved.forEach((photo) => {
      const partId = photo.street_parts?.external_id || photo.street_part_id;
      if (!footpathGroups.has(partId)) footpathGroups.set(partId, []);
      footpathGroups.get(partId).push(photo);
    });
    approvedGallery.innerHTML = footpathGroups.size
      ? [...footpathGroups.entries()]
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([partId, photos]) => {
            const current = active.find(
              (photo) => photo.street_part_id === photos[0]?.street_part_id,
            );
            return `
              <details class="footpath-toggle">
                <summary>
                  <span>${escapeHtml(prettyPart(partId))}</span>
                  <small>${photos.length} approved image${photos.length === 1 ? "" : "s"} · ${current ? "active selected" : "no active photo"}</small>
                </summary>
                <div class="footpath-content">
                  <div class="approved-group-head">
                    <h3>${escapeHtml(prettyPart(partId))}</h3>
                    <span class="current-label">${current ? "Active photo selected" : "No active photo"}</span>
                  </div>
                  <div class="gallery">
                    ${photos
                      .map(
                        (photo) => `
                          <article class="card gallery-card">
                            <img src="${escapeHtml(photo.image_url)}" alt="Approved footpath evidence" />
                            <div>
                              <b>${photo.id === current?.id ? "Current active photo" : "Approved candidate"}</b>
                              <p>CV score ${escapeHtml(photo.quality_score ?? "—")}/100<br>Approved submission from ${escapeHtml(formatDate(photo.submitted_at))}</p>
                              ${
                                photo.id === current?.id
                                  ? '<span class="badge approved">Active evidence</span>'
                                  : state.role === "authority"
                                    ? `<button type="button" class="candidate-action" data-activate-photo-id="${escapeHtml(photo.id)}">View and make active</button>`
                                    : '<span class="badge approved">Approved</span>'
                              }
                            </div>
                          </article>`,
                      )
                      .join("")}
                  </div>
                </div>
              </details>`;
          })
          .join("")
      : '<div class="empty">No photos have been approved yet.</div>';
    approvedGallery.querySelectorAll("[data-activate-photo-id]").forEach((button) => {
      button.onclick = () => openActivationModal(button.dataset.activatePhotoId, approved);
    });
    setStatus(
      approvedStatus,
      `${approved.length} approved photo${approved.length === 1 ? "" : "s"} across ${footpathGroups.size} footpath${footpathGroups.size === 1 ? "" : "s"}.`,
      "ok",
    );
  } catch (error) {
    approvedGallery.innerHTML = "";
    setStatus(approvedStatus, error.message, "err");
  }
}

function photoPreview(photo, emptyMessage) {
  return photo?.image_url
    ? `<img src="${escapeHtml(photo.image_url)}" alt="" />`
    : `<div class="no-current-photo">${escapeHtml(emptyMessage)}</div>`;
}

function openActivationModal(photoId, approvedPhotos) {
  if (state.role !== "authority") return;
  const candidate = approvedPhotos.find((photo) => photo.id === photoId);
  if (!candidate || candidate.validation_status !== "accepted") return;
  const current =
    state.activePhotos.find(
      (photo) => photo.street_part_id === candidate.street_part_id,
    ) || null;
  state.activationCandidate = candidate;
  currentPhotoPreview.innerHTML = photoPreview(
    current,
    "This Footpath does not currently have an active photo.",
  );
  newPhotoPreview.innerHTML = photoPreview(candidate, "Replacement photo unavailable.");
  currentPhotoMeta.textContent = current
    ? `${current.source || "Unknown source"} · ${formatDate(current.submitted_at)}`
    : "No current evidence";
  newPhotoMeta.textContent =
    `CV ${candidate.quality_score ?? "—"}/100 · ${formatDate(candidate.submitted_at)}`;
  activationModalTitle.textContent = current
    ? `Replace the active photo for ${prettyPart(candidate.street_parts?.external_id)}?`
    : `Make this photo active for ${prettyPart(candidate.street_parts?.external_id)}?`;
  confirmActivationBtn.textContent = current
    ? "Confirm replacement"
    : "Confirm activation";
  setStatus(activationStatus, "");
  activationModal.hidden = false;
  confirmActivationBtn.focus();
}

function closeActivationModal() {
  if (confirmActivationBtn.disabled) return;
  activationModal.hidden = true;
  state.activationCandidate = null;
}

async function confirmActivation() {
  const candidate = state.activationCandidate;
  if (!candidate) return;
  confirmActivationBtn.disabled = true;
  cancelActivationBtn.disabled = true;
  setStatus(activationStatus, "Updating active evidence in Supabase…");
  try {
    await rpc("activate_approved_photo", {
      p_photo_id: candidate.id,
      p_actor_external_id: state.user.external_id || "authority_staff",
    });
    setStatus(activationStatus, "Active photo updated.", "ok");
    confirmActivationBtn.disabled = false;
    cancelActivationBtn.disabled = false;
    activationModal.hidden = true;
    state.activationCandidate = null;
    await loadApprovedPhotos();
  } catch (error) {
    setStatus(activationStatus, error.message, "err");
    confirmActivationBtn.disabled = false;
    cancelActivationBtn.disabled = false;
  }
}

function applyRole() {
  roleBadge.textContent =
    state.role === "authority" ? "Authority staff" : "Public contributor";
  const authority = state.role === "authority";
  staffOnlyNotice.hidden = authority;
  staffWorkspace.hidden = !authority;
}

document.querySelectorAll(".step-tab").forEach((tab) => {
  tab.onclick = () => selectStep(tab.dataset.step);
});
photoUploadBtn.onclick = () => photoUploadInput.click();
photoUploadInput.onchange = async () => {
  const file = photoUploadInput.files?.[0];
  photoUploadInput.value = "";
  if (!file) return;
  photoUploadBtn.disabled = true;
  try {
    await submitPhoto(file);
  } catch (error) {
    setStatus(photoUploadStatus, error.message || "Photo submission failed.", "err");
  } finally {
    photoUploadBtn.disabled = !state.streetParts.length;
  }
};
refreshQueueBtn.onclick = loadReviewQueue;
refreshApprovedBtn.onclick = loadApprovedPhotos;
confirmActivationBtn.onclick = confirmActivation;
cancelActivationBtn.onclick = closeActivationModal;
activationModal.onclick = (event) => {
  if (event.target === activationModal) closeActivationModal();
};
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !activationModal.hidden) closeActivationModal();
});

applyRole();
Promise.all([loadStreetParts(), loadMySubmissions()]).catch((error) => {
  setStatus(photoUploadStatus, error.message, "err");
});
