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

function updateCards(snapshot) {
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

  els.decodeRate.textContent = number(decode, 1);
  els.promptRate.textContent = number(prompt, 1);
  els.contextUsed.textContent = number(slot.n_prompt_tokens);
  els.cacheUsed.textContent = number(slot.n_prompt_tokens_cache);
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

async function refresh() {
  try {
    const response = await fetch("/api/stats", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(response.statusText);
    }
    const snapshot = await response.json();
    els.status.classList.add("is-live");
    els.statusText.textContent = "live";
    updateCards(snapshot);
    pushPoint(snapshot);
    drawTimeline();
  } catch (error) {
    els.status.classList.remove("is-live");
    els.statusText.textContent = "offline";
  }
}

window.addEventListener("resize", drawTimeline);
void refresh();
window.setInterval(refresh, 1000);
