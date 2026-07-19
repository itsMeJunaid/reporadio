/* RepoRadio Studio — no external libraries. */
"use strict";

const $ = (id) => document.getElementById(id);
const STAGE_POS = { ingest: "12%", index: "38%", context: "63%", ready: "88%" };
const STAGE_ORDER = ["ingest", "index", "context", "ready"];

let ws = null;
let currentMode = "standard";
let currentLang = null; // null = mode default
let tunedAt = 0;
let gotFirstAudio = false;

/* ---------------------------------------------------------- tuner ticks */
const ticks = document.querySelector(".ticks");
for (let i = 0; i < 40; i++) ticks.appendChild(document.createElement("i"));

/* ---------------------------------------------------------- audio out */
const player = {
  ctx: null, analyser: null, nextTime: 0, sources: new Set(),
  ensure() {
    if (!this.ctx) {
      this.ctx = new (window.AudioContext || window.webkitAudioContext)();
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 512;
      this.analyser.connect(this.ctx.destination);
    }
    if (this.ctx.state === "suspended") this.ctx.resume();
  },
  play(b64, samplerate) {
    this.ensure();
    const raw = atob(b64);
    const n = raw.length / 2;
    const i16 = new Int16Array(n);
    for (let i = 0; i < n; i++)
      i16[i] = (raw.charCodeAt(2 * i) | (raw.charCodeAt(2 * i + 1) << 8)) << 16 >> 16;
    const f32 = new Float32Array(n);
    for (let i = 0; i < n; i++) f32[i] = i16[i] / 32768;
    const buf = this.ctx.createBuffer(1, n, samplerate);
    buf.copyToChannel(f32, 0);
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.connect(this.analyser);
    const t = Math.max(this.ctx.currentTime + 0.05, this.nextTime);
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
  suspend() { if (this.ctx) this.ctx.suspend(); updateOnAir(); },
  resume() { if (this.ctx) this.ctx.resume(); updateOnAir(); },
  playing() {
    return this.ctx && this.ctx.state === "running" && this.sources.size > 0;
  },
};

function updateOnAir() {
  const on = player.playing();
  const badge = $("onair");
  badge.textContent = on ? "● ON AIR" : "● OFF AIR";
  badge.classList.toggle("live", !!on);
}

/* ---------------------------------------------------------- waveform */
const wave = $("wave"), wctx = wave.getContext("2d");
(function drawWave() {
  requestAnimationFrame(drawWave);
  const w = wave.width, h = wave.height;
  wctx.clearRect(0, 0, w, h);
  const accent = getComputedStyle(document.body).getPropertyValue("--accent").trim();
  wctx.strokeStyle = accent; wctx.lineWidth = 2;
  if (player.analyser && player.playing()) {
    const data = new Uint8Array(player.analyser.frequencyBinCount);
    player.analyser.getByteTimeDomainData(data);
    wctx.beginPath();
    for (let i = 0; i < data.length; i++) {
      const x = (i / data.length) * w, y = (data[i] / 255) * h;
      i ? wctx.lineTo(x, y) : wctx.moveTo(x, y);
    }
    wctx.stroke();
  } else {
    wctx.globalAlpha = 0.35;
    wctx.beginPath(); wctx.moveTo(0, h / 2); wctx.lineTo(w, h / 2); wctx.stroke();
    wctx.globalAlpha = 1;
  }
})();

/* ---------------------------------------------------------- stations */
async function loadStations() {
  const modes = await (await fetch("/api/modes")).json();
  const row = $("stations");
  row.innerHTML = "";
  modes.forEach((m) => {
    const btn = document.createElement("button");
    btn.className = "station" + (m.key === currentMode ? " active" : "");
    btn.innerHTML = `<span class="fq">${m.freq}</span><span class="nm">${m.key}</span><span class="vb">${m.title}</span>`;
    btn.onclick = () => {
      currentMode = m.key;
      currentLang = null;
      document.body.dataset.mode = m.key;
      document.querySelectorAll(".station").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      markLang(m.language);
      status(`station set: <b>${m.freq} ${m.key}</b> — tune in to start the show`);
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

/* ---------------------------------------------------------- stage needle */
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

/* ---------------------------------------------------------- transcript */
function addLine(who, text, files) {
  const div = document.createElement("div");
  div.className = `tline ${who}`;
  const label = { host: "🎙 host", you: "📞 you", err: "⚠ studio", seg: "" }[who] || who;
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
  return div;
}

/* ---------------------------------------------------------- tune in */
$("tunebtn").onclick = tuneIn;
$("url").addEventListener("keydown", (e) => { if (e.key === "Enter") tuneIn(); });

function tuneIn() {
  const url = $("url").value.trim();
  if (!url) { status("paste a GitHub repo URL first"); return; }
  player.ensure(); // user gesture unlocks audio
  player.flush();
  $("tunebtn").disabled = true;
  $("console").hidden = false;
  $("transcript").innerHTML = "";
  gotFirstAudio = false;
  tunedAt = performance.now();

  if (ws) { try { ws.close(); } catch (e) {} }
  ws = new WebSocket(`ws://${location.host}/ws/session`);
  ws.onopen = () => ws.send(JSON.stringify(
    { type: "tune_in", url, mode: currentMode, lang: currentLang }));
  ws.onmessage = (e) => handle(JSON.parse(e.data));
  ws.onclose = () => { $("tunebtn").disabled = false; $("navstate").textContent = "off air"; };
  ws.onerror = () => status("⚠ lost the studio connection");
  setStage("ingest");
  status("📡 tuning in…");
  $("navstate").textContent = "on air";
}

function handle(ev) {
  switch (ev.type) {
    case "status":
      if (ev.stage === "flush") { player.flush(); break; }
      if (ev.stage === "off_air") {
        status(`📻 ${ev.detail} — stay tuned`);
        break;
      }
      setStage(ev.stage);
      status(ev.detail);
      break;
    case "ready": {
      setStage("ready");
      const chip = $("repochip");
      chip.hidden = false;
      chip.textContent = `${ev.repo} @ ${ev.commit}`;
      status(`<b>${ev.repo}</b> — ${ev.files} files, ~${ev.tokens.toLocaleString()} tokens · ${ev.freq} ${ev.mode}`);
      $("f_voice").innerHTML = `voice <b>${ev.voice}</b>`;
      loadVersions(ev.repo);
      break;
    }
    case "segment_start":
      $("segtitle").textContent = `${ev.n}. ${ev.title}`;
      addLine("seg", "");
      break;
    case "transcript_line":
      addLine(ev.who, ev.text, ev.files);
      break;
    case "audio_chunk":
      if (!gotFirstAudio) {
        gotFirstAudio = true;
        const s = ((performance.now() - tunedAt) / 1000).toFixed(1);
        $("f_latency").innerHTML = `latency <b>${s}s</b> to first audio`;
      }
      player.play(ev.data, ev.samplerate);
      break;
    case "error":
      addLine("err", ev.message);
      status(`⚠ ${ev.message}`);
      break;
  }
}

async function loadVersions(repo) {
  try {
    const data = await (await fetch(`/api/versions/${repo}`)).json();
    const box = $("versions");
    if (!data.versions.length) { box.textContent = "no versions yet"; return; }
    box.innerHTML = "";
    data.versions.slice().reverse().forEach((v, i) => {
      const row = document.createElement("div");
      row.className = "vrow";
      row.innerHTML = `<b>${v.commit}</b><span class="vd">${v.analyzed_at}</span>` +
        `<span class="vd">${v.files} files · ${v.languages}</span>` +
        (i === 0 ? `<span class="vd">← latest</span>` : "");
      box.appendChild(row);
    });
    if (data.episodes) {
      const ep = document.createElement("div");
      ep.className = "vd";
      ep.textContent = `${data.episodes} changelog episode(s) in the archive — reporadio changelog <url>`;
      box.appendChild(ep);
    }
  } catch (e) { /* deck is optional */ }
}

/* ---------------------------------------------------------- controls */
const send = (type) => ws && ws.readyState === 1 && ws.send(JSON.stringify({ type }));
$("pausebtn").onclick = () => { send("pause"); player.suspend(); };
$("resumebtn").onclick = () => { send("resume"); player.resume(); };
$("skipbtn").onclick = () => { send("skip"); player.flush(); };

/* ---------------------------------------------------------- push-to-talk */
const mic = {
  stream: null, ctx: null, node: null, src: null, live: false,
  async start() {
    if (this.live || !ws || ws.readyState !== 1) return;
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      addLine("err", "mic permission denied — allow the microphone to call the station");
      return;
    }
    this.live = true;
    $("micbtn").classList.add("live");
    $("micbtn").textContent = "🔴 LIVE — release to send";
    $("f_mic").innerHTML = "mic <b>LIVE</b>";
    player.flush();           // local barge-in: silence the host instantly
    this.ctx = new AudioContext();
    this.src = this.ctx.createMediaStreamSource(this.stream);
    this.node = this.ctx.createScriptProcessor(4096, 1, 1);
    const inRate = this.ctx.sampleRate;
    this.node.onaudioprocess = (e) => {
      if (!this.live) return;
      const input = e.inputBuffer.getChannelData(0);
      const outLen = Math.floor((input.length * 16000) / inRate);
      const i16 = new Int16Array(outLen);
      for (let i = 0; i < outLen; i++) {
        const v = input[Math.floor((i * inRate) / 16000)];
        i16[i] = Math.max(-1, Math.min(1, v)) * 32767;
      }
      let bin = "";
      const bytes = new Uint8Array(i16.buffer);
      for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
      ws.send(JSON.stringify({ type: "caller_audio", data: btoa(bin), end: false }));
    };
    this.src.connect(this.node);
    this.node.connect(this.ctx.destination);
  },
  stop() {
    if (!this.live) return;
    this.live = false;
    $("micbtn").classList.remove("live");
    $("micbtn").innerHTML = "🎙 HOLD&nbsp;TO&nbsp;CALL";
    $("f_mic").textContent = "mic idle";
    if (this.node) this.node.disconnect();
    if (this.src) this.src.disconnect();
    if (this.ctx) this.ctx.close();
    if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
    if (ws && ws.readyState === 1)
      ws.send(JSON.stringify({ type: "caller_audio", data: "", end: true }));
  },
};
const micbtn = $("micbtn");
micbtn.addEventListener("pointerdown", (e) => { e.preventDefault(); mic.start(); });
micbtn.addEventListener("pointerup", () => mic.stop());
micbtn.addEventListener("pointerleave", () => mic.stop());

/* ---------------------------------------------------------- boot */
loadStations();
markLang("en");
