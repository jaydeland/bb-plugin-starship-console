import re, urllib.parse, xml.etree.ElementTree as ET

import pathlib
BASE = str(pathlib.Path(__file__).resolve().parents[1] / "themes")
FILES = {
    "tng": f"{BASE}/lcars-tng/theme.css",
    "science": f"{BASE}/lcars-science/theme.css",
    "ten-forward": f"{BASE}/lcars-ten-forward/theme.css",
}
MARK = "/* ---------- LCARS chrome"

def scan(css):
    """Return (problems, rules) where rules = [(selector, body)] at top level."""
    probs, rules = [], []
    i, n, depth = 0, len(css), 0
    sel_start = 0
    body_start = None
    while i < n:
        c = css[i]
        if css.startswith("/*", i):
            j = css.find("*/", i + 2)
            if j < 0:
                probs.append("unterminated comment"); break
            i = j + 2; continue
        if c in "\"'":
            j = i + 1
            while j < n and css[j] != c:
                if css[j] == "\\": j += 1
                j += 1
            if j >= n:
                probs.append(f"unterminated string at offset {i}"); break
            i = j + 1; continue
        if c == "{":
            if depth == 0:
                body_start = i + 1
                sel = css[sel_start:i].strip()
                if not sel: probs.append(f"empty selector near offset {i}")
            depth += 1
        elif c == "}":
            depth -= 1
            if depth < 0:
                probs.append(f"unmatched }} at offset {i}"); depth = 0
            elif depth == 0:
                body = css[body_start:i]
                rules.append((css[sel_start:body_start-1].strip(), body))
                sel_start = i + 1
        elif depth == 0 and not c.isspace():
            pass
        i += 1
    if depth != 0: probs.append(f"unbalanced braces, depth {depth} at EOF")
    # stray text between rules (outside comments)
    stripped = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    tail = css[sel_start:].strip()
    if tail: probs.append(f"trailing text not in a rule: {tail[:60]!r}")
    return probs, rules

def decl_check(body):
    """Split body on ';' outside strings and check each declaration."""
    probs, decls, cur, i = [], [], "", 0
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    q = None
    for ch in body:
        if q:
            cur += ch
            if ch == q: q = None
            continue
        if ch in "\"'": q = ch; cur += ch; continue
        if ch == ";": decls.append(cur.strip()); cur = ""; continue
        cur += ch
    if cur.strip(): probs.append(f"declaration missing ';': {cur.strip()[:70]!r}")
    for d in decls:
        if d and not re.match(r"^(--[\w-]+|[a-zA-Z-]+)\s*:", d):
            probs.append(f"malformed declaration: {d[:70]!r}")
    return probs

def hex2rgb(h):
    h = h.lstrip("#")
    if len(h) == 3: h = "".join(x*2 for x in h)
    return tuple(int(h[k:k+2], 16) for k in (0, 2, 4))

def rgb2hex(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(x))) for x in c)

def parse_color(v):
    v = v.strip()
    if v.startswith("#"): return hex2rgb(v)
    m = re.match(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)", v)
    if m: return tuple(float(x) for x in m.groups())
    raise ValueError(v)

def lum(rgb):
    def ch(x):
        x = x / 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)

def ratio(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)

def blend(fg, bg, alpha):
    return tuple(alpha * f + (1 - alpha) * b for f, b in zip(fg, bg))

def tokens(body):
    out = {}
    for name, val in re.findall(r"--([a-z0-9-]+)\s*:\s*([^;]+);", body):
        if name in out: out.setdefault("__dup__", []).append(name)
        out[name] = val.strip()
    return out

def fix_fg(fg, bg, target, mode="raise"):
    """Shift fg lightness in HSL (hue kept) until ratio >= target (raise) or <= target (lower)."""
    import colorsys
    r, g, b = [x / 255 for x in fg]
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    best = None
    for direction in ([-1, 1] if mode == "raise" else [-1, 1]):
        for step in range(1, 201):
            ll = min(1, max(0, l + direction * step * 0.0025))
            c = colorsys.hls_to_rgb(h, ll, s)
            c255 = tuple(x * 255 for x in c)
            rt = ratio(c255, bg)
            ok = rt >= target if mode == "raise" else rt <= target
            if ok:
                if best is None or step < best[0]:
                    best = (step, rgb2hex(c255), round(rt, 2))
                break
    return best

REPORT = {}
issues = []

