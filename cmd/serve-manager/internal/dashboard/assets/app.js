const historyLimit = 180;
const points = [];

const els = {
  status: document.getElementById("status"),
  statusText: document.getElementById("status-text"),
  decodeRate: document.getElementById("decode-rate"),
  promptRate: document.getElementById("prompt-rate"),
  contextUsed: document.getElementById("context-used"),
  cacheUsed: document.getElementById("cache-used"),
  modelSource: document.getElementById("model-source"),
  bucketSummary: document.getElementById("bucket-summary"),
  slotState: document.getElementById("slot-state"),
  mtpState: document.getElementById("mtp-state"),
  decodeMean: document.getElementById("decode-mean"),
  decodedTotal: document.getElementById("decoded-total"),
  remainingTotal: document.getElementById("remaining-total"),
  observedAt: document.getElementById("observed-at"),
  timeline: document.getElementById("timeline"),
};

const ctx = els.timeline.getContext("2d");

function number(value, digits = 0) {
  if (value === undefined || value === null || Number.isNaN(value)) {
    return "--";
  }
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: digits,
  }).format(value);
}

function rate(snapshot, name, fallbackName) {
  const rates = snapshot.rates || {};
  const gauges = snapshot.gauges || {};
  if (typeof rates[name] === "number") {
    return rates[name];
  }
  if (typeof gauges[fallbackName] === "number") {
    return gauges[fallbackName];
  }
  return 0;
}

function primarySlot(snapshot) {
  const slots = snapshot.slots || [];
  return slots.find((slot) => slot.is_processing) || slots[0] || {};
}

function summaryMean(group, name) {
  const summary = group || {};
  return summary[name] && typeof summary[name].mean === "number"
    ? summary[name].mean
    : undefined;
}

function summaryLast(group, name) {
  const summary = group || {};
  return summary[name] && typeof summary[name].last === "number"
    ? summary[name].last
    : undefined;
}

function updateCards(snapshot, rolling, updateSummary = true) {
  const slot = primarySlot(snapshot);
  const history = snapshot.history || {};
  const historyRates = history.rates || {};
  const historySlots = history.slots || {};
  const decode = rate(
    snapshot,
    "predicted_tokens_per_second",
    "llamacpp:predicted_tokens_seconds",
  );
  const prompt = rate(
    snapshot,
    "prompt_tokens_per_second",
    "llamacpp:prompt_tokens_seconds",
  );

  if (updateSummary) {
    els.decodeRate.textContent = number(snapshot.rates?.predicted_tokens_per_second, 1);
    els.promptRate.textContent = number(snapshot.rates?.prompt_tokens_per_second, 1);
    els.contextUsed.textContent = number(rolling ? (rolling.context_available ? rolling.context : undefined) : slot.context_missing ? undefined : slot.n_prompt_tokens);
    els.cacheUsed.textContent = number(rolling ? (rolling.cache_available ? rolling.cache : undefined) : slot.cache_missing ? undefined : slot.n_prompt_tokens_cache);
    for (const metric of ["decode", "prompt", "context", "cache"]) updateBoxPlot(metric, rolling?.distributions?.[metric]);
    const observed = number(rolling?.observed_seconds, 0);
    document.getElementById("decode-bottom").textContent = rolling?.distributions?.decode ? `${number(rolling.generated)} tokens generated / ${observed}s observed` : "Collecting samples…";
    document.getElementById("prompt-bottom").textContent = rolling?.distributions?.prompt ? `${number(rolling.processed)} tokens processed / ${observed}s observed` : "Collecting samples…";
    document.getElementById("context-bottom").textContent = slot.context_missing ? "Context count not reported by worker" : `${number(slot.n_prompt_tokens)} tokens in latest primary slot`;
    document.getElementById("cache-bottom").textContent = slot.cache_missing ? "Cache count not reported by worker" : `${number(slot.n_prompt_tokens_cache)} cached tokens in latest primary slot`;
  }
  els.modelSource.textContent = snapshot.source || "--";
  els.bucketSummary.textContent = snapshot.bucket_seconds
    ? `${number(history.bucket_count)} buckets, ${number((snapshot.trend || {}).point_count)} compact points`
    : "--";
  els.slotState.textContent = slot.speculative ? "speculative" : "standard";
  els.mtpState.textContent =
    slot.mtp_active || summaryLast(historySlots, "mtp_active") === 1
      ? slot.draft_type || "draft-mtp"
      : "off";
  els.decodeMean.textContent = `${number(
    summaryMean(historyRates, "predicted_tokens_per_second"),
    1,
  )} tok/s`;
  els.decodedTotal.textContent = number(slot.n_decoded);
  els.remainingTotal.textContent = number(slot.n_remain);
  els.observedAt.textContent = snapshot.observed_at
    ? new Date(snapshot.observed_at).toLocaleTimeString()
    : "--";
}

