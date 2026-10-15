# Figures (SVG) for SOF-style questions

Read this guide when a spec row has `"figure": true`, when a style needs picture options, or when
a group of questions shares one figure. Build every figure as an SVG string with python3 and store
it in the part JSON.

## 1. Where figures go

| Place | How | Size |
|---|---|---|
| Question figure | `"figure": "<svg ...>"`; optional `"figure_position"`: `"below"` (default), `"above"`, or `"right"` (a small figure beside a short stem) | 60-340 px wide, ideally at most 260 px high |
| Figure options | `"options": {"A": {"svg": "<svg ...>"}, ...}`; each option may add a short `"text"` caption | At most 140 px wide; all four the same size |
| Shared figure | A `directions` entry with `"figure"` for the questions `from`-`to` | As for a question figure |

- Add a figure only when the student needs it to answer. Rows with `figure: false` get no figure.
- Put tables (timetables, bills, marks lists, pictographs) in the `table` field, never in an SVG.
- With figure options, leave `option_layout` out: `auto` puts all four options in one row.

## 2. SVG rules (the validator checks these)

- The root element is `<svg>` with `xmlns='http://www.w3.org/2000/svg'`, numeric `width` and
  `height` (pixels, no units) and a `viewBox`.
- The SVG must be well-formed XML. Use single quotes for attributes so the JSON stays readable.
- These are forbidden: DOCTYPE or ENTITY declarations; `<script>`, `<foreignObject>`, `<iframe>`,
  `<object>` and `<embed>`; `on...=` event attributes; any `href` or `url(` that does not point
  to a local `#id`; `@import`; `javascript:`; external images or fonts.
- Escape `&` and `<` inside `<text>`. The `text()` helper below does this for you.
- Papers are printed in black and white:
  - Use black strokes of width 1.5-2.
  - Use fills of `none` or white, or the greys `#eee`, `#ddd` and `#999`.
  - Never make the answer depend on colour. Use shading, dots or labels instead.
- Use `font-family='Arial, sans-serif'` at size 12-18. Labels must not overlap lines.
- Draw arrowheads as small polygons, not markers.
- Do not draw real logos, icons or screenshots of software. Use simple generic shapes, or name the
  tool in words.

## 3. Helper functions (copy into your build script)

```python
import math
from xml.sax.saxutils import escape

def svg(w, h, body, fs=14):
    return ("<svg xmlns='http://www.w3.org/2000/svg' width='%d' height='%d' viewBox='0 0 %d %d' "
            "font-family='Arial, sans-serif' font-size='%d'>%s</svg>" % (w, h, w, h, fs, body))

def line(x1, y1, x2, y2, sw=2, dash=False, col='#000'):
    d = " stroke-dasharray='5 4'" if dash else ""
    return ("<line x1='%g' y1='%g' x2='%g' y2='%g' stroke='%s' stroke-width='%g'%s/>"
            % (x1, y1, x2, y2, col, sw, d))

def rect(x, y, w, h, fill='none', sw=2):
    return ("<rect x='%g' y='%g' width='%g' height='%g' fill='%s' stroke='#000' stroke-width='%g'/>"
            % (x, y, w, h, fill, sw))

def circle(cx, cy, r, fill='none', sw=2):
    return ("<circle cx='%g' cy='%g' r='%g' fill='%s' stroke='#000' stroke-width='%g'/>"
            % (cx, cy, r, fill, sw))

def poly(points, fill='none', sw=2, closed=True):
    pts = ' '.join('%g,%g' % p for p in points)
    return ("<%s points='%s' fill='%s' stroke='#000' stroke-width='%g' stroke-linejoin='round'/>"
            % ('polygon' if closed else 'polyline', pts, fill, sw))

def text(x, y, s, size=None, anchor='middle', bold=False):
    extra = (" font-size='%d'" % size if size else '') + (" font-weight='bold'" if bold else '')
    return ("<text x='%g' y='%g' text-anchor='%s' dominant-baseline='middle'%s>%s</text>"
            % (x, y, anchor, extra, escape(str(s))))
```