for name, path in FILES.items():
    css = open(path, encoding="utf-8").read()
    probs, rules = scan(css)
    for p in probs: issues.append((name, "syntax", p))
    # per-declaration check on every rule body
    for sel, body in rules:
        for p in decl_check(body): issues.append((name, "syntax", f"{sel[:40]}: {p}"))
    print(f"{name}: rules={len(rules)} scan_problems={len(probs)}")

    # Split tokens vs chrome
    chrome_idx = css.find(MARK)
    head, chrome = css[:chrome_idx], css[chrome_idx:]
    light_body = re.search(r":root, \.light \{(.*?)\n\}", head, re.S).group(1)
    dark_body = re.search(r"\.dark \{(.*?)\n\}", head, re.S).group(1)
    L, D = tokens(light_body), tokens(dark_body)
    if "__dup__" in L or "__dup__" in D: issues.append((name, "syntax", "duplicate token in a block"))
    for k in ("__dup__",):
        L.pop(k, None); D.pop(k, None)
    for mode, T in (("light", L), ("dark", D)):
        for k, v in T.items():
            if "var(" in v: issues.append((name, "tokens", f"{mode} --{k} uses var(): {v}"))
    only_l = set(L) - set(D); only_d = set(D) - set(L)
    if only_l or only_d: issues.append((name, "tokens", f"key mismatch light-only={sorted(only_l)} dark-only={sorted(only_d)}"))

    # Chrome rules: data URIs. Every url() must be a quoted data URI; inside an SVG only url(%23id) fragment refs are allowed.
    uris = re.findall(r'url\("([^"]*)"\)', chrome)
    if re.search(r"url\(", re.sub(r'url\("[^"]*"\)', "", chrome)): issues.append((name, "svg", "url() outside a quoted data URI"))
    for raw in uris:
        if raw.startswith("data:image/svg") and re.search(r"url\((?!%23)", raw): issues.append((name, "svg", "SVG data URI references a non-fragment url()"))
    for idx, raw in enumerate(uris):
        if not raw.startswith("data:image/svg"): continue
        if "#" in raw: issues.append((name, "svg", f"uri[{idx}] has raw #"))
        if re.search(r"%(?![0-9A-Fa-f]{2})", raw): issues.append((name, "svg", f"uri[{idx}] bad % escape"))
        payload = raw.split(",", 1)[1]
        svg = urllib.parse.unquote(payload)
        try:
            ET.fromstring(svg.encode("utf-8"))
            res = "parse ok"
        except ET.ParseError as e:
            res = f"PARSE FAIL {e}"; issues.append((name, "svg", f"uri[{idx}] {e}"))
        print(f"  uri[{idx}] {raw[:40]}... {res} ({len(svg)} chars decoded)")
    # Blueprint background: one ::before host, masked by the galaxy PNG in the last block of the file.
    if "drag-region" in css: issues.append((name, "fleet", "comm badge / drag-region rule still present"))
    m = re.search(r"\[data-thread-window\]::before \{(.*?)\n\}", chrome, re.S)
    if not m: issues.append((name, "blueprint", "::before rule missing"))
    else:
        for need in ("position: absolute", "z-index: -1", "pointer-events: none", "opacity: var(--lcars-schematic-opacity)"):
            if need not in m.group(1): issues.append((name, "blueprint", f"::before missing {need!r}"))
    if "viewBox='0 0 1400 950'" in chrome: issues.append((name, "blueprint", "dead SVG tile still present"))
    bp = chrome[chrome.find("/* ---------- LCARS blueprint background"):]
    if "mask: url(\"data:image/png;base64," not in bp: issues.append((name, "blueprint", "galaxy mask missing"))
    if "\n/* ---------- " in bp[10:]: issues.append((name, "blueprint", "blueprint block is not the last block (apply_blueprint.py would move rules)"))
    if ".thread-scrollbar" not in css: issues.append((name, "fleet", ".thread-scrollbar rule missing"))
    REPORT[name] = dict(L=L, D=D, chrome=chrome, uris=uris)

