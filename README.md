# bb-theme-lcars

LCARS themes for the bb IDE, inspired by the computer displays in *Star Trek: The Next Generation*.

| Theme | Accent |
|---|---|
| `lcars-tng` | Orange and lavender (the classic bridge look) |
| `lcars-science` | Blue (Science/Ops) |
| `lcars-ten-forward` | Purple and mauve (Ten Forward) |

Each theme has a light mode and a dark mode.

## What the themes change

- An LCARS elbow frame around the left sidebar, the right panel, the top bar and the bottom status bar.
- Thread rows that look like LCARS menu buttons. The open thread is a solid pill.
- Section headers with elbows and uppercase labels.
- Pill buttons and badges.
- Decorative LCARS numbers ("47-1701", "LCARS 23-781").
- A faded Galaxy-class blueprint behind the thread area. It takes the colour of the theme.

All text colours pass WCAG AA contrast (4.5:1 or better).

## Install

Copy a theme folder into your bb theme directory, then select it:

```sh
THEME_DIR="$HOME/.bb-machines/<your-bb-host>/theme"   # see `bb theme list` for the path
cp -R themes/lcars-tng themes/lcars-science themes/lcars-ten-forward "$THEME_DIR/"
bb theme set lcars-tng
```

bb reloads the theme when the file changes.

## Change the themes

- Edit the CSS in `themes/<name>/theme.css`. Keep the chrome rules the same in all three files. Only the token blocks and the baked SVG stroke colours differ.
- Tune the background strength with `--lcars-schematic-opacity` in each token block.
- Run `python3 tools/qa_lcars.py` after a change. It checks syntax, tokens, contrast and that the chrome rules match across the three themes.

### Replace the background image

1. Make a mask from a blue-on-white blueprint PNG (RGB or RGBA, 8-bit, not interlaced):
   `python3 tools/png_mask.py source.png assets/galaxy_mask.png`
2. Embed the mask in all three themes: `python3 tools/apply_blueprint.py`

The tools use only the Python standard library.

## Notes

- The styles target bb's live DOM (tested on bb 0.50.1). A bb update can change the DOM hooks, and some chrome can then stop matching.
- The blueprint mask comes from a third-party Galaxy-class poster, and LCARS and Star Trek are Paramount trademarks. Keep this repo private and for internal use. Do not publish it to a plugin marketplace.
