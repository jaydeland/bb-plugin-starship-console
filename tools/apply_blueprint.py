# Embed assets/galaxy_mask.png as the colour-masked background layer of each theme (idempotent).
import base64, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
b64 = base64.b64encode((ROOT / "assets/galaxy_mask.png").read_bytes()).decode()
START = "/* ---------- LCARS blueprint background ---------- */"
block = f'''{START}
/* The schematic is a mask, so its ink takes --lcars-schematic in every theme and mode. */
:root [data-thread-window]::before,
:root.dark [data-thread-window]::before {{
  background-color: var(--lcars-schematic);
  mask: url("data:image/png;base64,{b64}") center / contain no-repeat;
}}
'''
for n in ["lcars-tng", "lcars-science", "lcars-ten-forward"]:
    p = ROOT / "themes" / n / "theme.css"
    s = p.read_text()
    if START in s:
        # Remove only the old blueprint block (up to the next section marker), so later rules survive.
        head, tail = s.split(START, 1)
        nxt = tail.find("\n/* ---------- ")
        s = head.rstrip("\n") + ("\n\n" + tail[nxt:].strip("\n") if nxt != -1 else "")
    p.write_text(s.rstrip("\n") + "\n\n" + block)
    print(n, len(s) + len(block))