Put the returned string straight into the question, for example `q["figure"] = svg(...)`, and let
`json.dump` do the escaping. Never type SVG markup into JSON by hand.

## 4. Templates (all coordinates in px)

Use whole-number coordinates. Build every figure from the helpers in section 3.

### 4.1 Mirror and water images

```python
def mirror(body, w):        # left-right flip inside a box of width w
    return "<g transform='translate(%g,0) scale(-1,1)'>%s</g>" % (w, body)

def water(body, h):         # top-bottom flip inside a box of height h
    return "<g transform='translate(0,%g) scale(1,-1)'>%s</g>" % (h, body)

def half_turn(body, w, h):  # rotate 180 degrees about the box centre
    return "<g transform='rotate(180 %g %g)'>%s</g>" % (w / 2.0, h / 2.0, body)
```

- Draw the object once as `body` in a fixed box (for example 100 x 100), then build every option
  from that same body.
- The question figure shows the object and a dashed line labelled "Mirror" (vertical, on the right)
  or "Water" (horizontal, below), e.g. `line(110, 5, 110, 95, dash=True)`.
- Options: the correct image, the other flip, the half turn, and a near miss (one small part moved).
- Choose objects that change when flipped: letters F, R, J, G, digits 4 and 7, a flag, an arrow
  with a dot. Symmetric objects make two options identical, so never use them.
- Text inside a flipped group is flipped too. That is intended for letters and digits.

### 4.2 Counting triangles, squares and rectangles

Count in python, never by eye. Put every corner and every crossing point in `pts`. Put every drawn
straight line in `segs` as ONE segment from end to end (do not split it at crossings), and draw the
figure from the same list: `''.join(line(a[0], a[1], b[0], b[1]) for a, b in segs)`.

```python
from itertools import combinations

def on(p, a, b):        # point p lies on segment ab
    cr = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    return (abs(cr) < 1e-9
            and min(a[0], b[0]) - 1e-9 <= p[0] <= max(a[0], b[0]) + 1e-9
            and min(a[1], b[1]) - 1e-9 <= p[1] <= max(a[1], b[1]) + 1e-9)

def joined(p, q):       # p and q lie on one drawn segment
    return any(on(p, a, b) and on(q, a, b) for a, b in segs)

def area2(p, q, r):
    return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

triangles = sum(1 for p, q, r in combinations(pts, 3)
                if abs(area2(p, q, r)) > 1e-9
                and joined(p, q) and joined(q, r) and joined(p, r))

# Upright rectangles; squares are the ones with equal sides.
xs = sorted({p[0] for p in pts})
ys = sorted({p[1] for p in pts})
rects = [(x1, y1, x2, y2) for x1, x2 in combinations(xs, 2) for y1, y2 in combinations(ys, 2)
         if joined((x1, y1), (x2, y1)) and joined((x1, y2), (x2, y2))
         and joined((x1, y1), (x1, y2)) and joined((x2, y1), (x2, y2))]
squares = [r for r in rects if r[2] - r[0] == r[3] - r[1]]
```

- Distractors come from typical miscounts: only the smallest shapes, the true count minus 2, the
  true count plus 2.
- Keep figures small enough to count by hand in about a minute (answers of 8 to 20 are typical).

### 4.3 Number grid with "?"

```python
def grid(vals, cell=56):    # vals: list of rows, e.g. [[2, 5, 10], [3, 6, 18], [4, 7, "?"]]
    rows, cols = len(vals), len(vals[0])
    body = ""
    for r, row in enumerate(vals):
        for c, v in enumerate(row):
            x, y = 10 + c * cell, 10 + r * cell
            body += rect(x, y, cell, cell)
            body += text(x + cell / 2.0, y + cell / 2.0, v, size=18, bold=(v == "?"))
    return svg(20 + cols * cell, 20 + rows * cell, body)
```

- One rule must work for every row (or every column) and give exactly one answer. Check it in
  python and state the rule in the explanation.