# Selector checks: dead rules gone, real-DOM rules present
TOGGLE = 'section[aria-label] > div.relative > button[aria-expanded]:first-child'
for n in FILES:
    ch = REPORT[n]["chrome"]
    for bad in ('[data-project-row]', 'hover:bg-sidebar-accent', 'aside[data-surface-tone="sidebar"]:not('):
        if bad in ch: issues.append((n, "selectors", f"stale selector still present: {bad}"))
    for need in ('[data-sidebar="sidebar"]::before', '[data-sidebar="sidebar"]::after', 'div:has(> a[data-sidebar-thread-id]):has(> a[aria-current="page"])',
                 '[data-project-stripe]', TOGGLE, 'span.h-px', '--lcars-header-ink'):
        if need not in ch: issues.append((n, "selectors", f"missing selector {need}"))
    for need in ('[data-split-pane-id] > header::before', '[data-split-pane-id] > header::after', '[data-split-pane-id] > header .bb-thread-title',
                 '[role="status"].fixed.inset-x-0.bottom-0::before', '[role="status"].fixed.inset-x-0.bottom-0::after',
                 '[data-thread-window]::after', 'mask-composite: subtract', 'border-top: 4px solid var(--lcars-frame-2)', 'padding-left: 46px', 'padding-right: 48px'):
        if need not in ch: issues.append((n, "bars", f"missing {need}"))
    bars = ch[ch.find("/* ---------- LCARS top bar and bottom bar"):].split("/* ---------- LCARS blueprint background")[0]
    frame = bars[bars.find("/* ---------- LCARS window frame"):]
    if bars.split("/* ---------- LCARS window frame")[0].count("pointer-events: none") != 1: issues.append((n, "bars", "expected 1 pointer-events:none in the status bar rules"))
    for sel in ("header::after {", "[data-thread-window]::after {", "[data-thread-window] > div:only-child::after {"):
        blk = frame[frame.find(sel):].split("\n}")[0]
        if "pointer-events: none" not in blk: issues.append((n, "bars", f"{sel} must not take pointer events"))
    if "text-transform" in bars.split(".bb-thread-title")[1].split("}")[0]: issues.append((n, "bars", "title is uppercased"))
    # segment geometry: 28+3+14+3+48 = 96px wide; the mask cuts 99px so a 3px gap sits before the first segment
    if "width: 96px" not in frame or "var(--lcars-pill-4) 48px 100%" not in frame or "99px 10px" not in frame: issues.append((n, "bars", "segment geometry changed"))
    for banned in ("[data-thread-window]::before",):
        if banned in bars: issues.append((n, "bars", f"bars block touches {banned}"))
    if re.search(r"(outline|box-shadow)\s*:", re.sub(r'\[data-testid="thread-secondary-panel-top-chrome"\] \{.*?\n\}', "", re.sub(r"\[data-thread-window\]::before \{.*?\n\}", "", ch, flags=re.S), flags=re.S)):
        issues.append((n, "focus", "chrome sets outline/box-shadow"))
    # Section-header rules must target the collapse toggle only (not the sort button)
    for m in re.finditer(r'button\[aria-expanded\][^{,]*', ch):
        # Allowed: the plain toggle, or the open-group variant that adds :has() guards to the section.
        if not (re.search(r"(section\[aria-label\]|:has\(> :is\(section, ul\) > \*\)) > div\.relative > $", ch[:m.start()]) and m.group(0).startswith('button[aria-expanded]:first-child')):
            issues.append((n, "selectors", f"unscoped header selector: {m.group(0)[:60]!r}"))
    if ch.count(TOGGLE) != 4: issues.append((n, "selectors", f"expected 4 toggle-scoped header rules, got {ch.count(TOGGLE)}"))
    # Sidebar padding, end block, card padding, header padding
    rb = lambda sel: (re.search(re.escape(sel) + r" \{(.*?)\n\}", ch, re.S) or [None, ""])[1]
    side = rb('[data-sidebar="sidebar"]')
    for need in ("padding-top: 14px", "padding-right: 10px", "position: relative", "box-sizing: border-box"):
        if need not in side: issues.append((n, "sidebar", f"sidebar root missing {need}"))
    endb = rb('[data-sidebar="sidebar"]::after')
    for need in ("bottom: 56px", "height: 104px", "width: 10px", "font-size: 8px", "letter-spacing: 0.12em", "line-height: 10px", "pointer-events: none"):
        if need not in endb: issues.append((n, "sidebar", f"end block missing {need}"))
    # 104px tall, 7 glyphs of 8px with .12em tracking is ~ 7*(5+1)=42px, so the text fits
    if 'content: "47-1701"' in endb and 7 * (8 * 0.62 + 8 * 0.12) > 104: issues.append((n, "sidebar", "end text cannot fit"))
    for sel in ('[data-sidebar="sidebar"] div:has(> a[data-sidebar-thread-id]):has(> a[aria-current="page"])',
                '[data-sidebar="sidebar"] div:has(> a[data-sidebar-thread-id]):not(:has(> a[aria-current="page"])):hover'):
        if "padding-right: 12px" not in rb(sel): issues.append((n, "rows", f"missing padding-right: 12px on {sel[-30:]}"))
    if "padding-left: 24px" not in rb('[data-split-pane-id] > header'): issues.append((n, "bars", "header padding-left: 24px missing"))
    # Right panel elbow
    A = 'aside[data-surface-tone="sidebar"]'
    ab, ap, aa = rb(A), rb(A + "::before"), rb(A + "::after")
    for need in ("padding-left: 16px", "padding-top: 10px", "box-sizing: border-box", "border-left-color: transparent"):
        if need not in ab: issues.append((n, "aside", f"aside missing {need}"))
    if "position" in ab: issues.append((n, "aside", "aside sets position"))
    for need in ("position: absolute", "top: 0", "left: 0", "right: 0", "height: 100%", "border-left: 10px solid var(--lcars-frame)",
                 "border-top: 10px solid var(--lcars-frame)", "border-top-left-radius: 28px", "pointer-events: none", "z-index: 1", "box-sizing: border-box"):
        if need not in ap: issues.append((n, "aside", f"aside::before missing {need}"))
    for need in ('content: ""', "position: absolute", "left: 0", "bottom: 56px", "width: 10px", "height: 104px", "background: var(--lcars-frame-2)", "pointer-events: none", "z-index: 1"):
        if need not in aa: issues.append((n, "aside", f"aside::after missing {need}"))
    if "box-shadow: inset 0 -6px 0 var(--lcars-frame-2)" not in rb('[data-testid="thread-secondary-panel-top-chrome"]'): issues.append((n, "aside", "top chrome row bar missing"))
    scopes = re.findall(r":is\(\[data-sidebar=\"sidebar\"\][^)]*\)", ch)
    if not scopes or any('aside[data-surface-tone="sidebar"]' not in sc for sc in scopes): issues.append((n, "aside", "pill/badge scope lacks right panel"))
    if not re.search(r'\[data-sidebar="sidebar"\] \{\s*position: relative;', ch): issues.append((n, "selectors", "sidebar root position:relative missing"))

