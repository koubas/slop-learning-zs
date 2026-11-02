# AGENTS.md

Small vibecoded learning apps for Czech primary school (ZŠ).

## Layout

- `<grade>/<app>/`: numeric top-level dir = school grade, one app per subdir with its own `README.md`.
- `web/`: shared browser runtime + build (`build.py`, `dev.py`, `runtime/`).
- `dist/` (build output) and `web/vendor/` (local library copies) are gitignored.
- When adding an app, add a row to the table in the root `README.md`.

## Writing mini apps

- Python 3, **stdlib only**, single-file terminal (curses) apps.
- Czech UI text, identifiers and comments (match existing code). Commit messages in English.
- State goes to a JSON file in the **current working directory** (e.g. `zak_<name>.json` via `--zak`).
  Save it on exit (`finally:`). On the web the cwd is a virtual FS that gets synced to localStorage.
- Stick to the curses subset that `web/runtime/curses_shim.py` implements: `wrapper`, `initscr/endwin`,
  `curs_set`, `init_pair/color_pair`, `A_BOLD/A_DIM/A_UNDERLINE/A_REVERSE`, `getch` with `timeout`,
  `addstr`, `erase/clear`, `getmaxyx`, `move`, `refresh`, `flushinp`, basic `KEY_*`.
  If you need more, extend the shim.
- `getch()` returns UTF-8 **bytes** for non-ASCII input (as real curses does). `KEY_*` codes are ≥ 256.
- Handle Enter as both 10 and 13, and Backspace as 8, 127 and `KEY_BACKSPACE`.
- To publish an app on the web, add `web.json` (`nazev`, `popis`, `spoustec`, optional `dotaz` = argument
  prompt shown before start; see the root README). All `*.py` in the app dir get shipped.
- Test the logic headlessly by importing the module. Test the TUI through a pty (`pty.fork`)
  by sending keys and reading output.

## Web build & serving

- `python3 web/build.py` builds the prod version: Pyodide + xterm.js from the jsdelivr CDN.
- `python3 web/dev.py [--port N]` downloads the libraries into `web/vendor/` (only missing files),
  then runs `build.py --lokalni` and serves `dist/` on localhost. Works fully offline after the first run.
- Library versions and the list of files needed locally live in `KNIHOVNY` in `web/build.py`.
  Placeholders `__PYODIDE__`, `__XTERM__`, `__XTERM_FIT__` in runtime files get replaced at build time.
- Pyodide versions now track CPython (314.x = Python 3.14). Its core files are `pyodide.mjs`,
  `pyodide.asm.mjs`, `pyodide.asm.wasm`, `python_stdlib.zip` and `pyodide-lock.json`.
- How it runs: Python runs in a module Web Worker. Keys reach it through a SharedArrayBuffer ring buffer
  and are read with blocking `Atomics.wait`, so apps need no async rewrite. `time.sleep` is patched to use
  `Atomics.wait`.
- SharedArrayBuffer needs cross-origin isolation. `dist/sw.js` (a service worker) adds the COOP/COEP
  headers, so a plain `python3 -m http.server -d dist` works, and so would GitHub Pages.
  - The first visit reloads the page once.
  - The page only works on `localhost` or https. A LAN IP over http or `file://` won't work.
  - `sw.js` must stay at the `dist/` root so its scope covers all apps.
- App data is saved to localStorage (`slop-learning-zs:<grade>/<app>:<file>`) only after the app exits.
- The main thread terminates the worker on `pagehide`, because a worker stuck in `Atomics.wait` would
  otherwise hang.

## Browser testing gotchas

- Use `puppeteer-core` with `/opt/google/chrome/chrome` headless, installed in a scratch dir and not in the repo.
  Read the screen from `.xterm-rows` innerText.
- **Don't** use `page.setRequestInterception`: it breaks the service worker / isolation and makes tests flaky.
  To test offline, launch Chrome with `--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost`.
- CDP `page.reload()` leaves the page non-isolated (looks like an automation quirk).
  Use `page.evaluate(() => location.reload())` instead.
- Port 9222 may already belong to the user's own Chromium. Don't touch it; use your own headless instance.
- Stop background servers by PID (`ss -ltnp`), not with `pkill -f <pattern>`: that also kills your own shell,
  whose command line contains the same pattern.
