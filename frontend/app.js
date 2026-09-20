const API = "/api";
let currentTrackId = null;
let pollTimer = null;

function fmtSize(bytes) {
  if (!bytes) return "-";
  const mb = bytes / (1024 * 1024);
  return `${mb.toFixed(1)} MB`;
}

function fmtScore(v) {
  return v === null || v === undefined ? "-" : `${Math.round(v)}%`;
}

async function api(path, opts) {
  const resp = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`${resp.status}: ${body}`);
  }
  return resp.status === 204 ? null : resp.json();
}

// ---- Tabs -------------------------------------------------------------

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
    if (btn.dataset.tab === "downloads") loadDownloads();
    if (btn.dataset.tab === "library") loadLibrary();
  });
});

// ---- Settings -----------------------------------------------------------

async function loadSettings() {
  const s = await api("/settings");
  document.getElementById("mode-select").value = s.mode;
  document.getElementById("strict-flac-toggle").checked = s.strict_flac_only;
}

document.getElementById("mode-select").addEventListener("change", async (e) => {
  await api("/settings", { method: "PUT", body: JSON.stringify({ mode: e.target.value }) });
});

document.getElementById("strict-flac-toggle").addEventListener("change", async (e) => {
  await api("/settings", { method: "PUT", body: JSON.stringify({ strict_flac_only: e.target.checked }) });
});

document.getElementById("reset-all-btn").addEventListener("click", async () => {
  if (!confirm("Clear all imported tracks, searches, downloads and logs?\n\n(Files already saved into your library folder on disk are NOT deleted.)")) {
    return;
  }
  await api("/admin/reset", { method: "POST" });
  loadTracks();
  loadLogs();
  loadDownloads();
  loadLibrary();
});

// ---- Import / analyze ---------------------------------------------------

document.getElementById("analyze-text-btn").addEventListener("click", async () => {
  const text = document.getElementById("text-input").value;
  if (!text.trim()) return;
  await api("/import/text", { method: "POST", body: JSON.stringify({ text }) });
  startPolling();
});

document.getElementById("analyze-spotify-btn").addEventListener("click", async () => {
  const playlist_url = document.getElementById("spotify-url-input").value;
  if (!playlist_url.trim()) return;
  try {
    await api("/import/spotify", { method: "POST", body: JSON.stringify({ playlist_url }) });
    startPolling();
  } catch (e) {
    alert(`Spotify import failed: ${e.message}`);
  }
});

document.getElementById("analyze-file-btn").addEventListener("click", async () => {
  const fileInput = document.getElementById("file-input");
  if (!fileInput.files.length) return;
  const form = new FormData();
  form.append("file", fileInput.files[0]);
  const resp = await fetch(`${API}/import/file`, { method: "POST", body: form });
  if (!resp.ok) {
    alert(`Import failed: ${await resp.text()}`);
    return;
  }
  startPolling();
});

// ---- Tracks table + polling ---------------------------------------------

function startPolling() {
  loadTracks();
  loadLogs();
  if (pollTimer) return;
  pollTimer = setInterval(() => {
    loadTracks();
    loadLogs();
  }, 2000);
}

