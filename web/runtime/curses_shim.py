"""Minimální náhrada modulu curses pro běh v prohlížeči (Pyodide + xterm.js).

Implementuje jen to, co používají aplikace v repu. Kreslí do bufferu
a při refresh() pošle do terminálu jen změněné řádky jako ANSI sekvence.
Klávesy čte blokujícím js.readKey() z worker.js. Stejně jako skutečný
curses vrací getch() pro ne-ASCII znaky jednotlivé bajty UTF-8, takže
kódy speciálních kláves (KEY_*, >= 256) nekolidují se znaky.
"""

import js

COLOR_BLACK, COLOR_RED, COLOR_GREEN, COLOR_YELLOW = 0, 1, 2, 3
COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN, COLOR_WHITE = 4, 5, 6, 7

A_NORMAL = 0
A_COLOR = 0xFF00
A_BOLD = 1 << 16
A_DIM = 1 << 17
A_UNDERLINE = 1 << 18
A_REVERSE = 1 << 19

KEY_DOWN, KEY_UP, KEY_LEFT, KEY_RIGHT = 258, 259, 260, 261
KEY_HOME, KEY_BACKSPACE = 262, 263
KEY_DC = 330
KEY_ENTER = 343
KEY_END = 360
KEY_RESIZE = 410

COLORS = 8
COLOR_PAIRS = 256


class error(Exception):
    pass


_pary = {0: (-1, -1)}
_kurzor = 1


def color_pair(n):
    return n << 8


def pair_number(attr):
    return (attr & A_COLOR) >> 8


def init_pair(n, fg, bg):
    _pary[n] = (fg, bg)


def start_color():
    pass


def use_default_colors():
    pass


def has_colors():
    return True


def curs_set(viditelnost):
    global _kurzor
    puvodni, _kurzor = _kurzor, viditelnost
    return puvodni


def flushinp():
    js.flushInput()


def napms(ms):
    js.sleepMs(ms)


def noecho():
    pass


def echo():
    pass


def cbreak():
    pass


def nocbreak():
    pass


def _sgr(attr):
    kody = ["0"]
    if attr & A_BOLD:
        kody.append("1")
    if attr & A_DIM:
        kody.append("2")
    if attr & A_UNDERLINE:
        kody.append("4")
    if attr & A_REVERSE:
        kody.append("7")
    fg, bg = _pary.get(pair_number(attr), (-1, -1))
    if fg >= 0:
        kody.append(str(30 + fg))
    if bg >= 0:
        kody.append(str(40 + bg))
    return "\x1b[" + ";".join(kody) + "m"


class _Okno:
    def __init__(self):
        self._timeout = -1
        self._vyska = self._sirka = 0
        self._zobrazeno = []
        self._y = self._x = 0
        self._prizpusob()

    def _prizpusob(self):
        vyska, sirka = js.termRows(), js.termCols()
        if (vyska, sirka) != (self._vyska, self._sirka):
            self._vyska, self._sirka = vyska, sirka
            self._zobrazeno = [None] * vyska
            js.writeOut("\x1b[0m\x1b[2J")
        self._buffer = [[(" ", 0)] * self._sirka for _ in range(self._vyska)]

    def getmaxyx(self):
        return self._vyska, self._sirka

    def erase(self):
        self._prizpusob()

    def clear(self):
        self._zobrazeno = [None] * self._vyska
        self._prizpusob()

    def move(self, y, x):
        if not (0 <= y < self._vyska and 0 <= x < self._sirka):
            raise error("move() mimo okno")
        self._y, self._x = y, x

    def addstr(self, *args):
        if len(args) >= 3 and isinstance(args[0], int):
            y, x, text, *zbytek = args
        else:
            (y, x), (text, *zbytek) = (self._y, self._x), args
        attr = zbytek[0] if zbytek else 0
        if not (0 <= y < self._vyska and 0 <= x < self._sirka):
            raise error("addstr() mimo okno")
        radek = self._buffer[y]
        for i, znak in enumerate(str(text)):
            if x + i >= self._sirka:
                break
            radek[x + i] = (znak, attr)
        self._y, self._x = y, min(x + len(text), self._sirka - 1)

    def refresh(self):
        vystup = []
        for y, radek in enumerate(self._buffer):
            casti, posledni = [], None
            for znak, attr in radek:
                if attr != posledni:
                    casti.append(_sgr(attr))
                    posledni = attr
                casti.append(znak)
            text = "".join(casti)
            if text != self._zobrazeno[y]:
                vystup.append(f"\x1b[{y + 1};1H{text}")
                self._zobrazeno[y] = text
        if _kurzor:
            vystup.append(f"\x1b[0m\x1b[{self._y + 1};{self._x + 1}H\x1b[?25h")
        else:
            vystup.append("\x1b[0m\x1b[?25l")
        js.writeOut("".join(vystup))

    def timeout(self, ms):
        self._timeout = ms

    def nodelay(self, zapnuto):
        self._timeout = 0 if zapnuto else -1

    def keypad(self, zapnuto):
        pass

    def getch(self):
        return js.readKey(self._timeout)


def initscr():
    js.writeOut("\x1b[?1049h")
    return _Okno()


def endwin():
    js.writeOut("\x1b[0m\x1b[?25h\x1b[?1049l")


def wrapper(funkce, *args, **kwargs):
    okno = initscr()
    try:
        return funkce(okno, *args, **kwargs)
    finally:
        endwin()