# Chrome identical check
def norm_chrome(c, color=False):
    c = re.sub(r'url\("data:[^"]*"\)', 'url(DATA)', c)
    return c
def norm_color(c):
    return re.sub(r'url\("(data:[^"]*)"\)', lambda m: 'url("' + re.sub(r"%23[0-9A-Fa-f]{6}", "%23COLOR", m.group(1)) + '")', c)

names = list(FILES)
base = names[0]
for other in names[1:]:
    a = norm_chrome(REPORT[base]["chrome"]); b = norm_chrome(REPORT[other]["chrome"])
    print(f"chrome text ({base} vs {other}) identical after data-URI normalise: {a == b}")
    if a != b:
        import difflib
        for line in list(difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm=""))[:20]:
            print("   ", line[:160])
    ca = norm_color(REPORT[base]["chrome"]); cb = norm_color(REPORT[other]["chrome"])
    print(f"chrome incl. SVG (stroke colours normalised) identical: {ca == cb}")
    for n in names:
        pass
    break

BARS = {n: REPORT[n]["chrome"][REPORT[n]["chrome"].find("/* ---------- LCARS top bar and bottom bar"):] for n in names}
print("bars block identical across files:", len(set(BARS.values())) == 1)
if len(set(BARS.values())) != 1: issues.append(("all", "bars", "bars block differs between files"))

# var() usage in chrome
for n in names:
    used = sorted(set(re.findall(r"var\(--([a-z0-9-]+)\)", REPORT[n]["chrome"])))
    missing = [u for u in used if u not in REPORT[n]["L"] or u not in REPORT[n]["D"]]
    print(f"{n}: chrome var() names={len(used)} missing-in-either-block={missing}")