function updateBoxPlot(name, distribution) {
  const plot = document.getElementById(`${name}-plot`);
  plot.style.visibility = distribution?.count ? "visible" : "hidden";
  document.getElementById(`${name}-min`).textContent = distribution ? `min ${number(distribution.min, 1)}` : "--";
  document.getElementById(`${name}-max`).textContent = distribution ? `max ${number(distribution.max, 1)}` : "--";
  document.getElementById(`${name}-summary`).textContent = distribution ? `Median ${number(distribution.median, 1)} · ${distribution.count} samples` : "Collecting samples…";
  if (!distribution) return;
  const {min, q1, median, q3, max} = distribution;
  document.getElementById(`${name}-plot-title`).textContent = `Min ${number(min,1)} · Q1 ${number(q1,1)} · Median ${number(median,1)} · Q3 ${number(q3,1)} · Max ${number(max,1)}`;
  const x = value => max > min ? 12 + 176 * (value - min) / (max - min) : 100;
  plot.setAttribute("aria-label", `Minimum ${number(min,1)}, lower quartile ${number(q1,1)}, median ${number(median,1)}, upper quartile ${number(q3,1)}, maximum ${number(max,1)}. Each plot uses its own scale.`);
  const attrs = (id, values) => { for (const [key, value] of Object.entries(values)) document.getElementById(`${name}-${id}`).setAttribute(key, value); };
  attrs("whisker", {x1:x(min), x2:x(max)});
  attrs("low", {x1:x(min), x2:x(min)}); attrs("high", {x1:x(max), x2:x(max)});
  attrs("box", {x:x(q1), width:Math.max(1,x(q3)-x(q1))});
  attrs("median", {x1:x(median), x2:x(median)});
}

function pushPoint(snapshot) {
  const trendPoints = ((snapshot.trend || {}).points || []).map(trendPoint);
  if (trendPoints.length > 0) {
    points.splice(0, points.length, ...trendPoints);
    return;
  }
  const buckets = snapshot.buckets || [];
  if (buckets.length > 0) {
    points.splice(0, points.length, ...buckets.map(bucketPoint));
    return;
  }
  const slot = primarySlot(snapshot);
  points.push({
    at: new Date(snapshot.observed_at || Date.now()),
    decode: rate(
      snapshot,
      "predicted_tokens_per_second",
      "llamacpp:predicted_tokens_seconds",
    ),
    prompt: rate(
      snapshot,
      "prompt_tokens_per_second",
      "llamacpp:prompt_tokens_seconds",
    ),
    context: slot.n_prompt_tokens || 0,
  });
  while (points.length > historyLimit) {
    points.shift();
  }
}

function trendPoint(point) {
  const metrics = point.metrics || {};
  return {
    at: new Date(point.at || Date.now()),
    decode: metrics.predicted_tokens_per_second || 0,
    prompt: metrics.prompt_tokens_per_second || 0,
    context: metrics.active_context_tokens || 0,
  };
}

function bucketPoint(bucket) {
  return {
    at: new Date(bucket.end || bucket.start || Date.now()),
    decode: summaryMean(bucket.rates, "predicted_tokens_per_second") || 0,
    prompt: summaryMean(bucket.rates, "prompt_tokens_per_second") || 0,
    context: summaryMean(bucket.slots, "active_context_tokens") || 0,
  };
}

