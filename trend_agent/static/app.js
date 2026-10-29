const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const span = (s) => (s.start === s.end ? s.start : `${s.start}~${s.end}`);
const BASE = { rolling: "직전 28일 중앙값", same_weekday: "직전 4주 같은 요일 중앙값" };
const STATE = {
  not_requested: "가장 최근 급등만 자동으로 설명합니다.",
  budget_exhausted: "오늘의 AI 설명 한도를 다 썼습니다. 탐지 결과는 그대로 볼 수 있고, 내일 다시 설명할 수 있습니다.",
  rate_limited: "오늘 이 접속에서 쓸 수 있는 AI 설명 횟수를 다 썼습니다.",
  error: "AI 설명 중 오류가 났습니다. 잠시 후 다시 시도해 주세요.",
};

function chart(series, spikes) {
  const W = Math.round(Math.min(860, Math.max(320, $("#result").clientWidth - 34))), H = 220, L = 32, R = 8, T = 10, B = 24;
  const n = series.length, x = (i) => L + (i * (W - L - R)) / Math.max(n - 1, 1);
  const y = (v) => T + (1 - v / 100) * (H - T - B);
  const idx = Object.fromEntries(series.map(([d], i) => [d, i]));
  let g = "";
  for (const v of [0, 50, 100]) g += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text class="axis" x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`;
  for (const s of spikes) {
    const a = idx[s.start], b = idx[s.end], p = idx[s.peak_date];
    if (a === undefined) continue;
    g += `<rect class="band" x="${x(a) - 3}" y="${T}" width="${x(b) - x(a) + 6}" height="${H - T - B}"/>`;
    g += `<circle class="peak" cx="${x(p)}" cy="${y(series[p][1])}" r="3.5"/>`;
  }
  const pts = series.map(([, v], i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  for (const i of [0, Math.floor((n - 1) / 2), n - 1]) {
    g += `<text class="axis" x="${x(i)}" y="${H - 6}" text-anchor="${i === 0 ? "start" : i === n - 1 ? "end" : "middle"}">${series[i][0]}</text>`;
  }
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" data-n="${n}" data-l="${L}" data-r="${R}" data-w="${W}" role="img" aria-label="최근 90일 상대지수 추이">${g}<polyline class="line" points="${pts}"/><line class="cursor" x1="0" x2="0" y1="${T}" y2="${H - B}" visibility="hidden"/></svg>`;
}

function hover(svg, series) {
  const tip = $("#tip"), cur = svg.querySelector(".cursor");
  const { n, l, r, w } = Object.fromEntries(Object.entries(svg.dataset).map(([k, v]) => [k, +v]));
  svg.addEventListener("pointermove", (e) => {
    const box = svg.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * w;
    const i = Math.min(n - 1, Math.max(0, Math.round(((px - l) / (w - l - r)) * (n - 1))));
    const cx = l + (i * (w - l - r)) / (n - 1);
    cur.setAttribute("x1", cx); cur.setAttribute("x2", cx); cur.setAttribute("visibility", "visible");
    tip.textContent = `${series[i][0]} · 상대지수 ${series[i][1]}`;
    tip.style.left = `${e.clientX + 12}px`; tip.style.top = `${e.clientY - 28}px`; tip.hidden = false;
  });
  svg.addEventListener("pointerleave", () => { tip.hidden = true; cur.setAttribute("visibility", "hidden"); });
}

function explanation(s) {
  const e = s.explanation;
  if (!e) return `<p class="status limit">${esc(STATE[s.explain_state] || "")}</p>`;
  let h = "";
  if (e.status === "found") {
    const refs = e.citations.map((c) => `<sup><a href="#c-${s.start}-${c.n}">[${c.n}]</a></sup>`).join("");
    h += `<p class="cause">${esc(e.cause)} ${refs}</p><ol class="cites">`;
    h += e.citations.map((c) => `<li id="c-${s.start}-${c.n}">${esc(c.date)} <a href="${esc(c.link)}" target="_blank" rel="noopener">${esc(c.title)}</a></li>`).join("");
    h += "</ol>";
  } else {
    h += `<p class="status unknown">원인 불명 — 급등 기간(${esc(s.news_period.join("~"))}) 기사로 원인을 확인하지 못했습니다. 추측으로 채우지 않습니다.</p>`;
  }
  if (e.searches?.length) {
    h += `<div class="searches">AI가 쓴 검색어: ${e.searches.map((q) => `<code>${esc(q.query)}</code> ${q.in_period}건`).join(" · ")}</div>`;
  }
  return h;
}