async function loadTracks() {
  const tracks = await api("/tracks");
  const tbody = document.getElementById("tracks-tbody");
  tbody.innerHTML = "";
  tracks.forEach((t, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${String(i + 1).padStart(2, "0")}</td>
      <td>${t.artist || "-"}</td>
      <td>${t.title || t.raw_line}</td>
      <td>${fmtScore(t.best_match_score)}</td>
      <td>${fmtScore(t.best_source_score)}</td>
      <td>${t.best_format || "-"}</td>
      <td>${fmtSize(t.best_size_bytes)}</td>
      <td><span class="status-pill status-${t.status}">${t.status}${t.status_reason ? " ⓘ" : ""}</span></td>
    `;
    tr.title = t.status_reason || "";
    tr.addEventListener("click", () => openCandidates(t));
    tbody.appendChild(tr);
  });
}

// ---- Candidate modal ------------------------------------------------------

async function openCandidates(track) {
  currentTrackId = track.id;
  document.getElementById("modal-title").textContent = `${track.artist || ""} - ${track.title || track.raw_line}`;
  const container = document.getElementById("modal-candidates");
  container.innerHTML = "Loading...";
  document.getElementById("candidate-modal").classList.remove("hidden");

  const candidates = await api(`/tracks/${track.id}/candidates`);
  if (!candidates.length) {
    container.innerHTML = "<p>No candidates yet.</p>";
    return;
  }

  container.innerHTML = "";
  candidates.slice(0, 10).forEach((c) => {
    const div = document.createElement("div");
    div.className = "candidate-row" + (c.review_required ? " review" : "");
    div.innerHTML = `
      <div class="candidate-meta">${c.username} — ${c.filename}</div>
      <div class="candidate-scores">
        <span class="score-badge">MATCH ${Math.round(c.match_score)}</span>
        <span class="score-badge">SOURCE ${Math.round(c.source_score)}</span>
        <span class="score-badge">${(c.extension || "?").toUpperCase()} ${c.bit_depth || "?"}/${c.sample_rate_hz ? (c.sample_rate_hz/1000).toFixed(1) : "?"}</span>
        <span class="score-badge">${fmtSize(c.size_bytes)}</span>
      </div>
      ${c.review_required ? `<div class="review-warning">⚠ Review required: ${c.review_reason || "ambiguous match"}</div>` : ""}
      <button data-candidate="${c.id}">Approve &amp; download</button>
    `;
    div.querySelector("button").addEventListener("click", () => approveCandidate(track.id, c.id));
    container.appendChild(div);
  });
}

async function approveCandidate(trackId, candidateId) {
  try {
    await api(`/tracks/${trackId}/approve`, { method: "POST", body: JSON.stringify({ candidate_id: candidateId }) });
    document.getElementById("candidate-modal").classList.add("hidden");
    loadTracks();
  } catch (e) {
    alert(`Approve failed: ${e.message}`);
  }
}

document.getElementById("modal-close-btn").addEventListener("click", () => {
  document.getElementById("candidate-modal").classList.add("hidden");
});

// ---- Downloads / Library --------------------------------------------------

async function loadDownloads() {
  const downloads = await api("/downloads");
  const tbody = document.getElementById("downloads-tbody");
  tbody.innerHTML = "";
  downloads.forEach((d) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${d.candidate_id.slice(0, 8)}</td>
      <td><span class="status-pill status-${d.state}">${d.state}</span></td>
      <td>${new Date(d.queued_at).toLocaleString()}</td>
      <td>${d.completed_at ? new Date(d.completed_at).toLocaleString() : "-"}</td>
      <td>${d.error || "-"}</td>
    `;
    tbody.appendChild(tr);
  });
}

async function loadLibrary() {
  const files = await api("/library");
  const tbody = document.getElementById("library-tbody");
  tbody.innerHTML = "";
  files.forEach((f) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${f.library_path || f.local_path}</td>
      <td>${f.verification_state}</td>
      <td>${f.codec || "-"}</td>
      <td>${f.sample_rate_hz ? (f.sample_rate_hz/1000).toFixed(1) + " kHz" : "-"}</td>
      <td>${f.bit_depth ? f.bit_depth + "-bit" : "-"}</td>
      <td>${f.channels || "-"}</td>
      <td>${f.duration_sec ? new Date(f.duration_sec * 1000).toISOString().substr(14, 5) : "-"}</td>
    `;
    tbody.appendChild(tr);
  });
}

// ---- Logs -----------------------------------------------------------------

async function loadLogs() {
  const entries = await api("/logs?limit=100");
  const el = document.getElementById("log-entries");
  el.innerHTML = entries
    .map((e) => `<div class="log-line">${new Date(e.created_at).toLocaleTimeString()} ${e.message}</div>`)
    .join("");
  el.scrollTop = el.scrollHeight;
}

// ---- Init -------------------------------------------------------------

loadSettings();
startPolling();