- Distractors: the answer from a wrong rule that fits only one row, and the answer plus or minus a
  small amount.

### 4.4 Clock faces

```python
def clock(h, m, r=70):
    c = r + 10
    body = circle(c, c, r)
    for k in range(1, 13):
        a = math.radians(30 * k)
        body += text(c + (r - 14) * math.sin(a), c - (r - 14) * math.cos(a), k, size=13)
    for ang, L, sw in ((30 * (h % 12) + 0.5 * m, r * 0.5, 4), (6 * m, r * 0.78, 2.5)):
        a = math.radians(ang)       # hour hand first (short, thick), then minute hand
        body += line(c, c, c + L * math.sin(a), c - L * math.cos(a), sw=sw)
    return svg(2 * c, 2 * c, body + circle(c, c, 3, fill='#000'))
```

- Use minutes that are multiples of 5 so the time can be read exactly.
- Mirror time = 11:60 minus the actual time (3:15 gives 8:45; 1:00 gives 11:00). For times from
  12:00 to 12:59 use 23:60 minus the time (12:20 gives 11:40). Compute it in python.
- Angle between the hands = |30 x h - 5.5 x m|; if this is more than 180, subtract it from 360.

### 4.5 Dice, cubes and nets

- Nets: draw six 40 px squares with `rect` and a symbol or number in each. On a net, two faces in
  the same straight row or column with exactly one face between them are opposite faces.

```python
def cube(x, y, s, front, top, right):   # one isometric cube showing three faces
    d = s / 2.0
    body = rect(x, y, s, s, fill='#fff')
    body += poly([(x, y), (x + s, y), (x + s + d, y - d), (x + d, y - d)], fill='#eee')
    body += poly([(x + s, y), (x + s + d, y - d), (x + s + d, y + s - d), (x + s, y + s)], fill='#ddd')
    body += text(x + s / 2.0, y + s / 2.0, front)
    body += text(x + s / 2.0 + d / 2.0, y - d / 2.0, top)
    body += text(x + s + d / 2.0, y + s / 2.0 - d / 2.0, right)
    return body
```

- Keep `y >= d + 5` and make the svg at least `x + s + d + 5` wide. Two or three views sit side by
  side in one svg, e.g. `svg(300, 110, cube(10, 40, 60, ...) + cube(110, 40, 60, ...))`.
- Show 2 or 3 views of the same dice. In python, check that exactly one option fits ALL the views.
- Say "opposite faces add up to 7" only when the question needs it; not every SOF dice question is a
  standard dice.

### 4.6 Bar graph

```python
def bar_graph(labels, values, step, top, title=''):
    W, H, x0, y0 = 340, 230, 45, 190
    k = (y0 - 30) / float(top)
    bw = (W - x0 - 20) / float(len(labels))
    body = line(x0, y0, W - 10, y0) + line(x0, y0, x0, 25)
    for v in range(0, top + 1, step):
        y = y0 - v * k
        body += line(x0 - 4, y, x0, y, sw=1) + text(x0 - 8, y, v, size=11, anchor='end')
    for i, (lab, val) in enumerate(zip(labels, values)):
        body += rect(x0 + i * bw + 0.2 * bw, y0 - val * k, 0.6 * bw, val * k, fill='#ddd', sw=1.5)
        body += text(x0 + i * bw + bw / 2.0, y0 + 14, lab, size=11)
    if title:
        body += text(W / 2.0, 12, title, size=13, bold=True)
    return svg(W, H, body)
```

- At most 6 bars, labels of at most 8 characters, every value a multiple of `step`, and `top` a
  multiple of `step` that is at least the largest value.
- When 2 or 3 questions share one graph, put the graph in a `directions` entry (with `from`, `to`,
  `text` and `figure`) instead of repeating it in each question.

### 4.7 Pictograph (use a table, not an SVG)

```python
q["table"] = {"headers": ["Day", "Books read"],
              "rows": [["Monday", "● ● ●"], ["Tuesday", "● ● ◐"], ["Wednesday", "● ● ● ●"]],
              "caption": "Key: ● = 10 books, ◐ = 5 books"}
```

