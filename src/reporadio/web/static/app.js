/* RepoRadio Studio v2 — live agent mode, 3D particle orb. No external libraries. */
"use strict";

const $ = (id) => document.getElementById(id);
const STAGE_POS = { ingest: "12%", index: "38%", context: "63%", ready: "88%" };
const STAGE_ORDER = ["ingest", "index", "context", "ready"];

let ws = null;
let currentMode = "standard";
let currentLang = null;
let tunedAt = 0;
let gotFirstAudio = false;

const ticks = document.querySelector(".ticks");
for (let i = 0; i < 40; i++) ticks.appendChild(document.createElement("i"));

/* =============================================== audio out (gapless) */
const player = {
  ctx: null, analyser: null, nextTime: 0, sources: new Set(),
  ensure() {
    if (!this.ctx) {
      this.ctx = new (window.AudioContext || window.webkitAudioContext)();
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 1024;
      this.analyser.connect(this.ctx.destination);
    }
    if (this.ctx.state === "suspended") this.ctx.resume();
  },
  play(b64, samplerate) {
    this.ensure();
    const raw = atob(b64), n = raw.length / 2;
    const f32 = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const v = (raw.charCodeAt(2 * i) | (raw.charCodeAt(2 * i + 1) << 8)) << 16 >> 16;
      f32[i] = v / 32768;
    }
    const buf = this.ctx.createBuffer(1, n, samplerate);
    buf.copyToChannel(f32, 0);
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.connect(this.analyser);
    const t = Math.max(this.ctx.currentTime + 0.06, this.nextTime);
    src.start(t);
    this.nextTime = t + buf.duration;
    this.sources.add(src);
    src.onended = () => { this.sources.delete(src); updateOnAir(); };
    updateOnAir();
  },
  flush() {
    this.sources.forEach((s) => { try { s.stop(); } catch (e) {} });
    this.sources.clear();
    this.nextTime = 0;
    updateOnAir();
  },
  level() {
    if (!this.analyser || !this.playing()) return 0;
    const d = new Uint8Array(this.analyser.frequencyBinCount);
    this.analyser.getByteTimeDomainData(d);
    let sum = 0;
    for (let i = 0; i < d.length; i++) { const v = (d[i] - 128) / 128; sum += v * v; }
    return Math.sqrt(sum / d.length);
  },
  playing() { return this.ctx && this.ctx.state === "running" && this.sources.size > 0; },
};

function updateOnAir() {
  const on = player.playing();
  const badge = $("onair");
  badge.textContent = on ? "● ON AIR" : "● OFF AIR";
  badge.classList.toggle("live", !!on);
}