function spikeBlock(s) {
  return `<div class="spike"><h4>${esc(span(s))} 급등</h4>
    <div class="meta">정점 ${esc(s.peak_date)} 상대지수 ${s.peak_value} (${BASE[s.baseline_kind]} ${s.baseline})</div>
    ${explanation(s)}</div>`;
}

function renderResult(r) {
  const box = $("#result");
  box.hidden = false;
  if (r.blocked) { box.innerHTML = `<div class="panel">성인 검색어로 판별되어 분석하지 않습니다.</div>`; return; }
  let h = `<div class="panel"><h3>${esc(r.keyword)} <span class="meta">${r.start} ~ ${r.end}</span></h3>${chart(r.series, r.spikes)}`;
  if (r.insufficient) {
    h += `<p class="status unknown">${r.reason === "low_volume" ? "검색량이 적어 지수가 계단처럼 움직입니다" : "관측된 날이 너무 적습니다"} — 급등을 판단하지 않습니다.</p>`;
  } else if (!r.spikes.length) {
    h += `<p class="status">최근 90일 동안 탐지된 급등이 없습니다.</p>`;
  }
  h += [...r.spikes].reverse().map(spikeBlock).join("") + "</div>";
  box.innerHTML = h;
  const svg = box.querySelector("svg");
  if (svg) hover(svg, r.series);
}

async function run(q) {
  const btn = $("#form button");
  btn.disabled = true;
  $("#result").hidden = false;
  $("#result").innerHTML = `<div class="panel muted">“${esc(q)}” 분석 중… 급등이 있으면 AI가 뉴스를 찾느라 10~30초 걸릴 수 있습니다.</div>`;
  try {
    const res = await fetch(`/api/analyze?q=${encodeURIComponent(q)}`);
    if (!res.ok) throw new Error((await res.json()).detail || res.status);
    renderResult(await res.json());
    history.replaceState(null, "", `?q=${encodeURIComponent(q)}`);
  } catch (err) {
    $("#result").innerHTML = `<div class="panel status unknown">분석 실패: ${esc(err.message)}</div>`;
  } finally {
    btn.disabled = false;
  }
}

async function loadDaily() {
  const d = await (await fetch("/api/daily")).json();
  const list = $("#daily-list");
  if (d.generated_at) $("#daily-meta").textContent = `감시 키워드 ${d.watchlist_size}개 중 최근 ${d.recent_days}일 급등 · ${d.generated_at} 기준`;
  if (!d.items?.length) { list.innerHTML = `<p class="muted">${d.generated_at ? "최근 급등한 감시 키워드가 없습니다." : "아직 일일 집계가 없습니다."}</p>`; return; }
  list.innerHTML = d.items.map((it) => `<div class="card">
      <h3><button data-q="${esc(it.keyword)}">${esc(it.keyword)}</button></h3>
      <div class="meta">${esc(span(it.spike))} · 정점 ${esc(it.spike.peak_date)} 상대지수 ${it.spike.peak_value} (${BASE[it.spike.baseline_kind]} ${it.spike.baseline})</div>
      ${explanation({ ...it.spike, explanation: it.explanation, explain_state: it.explain_state })}</div>`).join("");
  list.querySelectorAll("button[data-q]").forEach((b) => b.addEventListener("click", () => { $("#q").value = b.dataset.q; run(b.dataset.q); window.scrollTo({ top: 0, behavior: "smooth" }); }));
}

$("#form").addEventListener("submit", (e) => { e.preventDefault(); const q = $("#q").value.trim(); if (q) run(q); });
loadDaily().catch(() => { $("#daily-list").innerHTML = `<p class="muted">일일 집계를 불러오지 못했습니다.</p>`; });
const initial = new URLSearchParams(location.search).get("q");
if (initial) { $("#q").value = initial; run(initial); }