- Use plain symbols (● ◐ ■ ★ ✓), never emoji. Always give the key in `caption`.
- A half symbol must be exactly half of the key value.

### 4.8 Venn diagrams

```python
def venn2(a_name, b_name, only_a, both, only_b, outside=None):
    body = circle(100, 100, 62) + circle(170, 100, 62)
    body += text(80, 25, a_name, size=13, bold=True) + text(190, 25, b_name, size=13, bold=True)
    body += text(72, 100, only_a) + text(135, 100, both) + text(198, 100, only_b)
    if outside is not None:                 # a box for "neither"
        body += rect(5, 5, 260, 180, sw=1.5) + text(245, 172, outside)
    return svg(270, 190, body)

def venn3(names, regions):  # names: (A, B, C); regions: dict of counts or "?"
    # keys: "a", "b", "c", "ab", "ac", "bc", "abc" (each means "only these sets")
    body = circle(100, 95, 58) + circle(170, 95, 58) + circle(135, 155, 58)
    body += (text(70, 22, names[0], size=13, bold=True) + text(200, 22, names[1], size=13, bold=True)
             + text(135, 228, names[2], size=13, bold=True))
    spots = {"a": (75, 80), "b": (195, 80), "c": (135, 190), "ab": (135, 70),
             "ac": (100, 140), "bc": (170, 140), "abc": (135, 112)}
    for key, (x, y) in spots.items():
        if key in regions:
            body += text(x, y, regions[key])
    return svg(270, 240, body)
```

- Set names of at most 12 characters. Work out every region from python sets, e.g.
  `only_a = len(A - B)`, `both = len(A & B)`, and check every total used in the stem.
- Typical questions: how many like only one, both, at least one, or neither.

### 4.9 Number figures (find the missing number)

```python
def num_triangle(x, top, left, right, mid):
    body = poly([(x + 55, 22), (x + 10, 100), (x + 100, 100)])
    body += text(x + 55, 10, top) + text(x + 10, 115, left) + text(x + 100, 115, right)
    body += text(x + 55, 72, mid, bold=(mid == "?"))
    return body

data = [(2, 3, 4, 24), (1, 5, 2, 10), (3, 2, 5, "?")]   # rule: centre = top x left x right
q["figure"] = svg(340, 125, "".join(num_triangle(5 + i * 110, *d) for i, d in enumerate(data)))
```

- Two or three figures side by side (at most 340 px wide), with "?" only in the last one.
- One rule must work for every figure. In python, also try 2-3 other simple rules (sum, sum x 2,
  product, difference) on the complete figures; if another rule also fits them all, change the numbers.
- The same idea works for a circle cut into parts or a square with numbers at its corners: build it
  with `circle`, `line` and `text`, and keep every number well inside its part.

### 4.10 Logo / turtle paths (ICSO)

```python
def turtle(cmds):  # e.g. [("FD", 50), ("RT", 90)]; expand REPEAT first
    x = y = 0.0
    head = 0.0  # 0 = facing up; RT turns clockwise
    pts = [(x, y)]
    for c, n in cmds:
        if c in ("FD", "BK"):
            d = n if c == "FD" else -n
            x += d * math.sin(math.radians(head))
            y -= d * math.cos(math.radians(head))
            pts.append((round(x, 2), round(y, 2)))
        elif c == "RT":
            head += n
        elif c == "LT":
            head -= n
    return pts

def path_body(pts, scale=1.0, pad=15):
    xs = [p[0] * scale for p in pts]
    ys = [p[1] * scale for p in pts]
    q = [(round(x - min(xs) + pad, 1), round(y - min(ys) + pad, 1)) for x, y in zip(xs, ys)]
    body = poly(q, closed=False) + circle(q[0][0], q[0][1], 4, fill='#000')
    w = max(60, int(math.ceil(max(xs) - min(xs) + 2 * pad)))
    h = max(60, int(math.ceil(max(ys) - min(ys) + 2 * pad)))
    return body, w, h

def path_svg(pts, scale=1.0, pad=15):
    body, w, h = path_body(pts, scale, pad)
    return svg(w, h, body)

cmds = [("FD", 60), ("RT", 90)] * 4        # REPEAT 4 [FD 60 RT 90] draws a square
q["figure"] = path_svg(turtle(cmds))
```

