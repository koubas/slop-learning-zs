// Hlavní vlákno: terminál xterm.js, předávání kláves do workeru
// a ukládání datových souborů aplikace do localStorage.

const HEAD = 0, TAIL = 1, ROWS = 2, COLS = 3, N = 256;
const KEY_DOWN = 258, KEY_UP = 259, KEY_LEFT = 260, KEY_RIGHT = 261;
const KEY_HOME = 262, KEY_DC = 330, KEY_END = 360, KEY_RESIZE = 410;
const SEKVENCE = {
  "\x1b[A": KEY_UP, "\x1b[B": KEY_DOWN, "\x1b[C": KEY_RIGHT, "\x1b[D": KEY_LEFT,
  "\x1bOA": KEY_UP, "\x1bOB": KEY_DOWN, "\x1bOC": KEY_RIGHT, "\x1bOD": KEY_LEFT,
  "\x1b[H": KEY_HOME, "\x1b[F": KEY_END, "\x1b[3~": KEY_DC,
};

const app = JSON.parse(document.getElementById("app").textContent);
const root = new URL(app.root, location.href);
const prefix = `slop-learning-zs:${app.id}:`;

// SharedArrayBuffer vyžaduje cross-origin izolaci (hlavičky COOP/COEP).
// Obyčejný http.server je neposílá, dodá je service worker sw.js:
// po první registraci se stránka jednou znovu načte už pod jeho kontrolou.
async function izolace() {
  if (self.crossOriginIsolated) return true;
  if (!("serviceWorker" in navigator)) return false;
  await navigator.serviceWorker.register(new URL("sw.js", root), { scope: root.pathname });
  await navigator.serviceWorker.ready;
  const klic = "slop-learning-zs:reload";
  if (sessionStorage.getItem(klic)) return false;
  sessionStorage.setItem(klic, "1");
  location.reload();
  return new Promise(() => {});
}

function nactiData() {
  const data = {};
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k.startsWith(prefix)) data[k.slice(prefix.length)] = localStorage.getItem(k);
    }
  } catch (e) {
    console.warn("localStorage nedostupné", e);
  }
  return data;
}

function ulozData(soubory) {
  for (const [f, obsah] of Object.entries(soubory)) {
    try {
      localStorage.setItem(prefix + f, obsah);
    } catch (e) {
      console.warn("nelze uložit", f, e);
    }
  }
}

async function start() {
  const term = new Terminal({
    convertEol: true,
    fontFamily: "ui-monospace, Menlo, Consolas, monospace",
    fontSize: 20,
    theme: { background: "#111111" },
  });
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  term.open(document.getElementById("term"));
  fit.fit();
  addEventListener("resize", () => fit.fit());
  term.focus();

  if (!(await izolace())) {
    sessionStorage.removeItem("slop-learning-zs:reload");
    term.write(
      "\x1b[31mProhlížeč nepovolil SharedArrayBuffer (cross-origin izolace).\r\n" +
        "Otevři stránku přes http://localhost nebo https, ne přes IP adresu nebo file://.\x1b[0m\r\n"
    );
    return;
  }
  sessionStorage.removeItem("slop-learning-zs:reload");

  const sab = new SharedArrayBuffer(16 + 4 * N);
  const ctrl = new Int32Array(sab, 0, 4);
  const keys = new Int32Array(sab, 16, N);
  ctrl[ROWS] = term.rows;
  ctrl[COLS] = term.cols;

  const push = (k) => {
    const head = Atomics.load(ctrl, HEAD);
    if (head - Atomics.load(ctrl, TAIL) >= N) return;
    keys[head % N] = k;
    Atomics.store(ctrl, HEAD, head + 1);
    Atomics.notify(ctrl, HEAD);
  };
  const enc = new TextEncoder();
  term.onData((d) => {
    if (d in SEKVENCE) return push(SEKVENCE[d]);
    for (const ch of d) {
      if (ch === "\r") push(10);
      else enc.encode(ch).forEach(push);
    }
  });
  term.onResize(({ rows, cols }) => {
    Atomics.store(ctrl, ROWS, rows);
    Atomics.store(ctrl, COLS, cols);
    push(KEY_RESIZE);
  });

  const worker = new Worker(new URL("runtime/worker.js", root), { type: "module" });
  worker.onmessage = ({ data }) => {
    if (data.type === "out") term.write(data.text);
    else if (data.type === "save") ulozData(data.files);
  };
  worker.onerror = (e) => term.write(`\r\n\x1b[31mChyba workeru: ${e.message}\x1b[0m\r\n`);
  // worker visí v Atomics.wait(); bez ukončení by blokoval reload stránky
  addEventListener("pagehide", () => worker.terminate());
  worker.postMessage({
    sab,
    app,
    files: nactiData(),
    base: new URL(".", location.href).href,
    runtime: new URL("runtime/", root).href,
  });
}

start();