function resizeCanvas() {
  const ratio = window.devicePixelRatio || 1;
  const rect = els.timeline.getBoundingClientRect();
  els.timeline.width = Math.max(1, Math.floor(rect.width * ratio));
  els.timeline.height = Math.max(1, Math.floor(rect.height * ratio));
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
}

function drawTimeline() {
  resizeCanvas();
  const rect = els.timeline.getBoundingClientRect();
  const width = rect.width;
  const height = rect.height;
  const pad = { left: 54, right: 18, top: 22, bottom: 34 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const maxRate = Math.max(
    10,
    ...points.map((point) => Math.max(point.decode, point.prompt)),
  );

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#202821";
  ctx.fillRect(0, 0, width, height);

  ctx.strokeStyle = "#344039";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#9ba79e";
  ctx.font = "12px system-ui, sans-serif";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";

  for (let i = 0; i <= 4; i += 1) {
    const y = pad.top + (plotH * i) / 4;
    const value = maxRate - (maxRate * i) / 4;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(width - pad.right, y);
    ctx.stroke();
    ctx.fillText(number(value, 0), pad.left - 10, y);
  }

  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
  if (points.length === 0) {
    ctx.fillStyle = "#9ba79e";
    ctx.font = "14px system-ui, sans-serif";
    ctx.fillText("waiting for samples", pad.left, pad.top + 28);
    return;
  }

  drawSeries("prompt", "#e4b449", pad, plotW, plotH, maxRate);
  drawSeries("decode", "#58c7d8", pad, plotW, plotH, maxRate);
  drawXAxis(pad, plotW, height);
}

function drawSeries(field, color, pad, plotW, plotH, maxRate) {
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.beginPath();
  points.forEach((point, index) => {
    const x =
      pad.left + (points.length === 1 ? plotW : (plotW * index) / (points.length - 1));
    const y = pad.top + plotH - (Math.max(0, point[field]) / maxRate) * plotH;
    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });
  ctx.stroke();

  ctx.fillStyle = color;
  for (const [index, point] of points.entries()) {
    const x =
      pad.left + (points.length === 1 ? plotW : (plotW * index) / (points.length - 1));
    const y = pad.top + plotH - (Math.max(0, point[field]) / maxRate) * plotH;
    ctx.beginPath();
    ctx.arc(x, y, 2.5, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawXAxis(pad, plotW, height) {
  ctx.fillStyle = "#9ba79e";
  ctx.font = "12px system-ui, sans-serif";
  ctx.textBaseline = "top";
  const ticks = [0, Math.floor((points.length - 1) / 2), points.length - 1];
  for (const index of ticks) {
    if (!points[index]) {
      continue;
    }
    const x =
      pad.left + (points.length === 1 ? plotW : (plotW * index) / (points.length - 1));
    ctx.textAlign = index === 0 ? "left" : index === points.length - 1 ? "right" : "center";
    ctx.fillText(points[index].at.toLocaleTimeString(), x, height - 24);
  }
}

let selectedModel = null;
try { selectedModel = localStorage.getItem("dashboard-model"); } catch {}
let fleetModels = [];
const lastGood = new Map();
const modelButtons = new Map();
let lastCardsAt = 0;
let renderedModel = null;
let discoveryError = "";

function selectModel(id) {
  selectedModel = id;
  try { localStorage.setItem("dashboard-model", id); } catch {}
  renderSelected();
  for (const [key, button] of modelButtons) button.setAttribute("aria-pressed", String(key === id));
}
function renderSelected() {
  const model = fleetModels.find(m => m.id === selectedModel);
  const previous = lastGood.get(selectedModel);
  const snapshot = model?.snapshot || previous?.snapshot;
  const rolling = model?.rolling || previous?.rolling;
  const age = snapshot ? Math.max(0, Math.floor((Date.now() - Date.parse(snapshot.observed_at)) / 1000)) : 0;
  const stale = !!discoveryError || !model || !!model.stale || !model.snapshot || age > 15;
  document.getElementById("selected-model").textContent = selectedModel || "Choose a model";
  document.getElementById("model-detail").hidden = !snapshot;
  els.status.classList.toggle("is-live", !!snapshot && !stale);
  els.statusText.textContent = snapshot ? (stale ? "Showing last known data" : "Live") : "Waiting for metrics";
  const notice = document.getElementById("model-notice");
  notice.classList.toggle("is-stale", stale);
  notice.textContent = snapshot
    ? stale ? `Last sample ${age}s ago · ${discoveryError || (model?.state === "unloaded" ? "model unloaded" : "poll delayed; retrying automatically")}. History retained.`
      : snapshot.sample_count < 2 ? "Collecting samples for rolling rates…" : `Last sample ${age}s ago · ${Math.round(snapshot.window_seconds)}s rolling window`
    : model?.state === "unloaded" ? "This model is not loaded. Selecting it does not load it."
      : model?.metrics_error ? "This worker has no usable metrics yet. Retrying automatically."
      : "Waiting for the first sample…";
  notice.title = model?.metrics_error || discoveryError;
  if (snapshot) {
    const changed = renderedModel !== selectedModel;
    const updateSummary = changed || Date.now() - lastCardsAt >= 5000;
    if (changed) points.length = 0;
    updateCards(snapshot, rolling, updateSummary);
    if (updateSummary) lastCardsAt = Date.now();
    if (changed || !points.length || points.at(-1)?.at.getTime() !== Date.parse(snapshot.observed_at)) pushPoint(snapshot);
    drawTimeline();
    renderedModel = selectedModel;
  }
}
function renderModels() {
  const list = document.getElementById("model-list");
  const displayed = new Set(fleetModels.map(m => m.id));
  for (const [id, button] of modelButtons) {
    if (!displayed.has(id) && id !== selectedModel) { button.remove(); modelButtons.delete(id); }
  }
  for (const model of fleetModels) {
    let button = modelButtons.get(model.id);
    if (!button) {
      button = document.createElement("button"); button.type = "button";
      const name = document.createElement("span"); name.className = "model-name";
      const state = document.createElement("span"); state.className = "model-state";
      button.append(name, state);
      button.onclick = () => selectModel(model.id);
      modelButtons.set(model.id, button); list.append(button);
    }
    button.firstChild.textContent = model.id;
    button.lastChild.textContent = model.state === "unloaded" ? "Unloaded" : model.stale ? "Loaded · sample delayed" : model.snapshot ? "Loaded · metrics available" : "Loaded · metrics unavailable";
    button.setAttribute("aria-pressed", String(model.id === selectedModel));
    button.title = model.metrics_error || model.id;
  }
}
async function refresh() {
  try {
    const response = await fetch("/api/models", { cache: "no-store" });
    if (response.status === 404) {
      const legacy = await fetch("/api/stats", {cache:"no-store"});
      if (!legacy.ok) throw new Error("Stats unavailable");
      const snapshot = await legacy.json();
      document.getElementById("model-detail").hidden = false;
      document.getElementById("fleet-status").textContent = "Single-server mode";
      updateCards(snapshot); pushPoint(snapshot); drawTimeline();
      els.statusText.textContent = "single server";
      return;
    }
    if (!response.ok) throw new Error("Model discovery unavailable");
    const data = await response.json();
    fleetModels = data.models || [];
    discoveryError = "";
    for (const model of fleetModels) if (model.snapshot) lastGood.set(model.id, model);
    // A temporarily missing model must never change the user's selection.
    if (!selectedModel) selectedModel = fleetModels.find(m => m.snapshot)?.id || fleetModels[0]?.id;
    document.getElementById("fleet-status").textContent = `${fleetModels.filter(m => m.state !== "unloaded").length} loaded / ${fleetModels.length} configured`;
    renderModels(); renderSelected();
  } catch (error) {
    discoveryError = error.message;
    document.getElementById("fleet-status").textContent = "Discovery delayed · retrying";
    renderSelected();
  } finally { window.setTimeout(refresh, 1000); }
}

window.addEventListener("resize", drawTimeline);
void refresh();
