const SEGMENTS = {
  intro: { name: "片头", startOptional: true },
  recap: { name: "回顾", startOptional: true },
  credits: { name: "片尾", endOptional: true },
  preview: { name: "预告", endOptional: true },
};

const state = {
  view: "home",
  sessionsBusy: false,
  detail: null,
  formSegment: null,
  settingsLoaded: false,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    const error = new Error(data?.error?.message || `请求失败 (${response.status})`);
    error.code = data?.error?.code;
    throw error;
  }
  return data;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
}

function showToast(title, detail = "") {
  const toast = $("#toast");
  $("strong", toast).textContent = title;
  $("span", toast).textContent = detail;
  toast.classList.add("show");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => toast.classList.remove("show"), 2600);
}

function showView(name) {
  state.view = name;
  $$(".view").forEach(view => view.classList.toggle("active", view.id === `view-${name}`));
  $$(".nav-btn").forEach(button => button.classList.toggle("active", button.dataset.view === name));
  if (name === "home") refreshSessions();
  if (name === "settings") loadSettings();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

document.addEventListener("click", event => {
  const target = event.target.closest("[data-view]");
  if (target) showView(target.dataset.view);
});

async function refreshSessions() {
  if (state.sessionsBusy || state.view !== "home" || document.hidden) return;
  state.sessionsBusy = true;
  try {
    const sessions = await api("/api/sessions");
    renderSessions(sessions);
    setSyncStatus("ok", "Emby 已连接", "刚刚同步");
  } catch (error) {
    renderSessionError(error);
    setSyncStatus("error", error.code === "SETTINGS_REQUIRED" ? "Emby 尚未配置" : "Emby 连接失败", "需要处理");
  } finally {
    state.sessionsBusy = false;
  }
}

function setSyncStatus(kind, title, detail) {
  const element = $("#sync-status");
  element.className = `sync-status${kind === "error" ? " is-error" : kind === "loading" ? " is-loading" : ""}`;
  $("strong", element).textContent = title;
  $("span", element).textContent = detail;
}

function renderSessions(sessions) {
  const container = $("#sessions");
  $("#session-count").textContent = sessions.length ? `${sessions.length} 台设备` : "";
  if (!sessions.length) {
    if (!$(".state-card[data-empty]", container)) {
      container.innerHTML = `<div class="state-card" data-empty><h3>现在很安静</h3><p>当前没有带 TMDb ID 的电影或剧集正在播放。</p></div>`;
    }
    return;
  }

  $(".state-card", container)?.remove();
  const existing = new Map($$(".session-card", container).map(card => [card.dataset.key, card]));

  sessions.forEach((session, index) => {
    const key = sessionKey(session);
    let card = existing.get(key);
    const needsProgress = session.progress_percent != null;
    if (!card || Boolean($(".progress-wrap", card)) !== needsProgress) {
      card?.remove();
      card = createSessionCard(session, key);
    }
    updateSessionCard(card, session);

    const current = container.children[index];
    if (current !== card) container.insertBefore(card, current || null);
    existing.delete(key);
  });

  existing.forEach(card => card.remove());
}

function sessionKey(session) {
  return JSON.stringify([session.session_id, session.item_id]);
}

function createSessionCard(session, key) {
  const progress = session.progress_percent == null ? "" : `
    <span class="progress-wrap">
      <span class="progress-label"><span class="elapsed"></span><span class="progress-total"></span></span>
      <span class="progress"><i></i></span>
    </span>`;
  const template = document.createElement("template");
  template.innerHTML = `<button class="session-card">
    <span class="poster"><img alt="" loading="lazy" decoding="async" onerror="this.classList.add('is-error')"></span>
    <span class="session-info">
      <span class="live-row"><span class="live-chip"></span><span class="tag"></span></span>
      <h3></h3><span class="episode-line"></span><span class="meta"></span>${progress}
    </span>
  </button>`;
  const card = template.content.firstElementChild;
  card.dataset.key = key;
  return card;
}

function updateSessionCard(card, session) {
  card.dataset.session = session.session_id;
  card.dataset.item = session.item_id;

  const image = $(".poster img", card);
  if (image.dataset.src !== session.poster_url) {
    image.dataset.src = session.poster_url;
    image.alt = `${session.title} 海报`;
    image.classList.remove("is-error");
    image.src = session.poster_url;
  }

  const liveChip = $(".live-chip", card);
  liveChip.classList.toggle("paused", session.is_paused);
  liveChip.textContent = session.is_paused ? "Ⅱ 已暂停" : "▶ 播放中";
  $(".tag", card).textContent = session.item_type === "episode" ? "剧集" : "电影";
  $("h3", card).textContent = session.title;
  $(".episode-line", card).textContent = session.item_type === "episode"
    ? `S${pad(session.season)} E${pad(session.episode)}${session.episode_title ? ` · ${session.episode_title}` : ""}`
    : "电影";
  $(".meta", card).textContent = `${session.user_name} · ${session.client} ${session.device_name}`;

  if (session.progress_percent != null) {
    const progress = Math.max(0, Math.min(100, session.progress_percent));
    const rounded = Math.round(progress);
    $(".elapsed", card).textContent = formatClock(session.position_ms);
    $(".progress-total", card).textContent = `${rounded}% · ${formatClock(session.duration_ms)}`;
    const progressBar = $(".progress", card);
    progressBar.setAttribute("aria-label", `播放进度 ${rounded}%`);
    $(".progress i", card).style.setProperty("--progress", `${progress}%`);
  }
}

function renderSessionError(error) {
  $("#session-count").textContent = "";
  const needsSettings = ["SETTINGS_REQUIRED", "EMBY_UNAUTHORIZED"].includes(error.code);
  $("#sessions").innerHTML = `<div class="state-card"><h3>${escapeHtml(error.message)}</h3><p>${needsSettings ? "请检查 Server URL 与 API Key。" : "请确认 Emby 正在运行且当前设备可以访问。"}</p><button class="secondary" data-view="${needsSettings ? "settings" : "home"}" id="state-action">${needsSettings ? "前往设置" : "重新连接"}</button></div>`;
  $("#state-action")?.addEventListener("click", () => needsSettings ? showView("settings") : refreshSessions());
}

$("#sessions").addEventListener("click", event => {
  const card = event.target.closest(".session-card");
  if (card) openDetail(card.dataset.session, card.dataset.item);
});

async function openDetail(sessionId, itemId) {
  showView("editor");
  $("#editor-loading").hidden = false;
  $("#editor-loading").innerHTML = `<span class="loader"></span><h3>正在加载影片信息</h3>`;
  $("#editor-content").hidden = true;
  try {
    const detail = await api(`/api/sessions/${encodeURIComponent(sessionId)}?item_id=${encodeURIComponent(itemId)}`);
    state.detail = detail;
    state.formSegment = { type: "intro", start_ms: null, end_ms: null };
    renderDetail();
    $("#editor-loading").hidden = true;
    $("#editor-content").hidden = false;
  } catch (error) {
    $("#editor-loading").innerHTML = `<h3>${escapeHtml(error.message)}</h3><p>返回正在播放页面后可以重新选择设备。</p><button class="secondary" data-view="home">返回正在播放</button>`;
  }
}

function renderDetail() {
  const detail = state.detail;
  $("#detail-poster").src = detail.poster_url;
  $("#detail-poster").classList.remove("is-error");
  $("#detail-poster").onerror = event => event.currentTarget.classList.add("is-error");
  $("#detail-tag").textContent = `${detail.item_type === "episode" ? "电视剧" : "电影"}${detail.year ? ` · ${detail.year}` : ""}`;
  $("#detail-title").textContent = detail.title;
  $("#detail-episode").textContent = detail.item_type === "episode" ? `S${pad(detail.season)} E${pad(detail.episode)} · ${detail.episode_title || ""}` : "";
  $("#detail-meta").textContent = `TMDb ${detail.tmdb_id} · Emby 条目 ${detail.item_id}`;
  $("#timeline-duration").textContent = formatClock(detail.duration_ms);
  updateTypeButtons();
  renderSegmentEditor();
  renderTimeline();
}

function renderTimeline() {
  const duration = state.detail?.duration_ms;
  const { type } = state.formSegment;
  const inputs = $$(".time-input", $("#segments"));
  const readable = inputs.length === 2 && inputs.every(input => !input.value.trim() || parseTime(input.value) != null);
  const canPreview = requiredFieldsPresent() && readable;
  const start = inputs[0]?.value.trim() ? parseTime(inputs[0].value) : 0;
  const end = inputs[1]?.value.trim() ? parseTime(inputs[1].value) : duration;
  if (!duration) {
    $("#timeline-panel").hidden = true;
    return;
  }
  $("#timeline-panel").hidden = false;
  $("#timeline").innerHTML = canPreview
    ? `<span class="${type}" style="left:${Math.max(0, start / duration * 100)}%;width:${Math.max(.2, (end - start) / duration * 100)}%" title="${SEGMENTS[type].name}"></span>`
    : "";
  $("#timeline-label").textContent = `${SEGMENTS[type].name}提交预览`;
  $("#timeline-legend").innerHTML = `<span><i style="--color:var(--${type === "intro" ? "orange" : type === "recap" ? "blue" : type === "credits" ? "purple" : "teal"})"></i>${SEGMENTS[type].name}</span>`;
}

function renderSegmentEditor() {
  const { type, ...interval } = state.formSegment;
  const config = SEGMENTS[type];
  const hasValue = interval.start_ms != null || interval.end_ms != null;
  $("#segments").innerHTML = `<article class="segment-card ${type}" data-kind="${type}">
    <div class="segment-title"><h3><i></i>${config.name}</h3><button class="clear-segment" ${hasValue ? "" : "hidden"}>清空时间</button></div>
    ${timeBlock(type, "start_ms", interval.start_ms, config.startOptional)}
    ${timeBlock(type, "end_ms", interval.end_ms, config.endOptional)}
  </article>`;
  updateSubmitButton();
}

function timeBlock(kind, field, value, optional) {
  const label = field === "start_ms" ? "START" : "END";
  return `<div class="time-block">
    <div class="time-label"><span>${label}</span><span>${optional ? "可为空" : "必填"}</span></div>
    <div class="time-row"><input class="time-input" value="${value == null ? "" : formatTime(value)}" ${optional ? 'placeholder="可为空"' : ""} inputmode="decimal" data-field="${field}" aria-label="${SEGMENTS[kind].name}${label}"><button class="capture">获取进度</button></div>
    <div class="adjust-row"><button class="adjust" data-delta="-1000">−1s</button><button class="adjust" data-delta="-100">−0.1s</button><button class="adjust" data-delta="100">+0.1s</button><button class="adjust" data-delta="1000">+1s</button></div>
  </div>`;
}

$("#segment-type-picker").addEventListener("click", event => {
  const button = event.target.closest("button[data-kind]");
  if (!button || button.dataset.kind === state.formSegment.type) return;
  if (!syncAllInputs()) {
    showToast("时间格式有误", "请先修正标红的时间输入框");
    return;
  }
  state.formSegment.type = button.dataset.kind;
  updateTypeButtons();
  renderSegmentEditor();
  renderTimeline();
});

function updateTypeButtons() {
  $$("button[data-kind]", $("#segment-type-picker")).forEach(button => {
    const active = button.dataset.kind === state.formSegment.type;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

$("#segments").addEventListener("click", async event => {
  const card = event.target.closest(".segment-card");
  if (!card) return;
  if (event.target.closest(".clear-segment")) {
    state.formSegment.start_ms = null;
    state.formSegment.end_ms = null;
    renderSegmentEditor(); renderTimeline(); showToast("已清空时间", "请选择或获取新的播放位置");
  } else if (event.target.closest(".adjust")) {
    const input = $(".time-input", event.target.closest(".time-block"));
    const current = readInput(input, false) ?? 0;
    setInput(input, Math.max(0, current + Number(event.target.closest(".adjust").dataset.delta)));
  } else if (event.target.closest(".capture")) {
    const button = event.target.closest(".capture");
    const input = $(".time-input", button.closest(".time-block"));
    await capturePosition(button, input);
  }
});

$("#segments").addEventListener("input", event => {
  if (!event.target.matches(".time-input")) return;
  event.target.classList.remove("invalid");
  updateModelFromInput(event.target, false);
});

$("#segments").addEventListener("focusout", event => {
  if (!event.target.matches(".time-input") || !event.target.value.trim()) return;
  const value = readInput(event.target, true);
  if (value != null) setInput(event.target, value);
});

function readInput(input, flagInvalid = true) {
  const value = input.value.trim();
  if (!value) return null;
  const parsed = parseTime(value);
  input.classList.toggle("invalid", parsed == null && flagInvalid);
  return parsed;
}

function updateModelFromInput(input, strict) {
  const value = readInput(input, strict);
  if (input.value.trim() && value == null) {
    updateSubmitButton(); renderTimeline(); updateClearButton();
    return false;
  }
  state.formSegment[input.dataset.field] = value;
  updateSubmitButton(); renderTimeline(); updateClearButton();
  return true;
}

function setInput(input, value) {
  input.value = formatTime(value);
  input.classList.remove("invalid");
  updateModelFromInput(input, true);
}

function updateClearButton() {
  const card = $(".segment-card", $("#segments"));
  if (!card) return;
  $(".clear-segment", card).hidden = !$$('.time-input', card).some(input => input.value.trim());
}

async function capturePosition(button, input) {
  button.disabled = true;
  try {
    const detail = state.detail;
    const data = await api(`/api/sessions/${encodeURIComponent(detail.session_id)}/position?item_id=${encodeURIComponent(detail.item_id)}`);
    setInput(input, data.position_ms);
    showToast("已获取播放进度", `${data.device_name} · ${formatTime(data.position_ms)}`);
  } catch (error) {
    showToast("获取失败", error.message);
  } finally {
    button.disabled = false;
  }
}

function updateSubmitButton() {
  if (!state.formSegment) return;
  const button = $("#submit-btn");
  button.textContent = `提交${state.detail?.item_type === "episode" ? "本集" : "本片"}${SEGMENTS[state.formSegment.type].name}`;
  button.disabled = !requiredFieldsPresent();
  button.title = button.disabled ? "请填写必填时间" : "";
}

function requiredFieldsPresent() {
  if (!state.formSegment) return false;
  const { type, start_ms: start, end_ms: end } = state.formSegment;
  const inputs = $$(".time-input", $("#segments"));
  if (inputs.length === 2) {
    const required = type === "intro" || type === "recap" ? inputs[1] : inputs[0];
    return Boolean(required.value.trim() && parseTime(required.value) != null);
  }
  return type === "intro" || type === "recap" ? end != null : start != null;
}

$("#submit-btn").addEventListener("click", async event => {
  const button = event.currentTarget;
  if (!syncAllInputs()) return showToast("时间格式有误", "请检查标红的时间输入框");
  const segment = { ...state.formSegment };
  if (segment.start_ms == null && segment.end_ms == null) return showToast("还没有填写分段时间");
  const detail = state.detail;
  button.disabled = true;
  button.textContent = "正在提交…";
  try {
    const data = await api("/api/submit", { method: "POST", body: JSON.stringify({
      session_id: detail.session_id,
      item_id: detail.item_id,
      media: { type: detail.item_type, tmdb_id: detail.tmdb_id, season: detail.season, episode: detail.episode, duration_ms: detail.duration_ms },
      segment,
    }) });
    showResult(data.result);
  } catch (error) {
    showToast("提交失败", error.message);
  } finally {
    button.disabled = false;
    updateSubmitButton();
  }
});

function syncAllInputs() {
  return $$(".time-input", $("#segments")).map(input => updateModelFromInput(input, true)).every(Boolean);
}

function showResult(result) {
  const success = ["success", "duplicate"].includes(result.status);
  $("#result-summary").textContent = success ? "这个分段已成功提交或已存在。" : "这个分段未能提交。";
  $("#result-list").innerHTML = `<div class="result-item ${escapeHtml(result.status)}"><b>${SEGMENTS[result.type]?.name || result.type}</b><span>${escapeHtml(result.message)}</span></div>`;
  $("#result-sheet").classList.add("show");
}

$("#close-result").addEventListener("click", () => $("#result-sheet").classList.remove("show"));
$("#result-sheet").addEventListener("click", event => { if (event.target.id === "result-sheet") event.currentTarget.classList.remove("show"); });

async function loadSettings() {
  if (state.settingsLoaded) return;
  try {
    const data = await api("/api/settings");
    $("#emby-url").value = data.emby.server_url || "";
    $("#emby-key").placeholder = data.emby.api_key_masked ? `已配置 ${data.emby.api_key_masked}` : "";
    $("#tidb-key").placeholder = data.theintrodb.api_key_masked ? `已配置 ${data.theintrodb.api_key_masked}` : "";
    state.settingsLoaded = true;
  } catch (error) { showToast("读取设置失败", error.message); }
}

$("#emby-form").addEventListener("submit", async event => {
  event.preventDefault();
  await saveSettings({ emby: embyFormData() }, event.submitter);
});

$("#tidb-form").addEventListener("submit", async event => {
  event.preventDefault();
  await saveSettings({ theintrodb: tidbFormData() }, event.submitter);
});

async function saveSettings(payload, button) {
  button.disabled = true;
  try {
    await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
    showToast("设置已保存");
    state.settingsLoaded = false;
    $("#emby-key").value = ""; $("#tidb-key").value = "";
    await loadSettings();
  } catch (error) { showToast("保存失败", error.message); }
  finally { button.disabled = false; }
}

$$('[data-test]').forEach(button => button.addEventListener("click", async () => {
  const kind = button.dataset.test;
  button.disabled = true;
  try {
    const body = kind === "emby" ? embyFormData() : tidbFormData();
    const data = await api(`/api/settings/test-${kind}`, { method: "POST", body: JSON.stringify(body) });
    showToast(kind === "emby" ? "Emby 连接正常" : "TheIntroDB API Key 有效", data.server_name || "测试通过");
  } catch (error) { showToast("测试失败", error.message); }
  finally { button.disabled = false; }
}));

function embyFormData() { return { server_url: $("#emby-url").value.trim(), api_key: $("#emby-key").value.trim() || null }; }
function tidbFormData() { return { api_key: $("#tidb-key").value.trim() || null }; }

function parseTime(value) {
  const match = value.trim().match(/^(\d{1,2}):(\d{1,2}):(\d{1,2})(?:\.(\d{1,3}))?$/);
  if (!match) return null;
  const [, hours, minutes, seconds, fraction = ""] = match;
  if (Number(minutes) >= 60 || Number(seconds) >= 60) return null;
  const milliseconds = Number(fraction.padEnd(3, "0"));
  const total = ((Number(hours) * 60 + Number(minutes)) * 60 + Number(seconds)) * 1000 + milliseconds;
  return total <= 21_600_000 ? total : null;
}

function formatTime(value) {
  const rounded = Math.max(0, Math.round(value / 100) * 100);
  const hours = Math.floor(rounded / 3_600_000);
  const minutes = Math.floor(rounded % 3_600_000 / 60_000);
  const seconds = Math.floor(rounded % 60_000 / 1000);
  const tenths = Math.floor(rounded % 1000 / 100);
  return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}.${tenths}`;
}

function formatClock(value) {
  if (value == null) return "--:--:--";
  const seconds = Math.floor(value / 1000);
  return `${pad(Math.floor(seconds / 3600))}:${pad(Math.floor(seconds % 3600 / 60))}:${pad(seconds % 60)}`;
}

function pad(value) { return String(value ?? 0).padStart(2, "0"); }
document.addEventListener("visibilitychange", () => { if (!document.hidden && state.view === "home") refreshSessions(); });
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}
setInterval(refreshSessions, 3000);
refreshSessions();