- Write the commands in the stem in capitals: FD, BK, RT, LT and REPEAT n [ ... ]. Do not use PU or
  PD in a question that has a figure.
- The black dot is the start. Say "The turtle starts at the dot, facing up." in the stem.
- Keep the drawing within 300 x 300 px; reduce `scale` if needed.
- Scratch questions: describe the blocks in words or in a `table` (one block per row). Never use
  screenshots or pictures of blocks.

### 4.11 Options that are figures

```python
letters = "ABCD"
bodies = [wrong1, wrong2, wrong3]                    # each a body built with the helpers
bodies.insert(letters.index(row["answer"]), right)   # the correct figure goes at the row's letter
q["options"] = {L: {"svg": svg(120, 120, b)} for L, b in zip(letters, bodies)}
```

- Use the same box (at most 140 x 140 px) and the same scale for all four options.
- Odd-one-out options: only the intended rule may single out the answer. Draw the shapes at a
  similar size, and do not let one option be the only small, rotated or flat-topped one. Keep
  dots and marks at least 10 px inside every edge and at least 18 px apart (centre to centre).
- Do not set `option_layout`; `auto` puts figure options in one row.
- Each wrong option differs from the right one in one small way: flipped, turned, one line
  missing or extra, or a different count. Never make a wrong option that is also correct.
- An option may have a short label too: `{"text": "Shape P", "svg": svg(...)}`.
- Turtle-path options: `path_body(turtle(cmds), scale)[0]` for each, with
  `scale = 90.0 / (largest width or height of the four paths)`, so they match in size.

### 4.12 Shapes on a grid and fraction bars

```python
def grid_shape(cells, cell=20, cols=10, rows=8):
    body = ""
    for c in range(cols + 1):
        body += line(10 + c * cell, 10, 10 + c * cell, 10 + rows * cell, sw=0.5, col='#999')
    for r in range(rows + 1):
        body += line(10, 10 + r * cell, 10 + cols * cell, 10 + r * cell, sw=0.5, col='#999')
    for (c, r) in cells:
        body += rect(10 + c * cell, 10 + r * cell, cell, cell, fill='#ccc', sw=1)
    return svg(20 + cols * cell, 20 + rows * cell, body)

def fraction_bar(n, shaded, w=240, h=40):
    body = "".join(rect(10 + i * w / float(n), 10, w / float(n), h,
                        fill='#ccc' if i in shaded else 'none') for i in range(n))
    return svg(w + 20, h + 20, body)

cells = {(1, 1), (2, 1), (3, 1), (1, 2), (2, 2)}           # (column, row) of shaded squares
area = len(cells)                                          # in square units
perimeter = sum(4 - sum((c + dc, r + dr) in cells
                        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)))
                for c, r in cells)                         # in units
q["figure"] = grid_shape(cells)
```

- Say in the stem what one small square stands for ("Each small square is 1 cm by 1 cm.").
- Compute area and perimeter in python as above; never count by eye.
- Fraction bars: `fraction_bar(8, {0, 1, 2})` shows 3/8 shaded. Use at most 12 parts.

## 5 Figure checklist

- Built in python with the helpers; no SVG typed by hand.
- The figure is really needed, and every number and label in it matches the stem, the options
  and the explanation.
- Counts, times, paths, areas and Venn regions are computed in python, not by eye.
- Question figures are 60-340 px wide; option figures are at most 140 px wide.
- Readable when printed in black and white. Never refer to colours ("the shaded part", not
  "the blue part").
- `validate_cmd` passes. SVG problems are errors; a size outside the limits is a warning, but fix
  it anyway.