/* =============================================== 3D particle orb */
const orb = $("orb"), octx = orb.getContext("2d");
const P = [];
(function initParticles() {
  const N = 720;
  for (let i = 0; i < N; i++) {                       // fibonacci sphere
    const y = 1 - (i / (N - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const th = i * 2.39996323;
    P.push({ x: Math.cos(th) * r, y, z: Math.sin(th) * r, tw: Math.random() * 6.28 });
  }
  for (let i = 0; i < 140; i++) {                     // equator ring — the "dial"
    const a = (i / 140) * 6.283;
    P.push({ x: Math.cos(a) * 1.35, y: 0, z: Math.sin(a) * 1.35, ring: true, tw: Math.random() * 6.28 });
  }
})();
let rotY = 0, rotX = -0.35, amp = 0, micAmp = 0;

function accentRGB() {
  const c = getComputedStyle(document.body).getPropertyValue("--accent").trim();
  const m = c.match(/#(..)(..)(..)/);
  return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : [255, 176, 58];
}

(function drawOrb(ts) {
  requestAnimationFrame(drawOrb);
  const w = orb.width, h = orb.height, cx = w / 2, cy = h / 2 - 10;
  octx.clearRect(0, 0, w, h);

  const target = Math.min(1, player.level() * 4 + micAmp * 3);
  amp += (target - amp) * 0.12;
  rotY += 0.0035 + amp * 0.012;

  const listening = document.body.dataset.state === "listening" || micAmp > 0.06;
  const [ar, ag, ab] = listening ? [168, 224, 95] : accentRGB();
  const base = 118 + amp * 46 + Math.sin(ts / 1600) * 4;

  const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
  const cosX = Math.cos(rotX), sinX = Math.sin(rotX);
  for (const p of P) {
    let x = p.x * cosY - p.z * sinY;
    let z = p.x * sinY + p.z * cosY;
    let y = p.y * cosX - z * sinX;
    z = p.y * sinX + z * cosX;
    const jitter = p.ring ? 1 : 1 + amp * 0.35 * Math.sin(ts / 90 + p.tw);
    const persp = 340 / (340 - z * base);
    const sx = cx + x * base * jitter * persp;
    const sy = cy + y * base * jitter * persp;
    const lum = (z + 1.4) / 2.4;
    const size = (p.ring ? 1.1 : 1.5) * persp * (0.6 + amp * 0.8);
    octx.fillStyle = `rgba(${ar},${ag},${ab},${(p.ring ? 0.5 : 0.75) * lum})`;
    octx.beginPath();
    octx.arc(sx, sy, Math.max(0.4, size), 0, 6.283);
    octx.fill();
  }
  // core glow
  const g = octx.createRadialGradient(cx, cy, 0, cx, cy, base * 0.9);
  g.addColorStop(0, `rgba(${ar},${ag},${ab},${0.10 + amp * 0.22})`);
  g.addColorStop(1, "rgba(0,0,0,0)");
  octx.fillStyle = g;
  octx.fillRect(0, 0, w, h);
})(0);

/* =============================================== stations + langs */
async function loadStations() {
  const modes = await (await fetch("/api/modes")).json();
  const row = $("stations");
  row.innerHTML = "";
  modes.forEach((m) => {
    const btn = document.createElement("button");
    btn.className = "station" + (m.key === currentMode ? " active" : "");
    btn.innerHTML = `<span class="fq">${m.freq}</span><span class="meta"><span class="nm">${m.key}</span><span class="vb">${m.title.split("—")[1] || m.title}</span></span>`;
    btn.onclick = () => {
      currentMode = m.key;
      currentLang = null;
      document.body.dataset.mode = m.key;
      document.querySelectorAll(".station").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      markLang(m.language);
      status(`station: <b>${m.freq} ${m.key}</b> — tune in when ready`);
    };
    row.appendChild(btn);
  });
}
function markLang(lang) {
  document.querySelectorAll(".lang").forEach((b) =>
    b.classList.toggle("active", b.dataset.lang === lang));
}
document.querySelectorAll(".lang").forEach((b) => {
  b.onclick = () => { currentLang = b.dataset.lang; markLang(currentLang); };
});

/* =============================================== stage + status */
function setStage(stage) {
  if (!(stage in STAGE_POS)) return;
  $("needle").style.left = STAGE_POS[stage];
  const idx = STAGE_ORDER.indexOf(stage);
  document.querySelectorAll(".stages span").forEach((s) => {
    const i = STAGE_ORDER.indexOf(s.dataset.stage);
    s.classList.toggle("done", i < idx);
    s.classList.toggle("active", i === idx);
  });
}
function status(html) { $("statusline").innerHTML = html; }
function setState(st, label) {
  document.body.dataset.state = st;
  $("navstate").textContent = label || st;
}

/* =============================================== transcript */
function addLine(who, text, files) {
  const div = document.createElement("div");
  div.className = `tline ${who}`;
  const label = { host: "🎙 host", you: "📞 you", err: "⚠ studio" }[who] || who;
  div.innerHTML = `<span class="who">${label}</span><p></p>`;
  div.querySelector("p").textContent = text;
  if (files && files.length) {
    const f = document.createElement("div");
    f.className = "files";
    f.textContent = "from: " + files.join(", ");
    div.appendChild(f);
  }
  const t = $("transcript");
  t.appendChild(div);
  t.scrollTop = t.scrollHeight;
}

/* =============================================== repo explorer */
function buildTree(paths) {
  const root = {};
  paths.forEach((f) => {
    const parts = f.path.split("/");
    let node = root;
    parts.forEach((part, i) => {
      if (i === parts.length - 1) (node.__files = node.__files || []).push({ ...f, name: part });
      else node = node[part] = node[part] || {};
    });
  });
  const fmt = (n) => n > 1024 ? `${(n / 1024).toFixed(1)}k` : `${n}`;
  function render(node, depth) {
    const frag = document.createDocumentFragment();
    Object.keys(node).filter((k) => k !== "__files").sort().forEach((dir) => {
      const det = document.createElement("details");
      if (depth < 1) det.open = true;
      const sum = document.createElement("summary");
      sum.textContent = dir + "/";
      det.appendChild(sum);
      det.appendChild(render(node[dir], depth + 1));
      frag.appendChild(det);
    });
    (node.__files || []).sort((a, b) => a.name.localeCompare(b.name)).forEach((f) => {
      const div = document.createElement("div");
      div.className = "file" + (f.kept ? " kept" : "");
      div.innerHTML = `<span>${f.name}</span><span class="sz">${fmt(f.size)}</span>`;
      div.title = f.path + (f.kept ? " — in the host's digest" : " — trimmed for size");
      frag.appendChild(div);
    });
    return frag;
  }
  const box = $("tree");
  box.innerHTML = "";
  box.appendChild(render(root, 0));
}

/* =============================================== tune in + events */
$("tunebtn").onclick = tuneIn;
$("url").addEventListener("keydown", (e) => { if (e.key === "Enter") tuneIn(); });

function tuneIn() {
  const url = $("url").value.trim();
  if (!url) { status("paste a GitHub repo URL first"); return; }
  player.ensure();
  player.flush();
  $("tunebtn").disabled = true;
  document.body.classList.add("tuned");
  $("studio").hidden = false;
  $("transcript").innerHTML = "";
  gotFirstAudio = false;
  tunedAt = performance.now();

  if (ws) { try { ws.close(); } catch (e) {} }
  ws = new WebSocket(`ws://${location.host}/ws/session`);
  ws.onopen = () => ws.send(JSON.stringify(
    { type: "tune_in", url, mode: currentMode, lang: currentLang }));
  ws.onmessage = (e) => handle(JSON.parse(e.data));
  ws.onclose = () => { $("tunebtn").disabled = false; mic.stop(); setState("idle", "off air"); };
  ws.onerror = () => status("⚠ lost the studio connection");
  setStage("ingest");
  status("📡 tuning in…");
  setState("tuning", "on air");
}

function handle(ev) {
  switch (ev.type) {
    case "status":
      if (ev.stage === "flush") { player.flush(); break; }
      if (ev.stage === "listening") { setState("listening", "📞 listening…"); $("nowline").textContent = "…go ahead, caller"; break; }
      if (ev.stage === "thinking") { setState("thinking", "checking the code…"); $("nowline").textContent = "checking the code…"; break; }
      if (ev.stage === "on_air") { setState("onair", "on air"); break; }
      if (ev.stage === "off_air") { status(`📻 ${ev.detail} — stay tuned`); setState("idle", "show over"); break; }
      setStage(ev.stage);
      status(ev.detail);
      break;
    case "ready": {
      setStage("ready");
      const chip = $("repochip");
      chip.hidden = false;
      chip.textContent = `${ev.repo} @ ${ev.commit}`;
      status(`<b>${ev.repo}</b> — ${ev.files} files in the show, ~${ev.tokens.toLocaleString()} tokens · ${ev.freq} ${ev.mode}`);
      $("f_voice").innerHTML = `voice <b>${ev.voice}</b>`;
      $("exp_meta").textContent = `${ev.repo}`;
      if (ev.paths && ev.paths.length) buildTree(ev.paths);
      setState("onair", "on air");
      break;
    }
    case "segment_start":
      $("segtitle").textContent = `${ev.n}. ${ev.title}`;
      break;
    case "transcript_line":
      addLine(ev.who, ev.text, ev.files);
      if (ev.who === "host") $("nowline").textContent = ev.text;
      break;
    case "audio_chunk":
      if (!gotFirstAudio) {
        gotFirstAudio = true;
        $("f_latency").innerHTML = `latency <b>${((performance.now() - tunedAt) / 1000).toFixed(1)}s</b>`;
      }
      player.play(ev.data, ev.samplerate);
      break;
    case "error":
      addLine("err", ev.message);
      status(`⚠ ${ev.message}`);
      break;
  }
}

/* =============================================== controls */
const send = (obj) => ws && ws.readyState === 1 && ws.send(JSON.stringify(obj));
let pausedLocal = false;
$("pausebtn").onclick = () => {
  pausedLocal = !pausedLocal;
  $("pausebtn").textContent = pausedLocal ? "▶" : "⏸";
  if (pausedLocal) { send({ type: "pause" }); player.ctx && player.ctx.suspend(); }
  else { send({ type: "resume" }); player.ctx && player.ctx.resume(); }
};
$("skipbtn").onclick = () => { send({ type: "skip" }); player.flush(); };

/* =============================================== live agent mic */
const mic = {
  live: false, stream: null, ctx: null, node: null, src: null,
  async start() {
    if (this.live || !ws || ws.readyState !== 1) return;
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (e) {
      addLine("err", "mic permission denied — allow the microphone to go live");
      return;
    }
    this.live = true;
    send({ type: "mic", live: true });
    $("livebtn").classList.add("live");
    $("livebtn").querySelector("span").textContent = "LIVE — just talk";
    $("f_mic").innerHTML = "mic <b>LIVE</b>";
    $("f_mic").classList.add("live");
    $("livehint").textContent = "you're live — speak anytime, the host stops and listens";
    this.ctx = new AudioContext();
    this.src = this.ctx.createMediaStreamSource(this.stream);
    this.node = this.ctx.createScriptProcessor(4096, 1, 1);
    const inRate = this.ctx.sampleRate;
    this.node.onaudioprocess = (e) => {
      if (!this.live) return;
      const input = e.inputBuffer.getChannelData(0);
      let sum = 0;
      for (let i = 0; i < input.length; i += 16) sum += input[i] * input[i];
      micAmp = Math.min(1, Math.sqrt(sum / (input.length / 16)) * 6);
      const outLen = Math.floor((input.length * 16000) / inRate);
      const i16 = new Int16Array(outLen);
      for (let i = 0; i < outLen; i++) {
        const v = input[Math.floor((i * inRate) / 16000)];
        i16[i] = Math.max(-1, Math.min(1, v)) * 32767;
      }
      let bin = "";
      const bytes = new Uint8Array(i16.buffer);
      for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
      send({ type: "caller_audio", data: btoa(bin), end: false });
    };
    this.src.connect(this.node);
    this.node.connect(this.ctx.destination);
  },
  stop() {
    if (!this.live) return;
    this.live = false;
    micAmp = 0;
    send({ type: "mic", live: false });
    $("livebtn").classList.remove("live");
    $("livebtn").querySelector("span").innerHTML = "GO&nbsp;LIVE";
    $("f_mic").textContent = "mic off";
    $("f_mic").classList.remove("live");
    $("livehint").textContent = "go live, then just talk — the host stops and listens";
    if (this.node) this.node.disconnect();
    if (this.src) this.src.disconnect();
    if (this.ctx) this.ctx.close();
    if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
  },
};
$("livebtn").onclick = () => (mic.live ? mic.stop() : mic.start());

/* =============================================== boot */
loadStations();
markLang("en");
