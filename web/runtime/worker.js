// Web Worker: načte Pyodide, připraví virtuální FS a spustí aplikaci.
//
// Klávesnice: hlavní vlákno zapisuje kódy kláves do kruhového bufferu
// v SharedArrayBuffer, worker je čte blokujícím Atomics.wait(), takže
// Python může volat getch() synchronně jako v terminálu.

import { loadPyodide } from "__PYODIDE__pyodide.mjs";

const HEAD = 0, TAIL = 1, ROWS = 2, COLS = 3, N = 256;
const APP_DIR = "/home/pyodide/app";
const SHIM_DIR = "/home/pyodide/shim";
let ctrl, keys;

const sleeper = new Int32Array(new SharedArrayBuffer(4));

// --- funkce volané z Pythonu (modul js) ---

self.readKey = (timeoutMs) => {
  const tail = Atomics.load(ctrl, TAIL);
  if (Atomics.load(ctrl, HEAD) === tail) {
    if (timeoutMs === 0) return -1;
    Atomics.wait(ctrl, HEAD, tail, timeoutMs < 0 ? Infinity : timeoutMs);
    if (Atomics.load(ctrl, HEAD) === tail) return -1;
  }
  const k = keys[tail % N];
  Atomics.store(ctrl, TAIL, tail + 1);
  return k;
};
self.flushInput = () => Atomics.store(ctrl, TAIL, Atomics.load(ctrl, HEAD));
self.sleepMs = (ms) => Atomics.wait(sleeper, 0, 0, ms);
self.termRows = () => Atomics.load(ctrl, ROWS);
self.termCols = () => Atomics.load(ctrl, COLS);
self.writeOut = (text) => postMessage({ type: "out", text });
self.saveFiles = (json) => postMessage({ type: "save", files: JSON.parse(json) });

async function text(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return res.text();
}

self.onmessage = async ({ data: { sab, app, files, base, runtime } }) => {
  ctrl = new Int32Array(sab, 0, 4);
  keys = new Int32Array(sab, 16, N);
  try {
    writeOut("\x1b[2mNačítám Python…\x1b[0m\r\n");
    const [py, shim, bootstrap, ...zdroje] = await Promise.all([
      loadPyodide(),
      text(new URL("curses_shim.py", runtime)),
      text(new URL("bootstrap.py", runtime)),
      ...app.soubory.map((f) => text(new URL(f, base))),
    ]);
    const dec = new TextDecoder();
    const out = { write: (b) => (writeOut(dec.decode(b, { stream: true })), b.length) };
    py.setStdout(out);
    py.setStderr(out);

    py.FS.mkdirTree(APP_DIR);
    py.FS.mkdirTree(`${SHIM_DIR}/curses`);
    py.FS.writeFile(`${SHIM_DIR}/curses/__init__.py`, shim);
    app.soubory.forEach((f, i) => py.FS.writeFile(`${APP_DIR}/${f}`, zdroje[i]));
    for (const [f, obsah] of Object.entries(files)) py.FS.writeFile(`${APP_DIR}/${f}`, obsah);
    py.FS.chdir(APP_DIR);

    self.appConfig = JSON.stringify(app);
    writeOut("\x1b[2J\x1b[H");
    py.runPython(`
import sys
sys.path[:0] = ["${SHIM_DIR}", "${APP_DIR}"]
sys.modules.pop("curses", None)
`);
    py.runPython(bootstrap);
    py.runPython("spust()");
  } catch (e) {
    writeOut(`\r\n\x1b[31mChyba: ${String(e.message || e).replace(/\n/g, "\r\n")}\x1b[0m\r\n`);
  }
};