# Contrast
rows = []
for n in names:
    for mode in ("light", "dark"):
        T = REPORT[n]["L" if mode == "light" else "D"]
        C = lambda k: parse_color(T[k])
        pairs = [
            ("ink/canvas", "ink", "canvas", 4.5),
            ("foreground/canvas", "foreground", "canvas", 4.5),
            ("muted-fg/canvas", "muted-foreground", "canvas", 4.5),
            ("subtle-fg/canvas", "subtle-foreground", "canvas", 4.5),
            ("primary/canvas", "primary", "canvas", 4.5),
            ("sidebar-fg/sidebar", "sidebar-foreground", "sidebar", 4.5),
        ]
        for label, f, b, t in pairs:
            rows.append((n, mode, label, ratio(C(f), C(b)), t))
        worst = min(((ratio(C("lcars-pill-ink"), C(f"lcars-pill-{i}")), i) for i in range(1, 5)))
        for i in range(1, 5):
            rows.append((n, mode, f"pill-ink/pill-{i}", ratio(C("lcars-pill-ink"), C(f"lcars-pill-{i}")), 4.5))
        rows.append((n, mode, "end-label(--sidebar)/frame-2", ratio(C("sidebar"), C("lcars-frame-2")), 4.5))
        rows.append((n, mode, "promptbox label (--lcars-label, opacity 1)", ratio(C("lcars-label"), C("canvas")), 4.5))
        rows.append((n, mode, "section header (--lcars-header-ink)/sidebar", ratio(C("lcars-header-ink"), C("sidebar")), 4.5))
        # Bars are non-text graphics: WCAG 1.4.11 asks 3:1 against neighbours. Top bar sits on --surface-scrim over canvas; status bar on --canvas.
        for tok in ("lcars-frame", "lcars-frame-2", "lcars-pill-1", "lcars-pill-2", "lcars-pill-4"):
            rows.append((n, mode, f"bars graphic --{tok}/canvas" + ("" if tok in ("lcars-frame", "lcars-frame-2") else " (info, decorative)"), ratio(C(tok), C("canvas")), 3.0 if tok in ("lcars-frame", "lcars-frame-2") else 0))
        rows.append((n, mode, "(info) optional cap text pill-ink/frame (dropped)", ratio(C("lcars-pill-ink"), C("lcars-frame")), 0))
        rows.append((n, mode, "(info) --lcars-frame/sidebar", ratio(C("lcars-frame"), C("sidebar")), 0))
        rows.append((n, mode, "open row ink/row-active", ratio(C("lcars-row-active-ink"), C("lcars-row-active")), 4.5))

print()
print(f"{'file':12} {'mode':6} {'check':42} {'ratio':>6}  result")
for n, mode, label, r, t in rows:
    flag = "FAIL" if r < t else "pass"
    if mode == "dark" and label in ("ink/canvas", "foreground/canvas") and r > 12.5:
        flag = "FAIL (bloom >12.5)"
    print(f"{n:12} {mode:6} {label:42} {r:6.2f}  {flag}")

print()
print("Suggested fixes (hue kept, minimal lightness shift):")
for n in names:
    for mode in ("light", "dark"):
        T = REPORT[n]["L" if mode == "light" else "D"]
        C = lambda k: parse_color(T[k])
        for label, f, b in [("ink","ink","canvas"),("foreground","foreground","canvas"),("muted-fg","muted-foreground","canvas"),
                            ("subtle-fg","subtle-foreground","canvas"),("primary","primary","canvas"),("sidebar-fg","sidebar-foreground","sidebar")]:
            if ratio(C(f), C(b)) < 4.5:
                print(f"  {n} {mode} --{f} on --{b}: {T[f]} -> {fix_fg(C(f), C(b), 4.5)}")
        if mode == "dark":
            for f in ("ink", "foreground"):
                if ratio(C(f), C("canvas")) > 12.5:
                    print(f"  {n} dark --{f} bloom {ratio(C(f), C('canvas')):.2f}: {T[f]} -> {fix_fg(C(f), C('canvas'), 12.0, mode='lower')}")
        for i in range(1, 5):
            if ratio(C("lcars-pill-ink"), C(f"lcars-pill-{i}")) < 4.5:
                print(f"  {n} {mode} --lcars-pill-ink on --lcars-pill-{i} ({T[f'lcars-pill-{i}']}): {T['lcars-pill-ink']} -> {fix_fg(C('lcars-pill-ink'), C(f'lcars-pill-{i}'), 4.5)}")
        if ratio(C("sidebar"), C("lcars-frame-2")) < 4.5:
            print(f"  {n} {mode} end-label --sidebar on --lcars-frame-2 ({T['lcars-frame-2']}): alt bg fix {fix_fg(C('lcars-frame-2'), C('sidebar'), 4.5)} (frame-2 is the block bg; text stays --sidebar)")

print()
print("Syntax/SVG/token issues:")
for i in issues: print("  ", i)
if not issues: print("   none")
