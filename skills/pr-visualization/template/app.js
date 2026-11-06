/* PR Atlas renderer. Reusable for every PR: all PR-specific content comes from window.PR_DATA
   ({meta, spec, diff, sources, issues}) which pr_viz.py inlines above this script. */
(() => {
  'use strict';
  const D = window.PR_DATA || {};
  const S = D.spec || {};
  const M = D.meta || {};
  const SOURCES = D.sources || {};
  const DIFF = D.diff || [];
  const SVG_NS = 'http://www.w3.org/2000/svg';

  // ── DOM helpers ──────────────────────────────────────────────────────────
  function h(tag, attrs, ...kids) {
    const node = document.createElement(tag);
    applyAttrs(node, attrs);
    appendKids(node, kids);
    return node;
  }
  function s(tag, attrs, ...kids) {
    const node = document.createElementNS(SVG_NS, tag);
    applyAttrs(node, attrs);
    appendKids(node, kids);
    return node;
  }
  function applyAttrs(node, attrs) {
    if (!attrs) return;
    for (const [key, value] of Object.entries(attrs)) {
      if (value === undefined || value === null || value === false) continue;
      if (key === 'class') node.setAttribute('class', value);
      else if (key === 'text') node.textContent = value;
      else if (key === 'html') node.innerHTML = value;
      else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? '' : value);
    }
  }
  function appendKids(node, kids) {
    for (const kid of (Array.isArray(kids) ? kids.flat(Infinity) : [kids])) {
      if (kid === undefined || kid === null || kid === false) continue;
      node.appendChild(typeof kid === 'string' || typeof kid === 'number' ? document.createTextNode(String(kid)) : kid);
    }
  }
  const esc = (t) => String(t ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  /* Inline markup for spec prose: `code`, **bold**. Everything else is escaped. */
  function rich(text) {
    return esc(text)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  }
  const richEl = (tag, text, cls) => h(tag, { class: cls, html: rich(text) });
  const slug = (t) => String(t).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  const store = {
    get(k) { try { return localStorage.getItem('pr-atlas:' + k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem('pr-atlas:' + k, v); } catch (e) { /* storage blocked */ } },
  };

  // ── Registries: layers, symbols, files ───────────────────────────────────
  const DEFAULT_LAYERS = [
    { id: 'model', label: 'Data models', color: 'teal' },
    { id: 'api', label: 'API / Router', color: 'blue' },
    { id: 'service', label: 'Services', color: 'violet' },
    { id: 'repository', label: 'Repositories', color: 'amber' },
    { id: 'infra', label: 'Infra / Startup', color: 'slate' },
    { id: 'external', label: 'External systems', color: 'rose' },
    { id: 'tests', label: 'Tests', color: 'green' },
  ];
  const LAYERS = (S.layers && S.layers.length ? S.layers : DEFAULT_LAYERS);
  const LAYER = Object.fromEntries(LAYERS.map((l, i) => [l.id, { ...l, index: i }]));
  const layerColor = (id) => (LAYER[id] && LAYER[id].color) || 'slate';
  const layerLabel = (id) => (LAYER[id] && LAYER[id].label) || id || 'Other';

  const SYM = {};
  const FILE_LAYER = {};
  const FILE_INFO = {};
  ((S.layout && S.layout.groups) || []).forEach((group) => {
    (group.files || []).forEach((file) => {
      FILE_LAYER[file.path] = group.layer;
      FILE_INFO[file.path] = file;
      (file.symbols || []).forEach((sym) => { SYM[sym.id] = { ...sym, file: file.path, layer: group.layer }; });
    });
  });
  const CALLED_BY = {};
  Object.values(SYM).forEach((sym) => (sym.calls || []).forEach((c) => { (CALLED_BY[c] = CALLED_BY[c] || []).push(sym.id); }));
  const DIFF_BY_PATH = Object.fromEntries(DIFF.map((f, i) => [f.path, { ...f, index: i }]));

  function guessLayer(path) {
    if (FILE_LAYER[path]) return FILE_LAYER[path];
    if (/^tests?\//.test(path)) return LAYER.tests ? 'tests' : null;
    return null;
  }
  function refParts(ref) {
    const m = /^(.+?):(\d+)(?:-(\d+))?$/.exec(ref || '');
    return m ? { path: m[1], start: +m[2], end: +(m[3] || m[2]) } : null;
  }
  const shortRef = (ref) => {
    const p = refParts(ref);
    return p ? `${p.path.split('/').pop()}:${p.start}${p.end !== p.start ? '–' + p.end : ''}` : ref;
  };

  // ── Syntax highlighting (small, stateful per line so triple-quoted strings span lines) ──
  const LANGS = {
    python: {
      kw: 'False None True and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield match case',
      builtins: 'print len str int float dict list set tuple bool isinstance getattr setattr hasattr range enumerate zip map filter sorted sum min max any all open super type id repr round object Exception ValueError TypeError KeyError self cls',
      comment: '#', triple: true, decorators: true,
    },
    js: {
      kw: 'const let var function return if else for while do switch case break continue new class extends import from export default try catch finally throw async await of in typeof instanceof null undefined true false this',
      builtins: 'console document window Object Array String Number Math JSON Promise Map Set',
      comment: '//', triple: false, decorators: false,
    },
    yaml: { kw: 'true false null yes no', builtins: '', comment: '#', triple: false, decorators: false },
  };
  Object.values(LANGS).forEach((l) => { l.kwSet = new Set(l.kw.split(' ')); l.biSet = new Set(l.builtins.split(' ').filter(Boolean)); });
  function langOf(path) {
    if (/\.py$/.test(path)) return 'python';
    if (/\.(m?js|jsx|ts|tsx)$/.test(path)) return 'js';
    if (/\.ya?ml$/.test(path)) return 'yaml';
    return null;
  }
  function highlightLine(line, lang, state) {
    const L = LANGS[lang];
    if (!L) return { html: esc(line), state };
    let out = '';
    let i = 0;
    let prevWord = '';
    const span = (cls, text) => `<span class="tk-${cls}">${esc(text)}</span>`;
    if (state.tri) {
      const close = line.indexOf(state.tri);
      if (close === -1) return { html: span('str', line), state };
      out += span('str', line.slice(0, close + 3));
      i = close + 3;
      state = { tri: null };
    }
    while (i < line.length) {
      const rest = line.slice(i);
      const prevChar = i > 0 ? line[i - 1] : '';
      if (rest.startsWith(L.comment)) { out += span('com', rest); break; }
      const strMatch = /^([rRbBuUfF]{0,2})("""|'''|"|'|`)/.exec(rest);
      if (strMatch && !/\w/.test(prevChar)) {
        const q = strMatch[2];
        const startLen = strMatch[0].length;
        if (q.length === 3) {
          const close = rest.indexOf(q, startLen);
          if (close === -1) { out += span('str', rest); state = { tri: q }; break; }
          out += span('str', rest.slice(0, close + 3)); i += close + 3; continue;
        }
        let j = startLen;
        while (j < rest.length && rest[j] !== q) j += rest[j] === '\\' ? 2 : 1;
        out += span('str', rest.slice(0, j + 1)); i += j + 1; continue;
      }
      if (L.decorators && rest[0] === '@' && line.slice(0, i).trim() === '') {
        const m = /^@[\w.]+/.exec(rest);
        if (m) { out += span('dec', m[0]); i += m[0].length; continue; }
      }
      const num = /^\d[\d_]*(\.\d+)?/.exec(rest);
      if (num && !/\w/.test(prevChar)) { out += span('num', num[0]); i += num[0].length; continue; }
      const word = /^[A-Za-z_]\w*/.exec(rest);
      if (word) {
        const w = word[0];
        const after = line.slice(i + w.length);
        if (L.kwSet.has(w)) out += span('kw', w);
        else if (prevWord === 'def' || prevWord === 'class' || prevWord === 'function') out += span('fn', w);
        else if (L.biSet.has(w)) out += span('bi', w);
        else if (/^\s*\(/.test(after)) out += span('call', w);
        else if (/^[A-Z][A-Z0-9_]{2,}$/.test(w)) out += span('const', w);
        else out += esc(w);
        prevWord = w; i += w.length; continue;
      }
      if (rest[0] !== ' ') prevWord = '';
      out += esc(rest[0]); i += 1;
    }
    return { html: out, state };
  }
  function highlightJSON(value) {
    const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
    return esc(text).replace(/(&quot;|")((?:\\.|[^"\\])*?)\1(\s*:)?|\b(true|false|null)\b|-?\b\d+(?:\.\d+)?\b/g, (m, q, body, colon, lit) => {
      if (q) return colon ? `<span class="tk-key">"${body}"</span>${colon}` : `<span class="tk-str">"${body}"</span>`;
      if (lit) return `<span class="tk-kw">${lit}</span>`;
      return `<span class="tk-num">${m}</span>`;
    });
  }

  // ── Small shared components ──────────────────────────────────────────────
  const CHANGE_LABEL = { added: 'Added', modified: 'Modified', removed: 'Removed', renamed: 'Renamed', unchanged: 'Unchanged', existing: 'Existing' };
  const changeBadge = (change) => change ? h('span', { class: `badge chg-${change}`, text: CHANGE_LABEL[change] || change }) : null;
  const layerChip = (id) => id ? h('span', { class: `chip lc-${layerColor(id)}`, text: layerLabel(id) }) : null;
  const tagChips = (tags) => (tags || []).map((t) => h('span', { class: `tag tag-${slug(t)}`, text: t }));
  function symButton(id, opts = {}) {
    const sym = SYM[id];
    if (!sym) return h('code', { class: 'sym-missing', text: id });
    return h('button', {
      type: 'button', class: `sym-btn lc-${layerColor(sym.layer)}${opts.compact ? ' compact' : ''}`,
      title: `${sym.file || ''}${sym.ref ? ' · ' + shortRef(sym.ref) : ''}`,
      onclick: (e) => { e.stopPropagation(); openSymbol(id); },
    }, h('span', { class: 'sym-dot' }), sym.name);
  }
  function refButton(ref, label) {
    return h('button', { type: 'button', class: 'ref-btn', title: ref, onclick: (e) => { e.stopPropagation(); openRef(ref); } }, label || shortRef(ref));
  }
  function codeBlock(text, lang) {
    const pre = h('pre', { class: 'code' });
    if (lang === 'json') pre.innerHTML = highlightJSON(text);
    else {
      let state = {};
      pre.innerHTML = String(text).split('\n').map((ln) => { const r = highlightLine(ln, lang, state); state = r.state; return r.html; }).join('\n');
    }
    return h('div', { class: 'code-wrap' }, pre);
  }
  function snippet(ref) {
    const src = SOURCES[ref];
    if (!src) return h('p', { class: 'muted small', text: `Source for ${ref} was not embedded (ref not found at the PR head).` });
    const added = new Set(src.added || []);
    const lang = langOf(src.path);
    const fStart = src.focusStart || src.start, fEnd = src.focusEnd || src.end;
    const hasContext = src.start < fStart || src.end > fEnd;
    let state = {};
    const rows = src.lines.map((line, k) => {
      const n = src.start + k;
      const r = highlightLine(line, lang, state); state = r.state;
      const cls = [added.has(n) ? 'ln-add' : '', n < fStart || n > fEnd ? 'ctx' : ''].join(' ').trim();
      return `<tr class="${cls}"><td class="ln-no">${n}</td><td class="ln-code">${r.html || ' '}</td></tr>`;
    }).join('');
    const addedInFocus = [...added].filter((n) => n >= fStart && n <= fEnd).length;
    const box = h('div', { class: 'snippet' });
    const ctxBtn = hasContext ? h('button', { type: 'button', class: 'btn ghost small-btn', onclick: () => {
      const on = box.classList.toggle('show-ctx');
      ctxBtn.textContent = on ? 'Hide surrounding code' : `Show surrounding code (${src.start}–${src.end})`;
    } }, `Show surrounding code (${src.start}–${src.end})`) : null;
    appendKids(box, [
      h('div', { class: 'snippet-head' },
        h('span', { class: 'mono small', text: `${src.path}:${fStart}–${fEnd}` }),
        addedInFocus ? h('span', { class: 'legend-add', text: `${addedInFocus} line${addedInFocus > 1 ? 's' : ''} added in this PR` }) : h('span', { class: 'muted small', text: 'unchanged in this PR' }),
        ctxBtn),
      h('div', { class: 'code-wrap' }, h('table', { class: 'code-table', html: rows })),
      src.truncated ? h('p', { class: 'muted small', text: 'Truncated — open the diff for the full range.' }) : null,
    ]);
    return box;
  }
  function fieldTable(fields) {
    if (!fields || !fields.length) return null;
    return h('div', { class: 'table-wrap' }, h('table', { class: 'fields' },
      h('thead', null, h('tr', null, h('th', { text: 'Field' }), h('th', { text: 'Type' }), h('th', { text: 'Description' }))),
      h('tbody', null, fields.map((f) => h('tr', { class: f.change ? `row-${f.change}` : '' },
        h('td', null, h('code', { class: 'field-name', text: f.name }), f.required ? h('span', { class: 'req', title: 'required', text: '*' }) : null, f.change && f.change !== 'existing' ? changeBadge(f.change) : null),
        h('td', null, h('code', { class: 'type', text: f.type || '' })),
        h('td', null, richEl('div', f.desc || ''),
          f.values ? h('div', { class: 'enum' }, f.values.map((v) => h('code', { class: 'enum-v', text: v }))) : null,
          f.default !== undefined ? h('div', { class: 'muted small' }, 'default ', h('code', { text: String(f.default) })) : null,
          f.example !== undefined ? h('div', { class: 'muted small' }, 'e.g. ', h('code', { text: typeof f.example === 'string' ? f.example : JSON.stringify(f.example) })) : null))))));
  }
  function sectionHead(id, eyebrow, title, intro) {
    return h('header', { class: 'sec-head' },
      h('div', { class: 'eyebrow', text: eyebrow }),
      h('h2', { id: `${id}-title`, text: title }),
      intro ? richEl('p', intro, 'sec-intro') : null);
  }
  function disclosure(summaryNodes, bodyFn, open) {
    const body = h('div', { class: 'disc-body' });
    let built = false;
    const btn = h('button', { type: 'button', class: 'disc-toggle', 'aria-expanded': 'false' }, h('span', { class: 'caret' }), summaryNodes);
    const wrap = h('div', { class: 'disc' }, btn, body);
    const set = (on) => {
      if (on && !built) { appendKids(body, [bodyFn()]); built = true; }
      body.hidden = !on; btn.setAttribute('aria-expanded', String(on)); wrap.classList.toggle('open', on);
    };
    btn.addEventListener('click', () => set(body.hidden));
    wrap._set = set;
    set(!!open);
    return wrap;
  }

  // ── Graph diagram (layered DAG) ──────────────────────────────────────────
  // direction "TB" (default for flows): ranks are rows, nodes coloured by layer, order within a row
  // chosen by parent barycentre to cut crossings. direction "LR": ranks are columns, optional
  // swimlanes per layer (used for state lifecycles and small flows).
  function measureText(text, size) { return String(text || '').length * size * 0.6; }
  function cubicAt(p0, p1, p2, p3, t) {
    const u = 1 - t;
    const f = (i) => u * u * u * p0[i] + 3 * u * u * t * p1[i] + 3 * u * t * t * p2[i] + t * t * t * p3[i];
    return [f(0), f(1)];
  }
  /* Nudge a label box down (then up) until it clears every box placed so far. */
  function placeLabel(placed, x, y, w, hgt) {
    const hits = (yy) => placed.some((b) => Math.abs(b.x - x) < (b.w + w) / 2 + 4 && Math.abs(b.y - yy) < (b.h + hgt) / 2 + 2);
    for (let k = 0; k < 8; k++) {
      for (const yy of [y + k * 13, y - k * 13]) {
        if (!hits(yy)) { placed.push({ x, y: yy, w, h: hgt }); return yy; }
      }
    }
    placed.push({ x, y, w, h: hgt });
    return y;
  }
  function rankNodes(nodes, edges, byId) {
    const out = {}; nodes.forEach((n) => { out[n.id] = []; });
    edges.forEach((e) => { if (byId[e.from] && byId[e.to]) out[e.from].push(e.to); });
    const back = new Set(); const color = {};
    const dfs = (v) => {
      color[v] = 1;
      out[v].forEach((w) => { if (color[w] === 1) back.add(v + '>' + w); else if (!color[w]) dfs(w); });
      color[v] = 2;
    };
    nodes.forEach((n) => { if (!color[n.id]) dfs(n.id); });
    const indeg = {}; nodes.forEach((n) => { indeg[n.id] = 0; n.rank = 0; });
    const forward = (e) => byId[e.from] && byId[e.to] && e.from !== e.to && !back.has(e.from + '>' + e.to);
    edges.forEach((e) => { if (forward(e)) indeg[e.to]++; });
    const queue = nodes.filter((n) => !indeg[n.id]).map((n) => n.id);
    while (queue.length) {
      const v = queue.shift();
      out[v].forEach((w) => {
        if (back.has(v + '>' + w) || v === w) return;
        byId[w].rank = Math.max(byId[w].rank, byId[v].rank + 1);
        if (--indeg[w] === 0) queue.push(w);
      });
    }
    nodes.forEach((n) => { if (typeof n.col === 'number') n.rank = n.col; });
    return { back, forward };
  }
  function renderGraph(spec) {
    const nodes = (spec.nodes || []).map((n) => ({ ...n }));
    const edges = spec.edges || [];
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    const dir = spec.direction || 'TB';
    const NODE_H = 50;
    nodes.forEach((n) => {
      n.w = Math.min(240, Math.max(120, measureText(n.label, 12.5) + 32, measureText(n.sub, 10.5) + 28));
      n.h = NODE_H;
    });
    const { back } = rankNodes(nodes, edges, byId);
    const isBack = (e) => back.has(e.from + '>' + e.to) || (byId[e.to] && byId[e.from] && byId[e.to].rank < byId[e.from].rank);
    const maxRank = Math.max(0, ...nodes.map((n) => n.rank));
    const rows = Array.from({ length: maxRank + 1 }, (_, r) => nodes.filter((n) => n.rank === r));
    let width, height, lanes = [];
    const backEdges = edges.filter((e) => byId[e.from] && byId[e.to] && e.from !== e.to && isBack(e));

    if (dir === 'TB') {
      const HGAP = 34, VGAP = 70, PAD = 24;
      // Barycentre ordering: two downward sweeps using parents' positions.
      const parents = {}; nodes.forEach((n) => { parents[n.id] = []; });
      edges.forEach((e) => { if (byId[e.from] && byId[e.to] && !isBack(e) && e.from !== e.to) parents[e.to].push(byId[e.from]); });
      const place = () => {
        const rowW = rows.map((row) => row.reduce((a, n) => a + n.w, 0) + HGAP * Math.max(0, row.length - 1));
        width = Math.max(...rowW, 300) + PAD * 2;
        rows.forEach((row, r) => {
          let x = (width - rowW[r]) / 2;
          row.forEach((n) => { n.x = x; n.y = PAD + r * (NODE_H + VGAP); x += n.w + HGAP; });
        });
      };
      place();
      for (let sweep = 0; sweep < 2; sweep++) {
        rows.forEach((row, r) => {
          if (!r) return;
          row.forEach((n, i) => { const ps = parents[n.id]; n._bc = ps.length ? ps.reduce((a, p) => a + p.x + p.w / 2, 0) / ps.length : (n.x + n.w / 2) + i * 0.01; });
          row.sort((a, b) => a._bc - b._bc);
        });
        place();
      }
      // Rows with free space: nudge nodes toward their parents' centre without overlapping.
      rows.forEach((row, r) => {
        if (!r) return;
        let minX = PAD;
        row.forEach((n, i) => {
          const ps = parents[n.id];
          const want = ps.length ? ps.reduce((a, p) => a + p.x + p.w / 2, 0) / ps.length - n.w / 2 : n.x;
          const restW = row.slice(i + 1).reduce((a, m) => a + m.w + HGAP, 0);
          n.x = Math.max(minX, Math.min(want, width - PAD - restW - n.w));
          minX = n.x + n.w + HGAP;
        });
      });
      width += backEdges.length * 22;
      height = PAD * 2 + (maxRank + 1) * NODE_H + maxRank * VGAP;
    } else {
      const HGAP = 80, VGAP = 16, LANE_PAD = 16, TOP = 14;
      const useLanes = spec.lanes !== false && nodes.some((n) => n.layer);
      const LABEL_W = useLanes ? 132 : 0;
      const colW = rows.map((row) => Math.max(120, ...row.map((n) => n.w)));
      const colX = []; let x = LABEL_W + 20;
      colW.forEach((w, r) => { colX[r] = x; x += w + HGAP; });
      width = x - HGAP + 24;
      const laneIds = useLanes ? LAYERS.map((l) => l.id).filter((id) => nodes.some((n) => n.layer === id)) : ['_'];
      nodes.forEach((n) => { if (useLanes && !laneIds.includes(n.layer || '_other')) laneIds.push(n.layer || '_other'); });
      const laneOf = (n) => (useLanes ? (n.layer || '_other') : '_');
      let y = TOP;
      laneIds.forEach((lane) => {
        const cells = {};
        nodes.filter((n) => laneOf(n) === lane).forEach((n) => { (cells[n.rank] = cells[n.rank] || []).push(n); });
        const depth = Math.max(1, ...Object.values(cells).map((c) => c.length));
        const laneH = depth * (NODE_H + VGAP) - VGAP + LANE_PAD * 2;
        Object.entries(cells).forEach(([r, list]) => {
          const stackH = list.length * (NODE_H + VGAP) - VGAP;
          list.forEach((n, k) => { n.x = colX[r] + (colW[r] - n.w) / 2; n.y = y + (laneH - stackH) / 2 + k * (NODE_H + VGAP); });
        });
        if (useLanes) lanes.push({ id: lane, y, height: laneH });
        y += laneH + 6;
      });
      height = y + 10 + backEdges.length * 20;
    }

    const svg = s('svg', { class: 'diagram graph', viewBox: `0 0 ${width} ${height}`, width, height, role: 'img', 'aria-label': spec.title || 'Flow diagram' });
    svg.appendChild(arrowDefs());
    lanes.forEach((lane, i) => {
      const lc = layerColor(lane.id);
      svg.appendChild(s('rect', { class: `lane lc-${lc}${i % 2 ? ' alt' : ''}`, x: 0, y: lane.y, width, height: lane.height, rx: 8 }));
      svg.appendChild(s('text', { class: `lane-label lc-${lc}`, x: 14, y: lane.y + 22 }, layerLabel(lane.id)));
    });
    const edgeLayer = s('g', { class: 'edges' });
    const nodeLayer = s('g', { class: 'nodes' });
    const labelLayer = s('g', { class: 'edge-labels' });
    svg.append(edgeLayer, nodeLayer, labelLayer);

    let backIndex = 0;
    const placedLabels = nodes.map((n) => ({ x: n.x + n.w / 2, y: n.y + n.h / 2, w: n.w, h: n.h }));
    const edgeEls = edges.map((e) => {
      const a = byId[e.from], b = byId[e.to];
      if (!a || !b) return null;
      let p0, p1, p2, p3;
      if (a === b) {
        p0 = [a.x + a.w, a.y + 14]; p1 = [a.x + a.w + 46, a.y - 10]; p2 = [a.x + a.w + 46, a.y + a.h + 10]; p3 = [a.x + a.w, a.y + a.h - 14];
      } else if (isBack(e)) {
        const k = backIndex++;
        if (dir === 'TB') {
          const gx = width - 14 - k * 22;
          p0 = [a.x + a.w, a.y + a.h / 2]; p1 = [gx, a.y + a.h / 2]; p2 = [gx, b.y + b.h / 2]; p3 = [b.x + b.w, b.y + b.h / 2];
        } else if (a.y + a.h <= b.y || a.y >= b.y + b.h) {
          // Arc from the source's left side into the top (or bottom) of the earlier node.
          const above = a.y + a.h <= b.y;
          p0 = [a.x, a.y + a.h / 2]; p3 = [b.x + b.w / 2 + (k % 2 ? -14 : 14), above ? b.y : b.y + b.h];
          p1 = [a.x - 60, a.y + a.h / 2]; p2 = [p3[0], p3[1] + (above ? -50 : 50)];
        } else {
          const gy = height - 12 - k * 20;
          p0 = [a.x + a.w / 2, a.y + a.h]; p1 = [a.x + a.w / 2, gy]; p2 = [b.x + b.w / 2, gy]; p3 = [b.x + b.w / 2, b.y + b.h];
        }
      } else if (a.rank === b.rank) {
        const right = b.x > a.x;
        if (dir === 'TB') {
          p0 = [right ? a.x + a.w : a.x, a.y + a.h / 2]; p3 = [right ? b.x : b.x + b.w, b.y + b.h / 2];
          p1 = [(p0[0] + p3[0]) / 2, p0[1]]; p2 = [(p0[0] + p3[0]) / 2, p3[1]];
        } else {
          const down = b.y > a.y;
          p0 = [a.x + a.w / 2, down ? a.y + a.h : a.y]; p3 = [b.x + b.w / 2, down ? b.y : b.y + b.h];
          p1 = [p0[0], (p0[1] + p3[1]) / 2]; p2 = [p3[0], (p0[1] + p3[1]) / 2];
        }
      } else if (dir === 'TB') {
        p0 = [a.x + a.w / 2, a.y + a.h]; p3 = [b.x + b.w / 2, b.y];
        const dy = Math.max(28, (p3[1] - p0[1]) / 2);
        p1 = [p0[0], p0[1] + dy]; p2 = [p3[0], p3[1] - dy];
      } else {
        p0 = [a.x + a.w, a.y + a.h / 2]; p3 = [b.x, b.y + b.h / 2];
        const dx = Math.max(30, (p3[0] - p0[0]) / 2);
        p1 = [p0[0] + dx, p0[1]]; p2 = [p3[0] - dx, p3[1]];
      }
      const kind = e.kind || (isBack(e) ? 'retry' : 'call');
      const d = `M${p0[0]},${p0[1]} C${p1[0]},${p1[1]} ${p2[0]},${p2[1]} ${p3[0]},${p3[1]}`;
      const path = s('path', { class: `edge ek-${kind}`, d, 'marker-end': `url(#arrow-${kind})` });
      edgeLayer.appendChild(path);
      // Fan-outs from one node crowd at the midpoint; label those nearer the target.
      const fanOut = edges.filter((x) => x.from === e.from).length > 3 && !isBack(e);
      const [mx, my0] = cubicAt(p0, p1, p2, p3, fanOut ? 0.72 : 0.5);
      const textW = measureText(e.label, 11);
      const my = e.label || e.step !== undefined ? placeLabel(placedLabels, mx, my0 - 4, textW + (e.step !== undefined ? 26 : 0), 14) + 4 : my0;
      const g = s('g', { class: 'edge-label' });
      if (e.step !== undefined) {
        const cx = e.label ? mx - textW / 2 - 12 : mx;
        g.appendChild(s('circle', { class: 'step-dot', cx, cy: my - 4, r: 9 }));
        g.appendChild(s('text', { class: 'step-num', x: cx, y: my - 0.5 }, String(e.step)));
      }
      if (e.label) g.appendChild(s('text', { class: 'edge-text', x: mx, y: my }, e.label));
      labelLayer.appendChild(g);
      return { e, path, g };
    });

    nodes.forEach((n) => {
      const lc = layerColor(n.layer);
      const clickable = n.symbol || n.ref;
      const g = s('g', { class: `node${n.layer ? ` lc-${lc}` : ''} shape-${n.shape || 'box'}${n.cls ? ' ' + n.cls : ''}${clickable ? ' clickable' : ''}`, transform: `translate(${n.x},${n.y})`, tabindex: clickable ? 0 : null, role: clickable ? 'button' : null });
      if (n.shape === 'db') {
        g.appendChild(s('path', { class: 'node-box', d: `M0,8 Q0,0 ${n.w / 2},0 Q${n.w},0 ${n.w},8 L${n.w},${n.h - 8} Q${n.w},${n.h} ${n.w / 2},${n.h} Q0,${n.h} 0,${n.h - 8} Z` }));
        g.appendChild(s('path', { class: 'node-rim', d: `M0,8 Q0,16 ${n.w / 2},16 Q${n.w},16 ${n.w},8` }));
      } else {
        g.appendChild(s('rect', { class: 'node-box', width: n.w, height: n.h, rx: n.shape === 'pill' ? n.h / 2 : 8 }));
      }
      if (n.change) g.appendChild(s('circle', { class: `node-chg chg-dot-${n.change}`, cx: n.w - 9, cy: 9, r: 4 }));
      const textY = n.shape === 'db' ? 6 : 0;
      g.appendChild(s('text', { class: 'node-label', x: n.w / 2, y: (n.sub ? 21 : 30) + textY }, n.label));
      if (n.sub) g.appendChild(s('text', { class: 'node-sub', x: n.w / 2, y: 37 + textY / 2 }, n.sub));
      if (n.tip) g.appendChild(s('title', null, n.tip));
      const connected = edgeEls.filter((x) => x && (x.e.from === n.id || x.e.to === n.id));
      g.addEventListener('mouseenter', () => { svg.classList.add('focusing'); g.classList.add('lit'); connected.forEach((x) => { x.path.classList.add('lit'); x.g.classList.add('lit'); }); });
      g.addEventListener('mouseleave', () => { svg.classList.remove('focusing'); g.classList.remove('lit'); connected.forEach((x) => { x.path.classList.remove('lit'); x.g.classList.remove('lit'); }); });
      if (clickable) {
        const open = () => (n.symbol ? openSymbol(n.symbol) : openRef(n.ref));
        g.addEventListener('click', open);
        g.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); open(); } });
      }
      nodeLayer.appendChild(g);
    });
    const usedLayers = dir === 'TB' ? LAYERS.filter((l) => nodes.some((n) => n.layer === l.id)) : [];
    return h('div', { class: 'graph-wrap' },
      usedLayers.length ? h('div', { class: 'layer-legend' }, usedLayers.map((l) => h('span', { class: `ll-item lc-${l.color}` }, h('span', { class: 'swatch' }), l.label))) : null,
      h('div', { class: 'diagram-scroll' }, svg));
  }
  function arrowDefs() {
    const defs = s('defs');
    ['call', 'data', 'async', 'external', 'write', 'return', 'retry', 'config', 'trigger'].forEach((k) => {
      const m = s('marker', { id: `arrow-${k}`, viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' });
      m.appendChild(s('path', { class: `arrowhead ek-${k}`, d: k === 'return' || k === 'async' ? 'M1,1 L9,5 L1,9' : 'M0,0 L10,5 L0,10 z' }));
      defs.appendChild(m);
    });
    return defs;
  }

  // ── Flowchart: classic top-down process chart ────────────────────────────
  // Nodes without `side` form the main spine, in the order listed. A node with side "right"/"left"
  // sits on the same row as the node that branches to it (outcomes, early exits). `groups` draw a
  // dashed box around a run of spine nodes (loops). Edges going back up the spine route on the left.
  function wrapLines(text, perLine) {
    const words = String(text || '').split(/\s+/);
    const lines = []; let cur = '';
    words.forEach((w) => { if ((cur + ' ' + w).trim().length > perLine && cur) { lines.push(cur); cur = w; } else cur = (cur + ' ' + w).trim(); });
    if (cur) lines.push(cur);
    return lines.length || 1;
  }
  function renderFlowchart(spec) {
    const nodes = (spec.nodes || []).map((n) => ({ ...n }));
    const edges = spec.edges || [];
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    const LINE = 17, VGAP = 34, SIDE_GAP = 64, PAD = 24, LOOP_PAD = 16;
    const spine = nodes.filter((n) => !n.side);
    nodes.forEach((n) => {
      const kind = n.kind || 'step';
      if (kind === 'decision') {
        n.w = 300; const lines = wrapLines(n.label, 24);
        n.h = Math.max(92, lines * LINE + 56);
      } else if (kind === 'start' || kind === 'end') {
        n.w = n.side ? 230 : 280; const lines = wrapLines(n.label, n.side ? 26 : 32);
        n.h = Math.max(44, lines * LINE + 22 + (n.sub ? 15 : 0));
      } else {
        n.w = 300; const lines = wrapLines(n.label, 36);
        n.h = Math.max(50, lines * LINE + 24 + (n.sub ? 16 : 0));
      }
    });
    spine.forEach((n, i) => { n.row = i; });
    // Side nodes take the row of their first incoming edge; chained side nodes move one column out.
    const sideCol = {};
    nodes.filter((n) => n.side).forEach((n) => {
      const inc = edges.find((e) => e.to === n.id && byId[e.from]);
      const src = inc ? byId[inc.from] : spine[0];
      n.row = src.row ?? 0;
      n.col = src.side ? (src.col || 1) + 1 : 1;
      const key = `${n.side}:${n.row}:${n.col}`;
      while (sideCol[`${n.side}:${n.row}:${n.col}`]) n.col += 1;
      sideCol[`${n.side}:${n.row}:${n.col}`] = true;
      void key;
    });
    const rows = Math.max(0, ...nodes.map((n) => n.row)) + 1;
    const rowH = Array.from({ length: rows }, (_, r) => Math.max(40, ...nodes.filter((n) => n.row === r).map((n) => n.h)));
    const rowY = []; let y = PAD + 22;
    rowH.forEach((hgt, r) => { rowY[r] = y; y += hgt + VGAP; });
    const SPINE_W = 300;
    const leftCols = Math.max(0, ...nodes.filter((n) => n.side === 'left').map((n) => n.col));
    const rightCols = Math.max(0, ...nodes.filter((n) => n.side === 'right').map((n) => n.col));
    const backEdges = edges.filter((e) => byId[e.from] && byId[e.to] && !byId[e.from].side && !byId[e.to].side && byId[e.to].row <= byId[e.from].row);
    const BACK_W = backEdges.length ? 34 + backEdges.length * 16 : 0;
    const spineX = PAD + BACK_W + leftCols * (240 + SIDE_GAP);
    const width = spineX + SPINE_W + rightCols * (230 + SIDE_GAP) + PAD;
    const height = y - VGAP + PAD;
    nodes.forEach((n) => {
      const cy = rowY[n.row] + rowH[n.row] / 2;
      if (!n.side) n.x = spineX + (SPINE_W - n.w) / 2;
      else if (n.side === 'right') n.x = spineX + SPINE_W + SIDE_GAP + (n.col - 1) * (230 + SIDE_GAP);
      else n.x = spineX - SIDE_GAP - n.w - (n.col - 1) * (240 + SIDE_GAP);
      n.y = cy - n.h / 2;
    });

    const svg = s('svg', { class: 'diagram flowchart', viewBox: `0 0 ${width} ${height}`, width, height, role: 'img', 'aria-label': spec.title || 'Flowchart' });
    svg.style.minWidth = `${Math.round(width * 0.62)}px`;
    svg.appendChild(arrowDefs());
    (spec.groups || []).forEach((g) => {
      const a = byId[g.from], b = byId[g.to];
      if (!a || !b) return;
      const inRows = nodes.filter((n) => n.row >= a.row && n.row <= b.row);
      const x1 = Math.min(...inRows.map((n) => n.x)) - LOOP_PAD - (backEdges.length ? 6 : 0);
      const x2 = Math.max(...inRows.map((n) => n.x + n.w)) + LOOP_PAD;
      const y1 = rowY[a.row] - LOOP_PAD - 8, y2 = rowY[b.row] + rowH[b.row] + LOOP_PAD;
      svg.appendChild(s('rect', { class: 'fc-loop', x: x1, y: y1, width: x2 - x1, height: y2 - y1, rx: 12 }));
      svg.appendChild(s('text', { class: 'fc-loop-label', x: x2 - 12, y: y1 + 15, 'text-anchor': 'end' }, g.label || 'loop'));
    });
    const edgeLayer = s('g'); const nodeLayer = s('g'); const labelLayer = s('g');
    svg.append(edgeLayer, nodeLayer, labelLayer);
    let backK = 0;
    const edgeEls = edges.map((e) => {
      const a = byId[e.from], b = byId[e.to];
      if (!a || !b) return null;
      const acx = a.x + a.w / 2, acy = a.y + a.h / 2, bcx = b.x + b.w / 2, bcy = b.y + b.h / 2;
      let d, lx, ly, anchor = 'start';
      if (!a.side && !b.side && b.row > a.row) {
        d = `M${acx},${a.y + a.h} L${bcx},${b.y}`;
        lx = acx + 8; ly = a.y + a.h + 15;
        if (b.row > a.row + 1) {
          // Skips rows: run down the spine's right edge so it doesn't cross intermediate nodes.
          const gx = spineX + SPINE_W + 14;
          d = `M${a.x + a.w},${acy} L${gx},${acy} L${gx},${bcy} L${b.x + b.w},${bcy}`;
          lx = gx + 4; ly = acy - 6;
        }
      } else if (!a.side && !b.side) {
        const gx = spineX - 22 - backK++ * 16;
        d = `M${a.x},${acy} L${gx},${acy} L${gx},${bcy} L${b.x},${bcy}`;
        lx = gx - 4; ly = (acy + bcy) / 2; anchor = 'end';
      } else if (b.side && a.row === b.row) {
        const right = b.x > a.x;
        const sx = right ? a.x + a.w : a.x, tx = right ? b.x : b.x + b.w;
        d = `M${sx},${acy} L${tx},${bcy}`;
        lx = sx + (right ? 8 : -8); ly = acy - 7; anchor = right ? 'start' : 'end';
      } else {
        d = `M${acx},${a.y + a.h} C${acx},${bcy} ${acx},${bcy} ${b.x > acx ? b.x : b.x + b.w},${bcy}`;
        lx = acx + 6; ly = a.y + a.h + 14;
      }
      const kind = e.kind || (backEdges.includes(e) ? 'retry' : 'call');
      const path = s('path', { class: `edge fc-edge ek-${kind}`, d, 'marker-end': `url(#arrow-${kind})` });
      edgeLayer.appendChild(path);
      const g = s('g', { class: 'edge-label' });
      if (e.label) g.appendChild(s('text', { class: `fc-edge-text${/^(yes|no)$/i.test(e.label) ? ` fc-${e.label.toLowerCase()}` : ''}`, x: lx, y: ly, 'text-anchor': anchor }, e.label));
      labelLayer.appendChild(g);
      return { e, path, g };
    });
    nodes.forEach((n) => {
      const kind = n.kind || 'step';
      const clickable = n.symbol || n.ref;
      const g = s('g', { class: `fc-node fk-${kind}${n.tone ? ` tone-${n.tone}` : ''}${n.layer ? ` lc-${layerColor(n.layer)}` : ''}${clickable ? ' clickable' : ''}`, transform: `translate(${n.x},${n.y})`, tabindex: clickable ? 0 : null, role: clickable ? 'button' : null });
      if (kind === 'decision') {
        g.appendChild(s('path', { class: 'fc-shape', d: `M${n.w / 2},0 L${n.w},${n.h / 2} L${n.w / 2},${n.h} L0,${n.h / 2} Z` }));
      } else {
        g.appendChild(s('rect', { class: 'fc-shape', width: n.w, height: n.h, rx: kind === 'step' ? 8 : n.h / 2 > 24 ? 22 : n.h / 2 }));
        if (kind === 'step' && n.layer) g.appendChild(s('rect', { class: 'fc-layer-bar', width: 5, height: n.h - 12, x: 6, y: 6, rx: 2 }));
      }
      const inset = kind === 'decision' ? n.w * 0.2 : 14;
      const fo = s('foreignObject', { x: inset, y: 0, width: n.w - inset * 2, height: n.h });
      fo.appendChild(h('div', { class: 'fc-text' },
        h('div', { class: 'fc-label', html: rich(n.label) }),
        n.sub ? h('div', { class: 'fc-sub', html: rich(n.sub) }) : null));
      g.appendChild(fo);
      if (n.change) g.appendChild(s('circle', { class: `node-chg chg-dot-${n.change}`, cx: kind === 'decision' ? n.w / 2 + 14 : n.w - 9, cy: kind === 'decision' ? 12 : 9, r: 4 }));
      if (n.tip) g.appendChild(s('title', null, n.tip));
      const connected = edgeEls.filter((x) => x && (x.e.from === n.id || x.e.to === n.id));
      g.addEventListener('mouseenter', () => { svg.classList.add('focusing'); g.classList.add('lit'); connected.forEach((x) => { x.path.classList.add('lit'); x.g.classList.add('lit'); }); });
      g.addEventListener('mouseleave', () => { svg.classList.remove('focusing'); g.classList.remove('lit'); connected.forEach((x) => { x.path.classList.remove('lit'); x.g.classList.remove('lit'); }); });
      if (clickable) {
        const open = () => (n.symbol ? openSymbol(n.symbol) : openRef(n.ref));
        g.addEventListener('click', open);
        g.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); open(); } });
      }
      nodeLayer.appendChild(g);
    });
    const usedLayers = LAYERS.filter((l) => nodes.some((n) => n.layer === l.id));
    return h('div', { class: 'graph-wrap' },
      h('div', { class: 'layer-legend' },
        h('span', { class: 'll-item' }, h('span', { class: 'shape-key sk-step' }), 'step'),
        h('span', { class: 'll-item' }, h('span', { class: 'shape-key sk-decision' }), 'decision'),
        h('span', { class: 'll-item' }, h('span', { class: 'shape-key sk-end' }), 'outcome'),
        usedLayers.map((l) => h('span', { class: `ll-item lc-${l.color}` }, h('span', { class: 'swatch' }), l.label))),
      h('div', { class: 'diagram-scroll' }, svg));
  }

  // ── Sequence diagram ─────────────────────────────────────────────────────
  function renderSequence(spec) {
    const parts = spec.participants || [];
    const msgs = spec.messages || [];
    const HEAD_H = 52, TOP = 12, ROW = 40;
    let x = 16;
    parts.forEach((p) => { p.w = Math.max(132, measureText(p.label, 13) + 28, measureText(p.sub, 11) + 28); p.cx = x + p.w / 2; x += p.w + 34; });
    const width = Math.max(x, 400);
    const pos = Object.fromEntries(parts.map((p) => [p.id, p]));
    let y = TOP + HEAD_H + 26;
    const rows = msgs.map((m) => {
      const isSelf = m.from && m.from === m.to;
      const rowH = m.kind === 'divider' ? 34 : m.kind === 'note' ? 18 + Math.ceil(String(m.label).length / 48) * 15 : isSelf ? 52 : ROW;
      const row = { m, y, rowH };
      y += rowH;
      return row;
    });
    const height = y + 18;
    const svg = s('svg', { class: 'diagram sequence', viewBox: `0 0 ${width} ${height}`, width, height, role: 'img', 'aria-label': spec.title || 'Sequence diagram' });
    svg.appendChild(arrowDefs());
    parts.forEach((p) => {
      svg.appendChild(s('line', { class: 'lifeline', x1: p.cx, y1: TOP + HEAD_H, x2: p.cx, y2: height - 6 }));
    });
    let step = 0;
    rows.forEach(({ m, y: ry, rowH }) => {
      const g = s('g', { class: `msg mk-${m.kind || 'call'}${m.symbol || m.ref ? ' clickable' : ''}` });
      if (m.kind === 'divider') {
        g.appendChild(s('rect', { class: 'seq-divider', x: 6, y: ry + 4, width: width - 12, height: rowH - 8, rx: 6 }));
        g.appendChild(s('text', { class: 'seq-divider-text', x: 16, y: ry + rowH / 2 + 4 }, m.label));
      } else if (m.kind === 'note') {
        const a = pos[m.from] || parts[0], b = pos[m.to] || a;
        const x1 = Math.min(a.cx, b.cx) - 60, x2 = Math.max(a.cx, b.cx) + 60;
        const fo = s('foreignObject', { x: x1, y: ry + 2, width: x2 - x1, height: rowH - 4 });
        fo.appendChild(h('div', { class: 'seq-note', html: rich(m.label) }));
        g.appendChild(fo);
      } else {
        const a = pos[m.from], b = pos[m.to];
        if (!a || !b) return;
        step += 1;
        const kind = m.kind || 'call';
        const ay = ry + rowH - 12;
        if (a === b) {
          g.appendChild(s('path', { class: `edge ek-${kind}`, d: `M${a.cx},${ay - 14} h34 v20 h-30`, 'marker-end': `url(#arrow-${kind})` }));
          g.appendChild(s('text', { class: 'msg-text start', x: a.cx + 42, y: ay - 2 }, m.label));
        } else {
          const dir = b.cx > a.cx ? 1 : -1;
          g.appendChild(s('line', { class: `edge ek-${kind}`, x1: a.cx + dir * 3, y1: ay, x2: b.cx - dir * 4, y2: ay, 'marker-end': `url(#arrow-${kind})` }));
          g.appendChild(s('text', { class: 'msg-text', x: (a.cx + b.cx) / 2, y: ay - 8 }, m.label));
        }
        g.appendChild(s('circle', { class: 'step-dot', cx: a.cx, cy: ay, r: 8 }));
        g.appendChild(s('text', { class: 'step-num', x: a.cx, y: ay + 3.5 }, String(step)));
        if (m.symbol || m.ref) {
          g.setAttribute('tabindex', '0');
          const open = () => (m.symbol ? openSymbol(m.symbol) : openRef(m.ref));
          g.addEventListener('click', open);
          g.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') open(); });
        }
        if (m.tip) g.appendChild(s('title', null, m.tip));
      }
      svg.appendChild(g);
    });
    parts.forEach((p) => {
      const lc = layerColor(p.layer);
      const g = s('g', { class: `node seq-head lc-${lc}${p.symbol ? ' clickable' : ''}`, transform: `translate(${p.cx - p.w / 2},${TOP})` });
      g.appendChild(s('rect', { class: 'node-box', width: p.w, height: HEAD_H, rx: 8 }));
      g.appendChild(s('text', { class: 'node-label', x: p.w / 2, y: p.sub ? 22 : 31 }, p.label));
      if (p.sub) g.appendChild(s('text', { class: 'node-sub', x: p.w / 2, y: 39 }, p.sub));
      if (p.symbol) g.addEventListener('click', () => openSymbol(p.symbol));
      svg.appendChild(g);
    });
    return h('div', { class: 'diagram-scroll' }, svg);
  }

  // ── Drawer: docked side panel on wide screens (the page stays visible and usable beside it),
  //    overlay with a scrim on narrow screens. Resizable by dragging its left edge. ──────────
  const drawer = document.getElementById('drawer');
  const drawerBody = document.getElementById('drawer-body');
  const drawerCrumb = document.getElementById('drawer-crumb');
  const drawerBack = document.getElementById('drawer-back');
  const drawerWide = document.getElementById('drawer-wide');
  const drawerResize = document.getElementById('drawer-resize');
  const scrim = document.getElementById('scrim');
  const backStack = [];
  const DOCK_MIN_VIEWPORT = 1000;
  const canDock = () => window.innerWidth >= DOCK_MIN_VIEWPORT;
  const clampDrawer = (w) => Math.round(Math.max(380, Math.min(w, window.innerWidth - 360)));
  let drawerW = parseInt(store.get('drawerW') || '0', 10) || Math.round(window.innerWidth * 0.42);
  const isWide = () => drawerW >= window.innerWidth * 0.58;
  function applyDrawerLayout() {
    const docked = !drawer.hidden && canDock();
    const w = canDock() ? clampDrawer(drawerW) : Math.min(window.innerWidth, 640);
    const root = document.documentElement.style;
    root.setProperty('--drawer-w', `${w}px`);
    const bar = document.getElementById('topbar');
    root.setProperty('--topbar-real', `${bar ? bar.offsetHeight : 64}px`);
    document.body.classList.toggle('drawer-docked', docked);
    scrim.hidden = drawer.hidden || canDock();
    drawerWide.textContent = isWide() ? '⇥' : '⇤';
    drawerWide.title = isWide() ? 'Make panel narrower' : 'Make panel wider';
    drawerWide.setAttribute('aria-label', drawerWide.title);
  }
  window.addEventListener('resize', applyDrawerLayout);
  drawerWide.addEventListener('click', () => {
    drawerW = Math.round(window.innerWidth * (isWide() ? 0.42 : 0.66));
    store.set('drawerW', String(drawerW));
    applyDrawerLayout();
  });
  drawerResize.addEventListener('pointerdown', (e) => {
    if (!canDock()) return;
    e.preventDefault();
    drawerResize.setPointerCapture(e.pointerId);
    document.body.classList.add('resizing');
    const move = (ev) => { drawerW = clampDrawer(window.innerWidth - ev.clientX); applyDrawerLayout(); };
    const up = () => {
      document.body.classList.remove('resizing');
      drawerResize.removeEventListener('pointermove', move);
      drawerResize.removeEventListener('pointerup', up);
      store.set('drawerW', String(drawerW));
    };
    drawerResize.addEventListener('pointermove', move);
    drawerResize.addEventListener('pointerup', up);
  });
  drawerResize.addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    drawerW = clampDrawer(drawerW + (e.key === 'ArrowLeft' ? 40 : -40));
    store.set('drawerW', String(drawerW));
    applyDrawerLayout();
  });
  function showDrawer(entry, push = true) {
    if (push) backStack.push(entry);
    drawerBody.innerHTML = '';
    drawerCrumb.textContent = entry.crumb;
    appendKids(drawerBody, [entry.build()]);
    drawer.hidden = false;
    drawerBack.hidden = backStack.length < 2;
    drawerBody.scrollTop = 0;
    applyDrawerLayout();
  }
  function closeDrawer() { drawer.hidden = true; backStack.length = 0; applyDrawerLayout(); }
  /* Jumping to the diff keeps a docked panel open; an overlay panel would hide the target. */
  function leaveDrawerFor(fn) { if (!canDock()) closeDrawer(); fn(); }
  drawerBack.addEventListener('click', () => { backStack.pop(); const prev = backStack[backStack.length - 1]; if (prev) showDrawer(prev, false); });
  document.getElementById('drawer-close').addEventListener('click', closeDrawer);
  scrim.addEventListener('click', closeDrawer);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !drawer.hidden) closeDrawer(); });

  function openSymbol(id) {
    const sym = SYM[id];
    if (!sym) return;
    showDrawer({
      crumb: `${layerLabel(sym.layer)} / ${sym.file ? sym.file.split('/').pop() : 'external'}`,
      build: () => {
        const callers = CALLED_BY[id] || [];
        const inDiff = sym.file && DIFF_BY_PATH[sym.file];
        const refStart = refParts(sym.ref);
        return h('div', { class: 'detail' },
          h('div', { class: 'detail-kicker' }, h('span', { class: 'kind', text: sym.kind || 'symbol' }), changeBadge(sym.change), tagChips(sym.tags)),
          h('h3', { class: 'detail-title mono', text: sym.name }),
          sym.file ? h('div', { class: 'mono small muted' }, sym.file, sym.ref ? ` · lines ${refStart.start}–${refStart.end}` : '') : null,
          sym.signature ? codeBlock(sym.signature, langOf(sym.file || '') || 'python') : null,
          sym.summary ? richEl('p', sym.summary, 'detail-text') : null,
          (sym.notes || []).length ? h('ul', { class: 'notes' }, sym.notes.map((n) => richEl('li', n))) : null,
          (sym.calls || []).length ? h('div', { class: 'rel' }, h('div', { class: 'label', text: 'Calls' }), h('div', { class: 'chips' }, sym.calls.map((c) => symButton(c, { compact: true })))) : null,
          callers.length ? h('div', { class: 'rel' }, h('div', { class: 'label', text: 'Called by' }), h('div', { class: 'chips' }, callers.map((c) => symButton(c, { compact: true })))) : null,
          sym.ref ? snippet(sym.ref) : null,
          inDiff ? h('button', { type: 'button', class: 'btn', onclick: () => leaveDrawerFor(() => revealDiff(sym.file, refStart && refStart.start)) }, 'Show in diff →') : null);
      },
    });
  }
  function openRef(ref) {
    const p = refParts(ref);
    showDrawer({
      crumb: p ? p.path : ref,
      build: () => h('div', { class: 'detail' },
        h('h3', { class: 'detail-title mono', text: shortRef(ref) }),
        snippet(ref),
        p && DIFF_BY_PATH[p.path] ? h('button', { type: 'button', class: 'btn', onclick: () => leaveDrawerFor(() => revealDiff(p.path, p.start)) }, 'Show in diff →') : null),
    });
  }

  // ── Header & navigation ──────────────────────────────────────────────────
  function renderTopbar() {
    const bar = document.getElementById('topbar');
    const sum = S.summary || {};
    const state = M.isDraft ? 'Draft' : (M.state || '').toLowerCase();
    const search = h('input', { id: 'atlas-search', type: 'search', class: 'search', placeholder: 'Find a function, file, or field…', autocomplete: 'off', 'aria-label': 'Search symbols and files' });
    const results = h('div', { class: 'search-results', hidden: true, role: 'listbox' });
    search.addEventListener('input', () => runSearch(search.value, results));
    search.addEventListener('keydown', (e) => { if (e.key === 'Enter') { const first = results.querySelector('button'); if (first) first.click(); } });
    document.addEventListener('click', (e) => { if (!results.contains(e.target) && e.target !== search) results.hidden = true; });
    const themeBtn = h('button', { type: 'button', class: 'icon-btn', id: 'theme-btn', title: 'Theme' });
    const themes = ['system', 'light', 'dark'];
    const applyTheme = (t) => {
      if (t === 'system') document.documentElement.removeAttribute('data-theme'); else document.documentElement.setAttribute('data-theme', t);
      themeBtn.textContent = t === 'dark' ? '☾' : t === 'light' ? '☀' : '◐';
      themeBtn.title = `Theme: ${t}`;
    };
    let theme = store.get('theme') || 'system';
    applyTheme(theme);
    themeBtn.addEventListener('click', () => { theme = themes[(themes.indexOf(theme) + 1) % 3]; store.set('theme', theme); applyTheme(theme); });

    appendKids(bar, h('div', { class: 'topbar-inner' },
      h('div', { class: 'brand' },
        h('span', { class: 'brand-mark', text: 'PR' }),
        h('div', { class: 'brand-text' },
          h('div', { class: 'brand-kicker' }, h('span', { class: 'mono', text: `#${M.number}` }), h('span', { class: `state st-${slug(state)}`, text: state || 'unknown' }),
            h('span', { class: 'mono branch', text: `${M.head} → ${M.base}` })),
          h('h1', { class: 'pr-title', text: sum.short_name ? sum.short_name : M.title }))),
      h('div', { class: 'top-tools' },
        h('div', { class: 'stat-inline mono' },
          h('span', { class: 'add', text: `+${M.additions ?? '?'}` }), h('span', { class: 'del', text: `−${M.deletions ?? '?'}` }),
          h('span', { class: 'muted', text: `${M.changedFiles ?? DIFF.length} files` })),
        h('div', { class: 'search-box' }, search, results),
        themeBtn,
        M.url ? h('a', { class: 'icon-btn gh', href: M.url, target: '_blank', rel: 'noopener', title: 'Open on GitHub', text: '↗' }) : null)));
  }
  function runSearch(q, results) {
    results.innerHTML = '';
    q = q.trim().toLowerCase();
    if (q.length < 2) { results.hidden = true; return; }
    const hits = [];
    Object.values(SYM).forEach((sym) => { if ((sym.name + ' ' + (sym.file || '')).toLowerCase().includes(q)) hits.push({ label: sym.name, sub: sym.file || layerLabel(sym.layer), go: () => openSymbol(sym.id) }); });
    DIFF.forEach((f) => { if (f.path.toLowerCase().includes(q)) hits.push({ label: f.path.split('/').pop(), sub: `${f.path} · diff`, go: () => revealDiff(f.path) }); });
    ((S.data_model && S.data_model.entities) || []).forEach((en) => (en.fields || []).forEach((f) => {
      if (f.name.toLowerCase().includes(q)) hits.push({ label: f.name, sub: `field · ${en.name}`, go: () => openEntity(en.id) });
    }));
    hits.slice(0, 12).forEach((hit) => results.appendChild(h('button', { type: 'button', role: 'option', onclick: () => { results.hidden = true; hit.go(); } },
      h('span', { class: 'mono', text: hit.label }), h('span', { class: 'muted small', text: hit.sub }))));
    if (!hits.length) results.appendChild(h('div', { class: 'muted small empty', text: 'No matches' }));
    results.hidden = false;
  }
  function scrollToId(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
    el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
  }

  // ── Sections ─────────────────────────────────────────────────────────────
  const SECTIONS = [];
  function addSection(id, navLabel, node, count) {
    if (!node) return;
    SECTIONS.push({ id, navLabel, count });
    node.id = id;
    node.classList.add('section');
    document.getElementById('main').appendChild(node);
  }

  function issuesBanner() {
    const issues = D.issues || {};
    const errs = issues.errors || [];
    if (!errs.length) return null;
    return h('div', { class: 'banner banner-error', role: 'alert' },
      h('strong', { text: `${errs.length} spec problem${errs.length > 1 ? 's' : ''} — parts of this page may be wrong or missing.` }),
      h('ul', null, errs.slice(0, 8).map((e) => h('li', { class: 'mono small', text: e }))),
      errs.length > 8 ? h('div', { class: 'small', text: `…and ${errs.length - 8} more (see build output).` }) : null);
  }

  function renderOverview() {
    const sum = S.summary || {};
    const counts = {};
    DIFF.forEach((f) => {
      const layer = guessLayer(f.path) || '_other';
      counts[layer] = counts[layer] || { add: 0, del: 0, files: 0 };
      counts[layer].add += f.additions; counts[layer].del += f.deletions; counts[layer].files += 1;
    });
    const order = LAYERS.map((l) => l.id).filter((id) => counts[id]).concat(counts._other ? ['_other'] : []);
    const total = order.reduce((a, id) => a + counts[id].add + counts[id].del, 0) || 1;
    const bar = h('div', { class: 'footprint-bar', role: 'img', 'aria-label': 'Changed lines by layer' },
      order.map((id) => h('span', { class: `seg lc-${id === '_other' ? 'slate' : layerColor(id)}`, style: `flex-grow:${counts[id].add + counts[id].del}`, title: `${layerLabel(id === '_other' ? 'Other' : id)}: +${counts[id].add} −${counts[id].del}` })));
    const legend = h('div', { class: 'footprint-legend' }, order.map((id) => h('div', { class: 'fp-item' },
      h('span', { class: `swatch lc-${id === '_other' ? 'slate' : layerColor(id)}` }),
      h('span', { text: id === '_other' ? 'Other' : layerLabel(id) }),
      h('span', { class: 'mono muted small' }, `${counts[id].files}f · `, h('span', { class: 'add', text: `+${counts[id].add}` }), counts[id].del ? h('span', { class: 'del', text: ` −${counts[id].del}` }) : null,
        h('span', { text: ` · ${Math.round((counts[id].add + counts[id].del) / total * 100)}%` })))));

    const findings = (S.review && S.review.findings) || [];
    const sev = ['high', 'medium', 'low', 'info'].map((k) => [k, findings.filter((f) => f.severity === k).length]).filter(([, n]) => n);

    return h('section', null,
      issuesBanner(),
      h('div', { class: 'overview-grid' },
        h('div', { class: 'ov-main' },
          h('div', { class: 'eyebrow', text: 'What this PR does' }),
          sum.headline ? richEl('p', sum.headline, 'headline') : h('p', { class: 'headline', text: M.title }),
          (sum.what || []).length ? h('ul', { class: 'what' }, sum.what.map((w) => richEl('li', w))) : null,
          sum.why ? h('div', { class: 'why' }, h('div', { class: 'label', text: 'Why' }), richEl('p', sum.why)) : null),
        h('aside', { class: 'ov-side' },
          h('dl', { class: 'facts' },
            fact('Author', M.author), fact('Branch', `${M.head} → ${M.base}`), fact('Commits', M.commits),
            fact('Opened', (M.createdAt || '').slice(0, 10)), fact('Updated', (M.updatedAt || '').slice(0, 10)),
            sum.ticket ? fact('Ticket', sum.ticket) : null),
          (sum.tags || []).length ? h('div', { class: 'chips' }, sum.tags.map((t) => h('span', { class: 'tag', text: t }))) : null,
          sev.length ? h('div', { class: 'sev-summary' }, h('div', { class: 'label', text: 'Review findings' }),
            h('div', { class: 'chips' }, sev.map(([k, n]) => h('button', { type: 'button', class: `sev-chip sev-${k}`, onclick: () => scrollToId('review') }, `${n} ${k}`)))) : null)),
      h('div', { class: 'footprint' }, h('div', { class: 'label', text: 'Where the changed lines are' }), bar, legend),
      (sum.impact || []).length ? h('div', { class: 'impact' }, h('div', { class: 'label', text: 'Impact' }),
        h('dl', { class: 'impact-list' }, sum.impact.map((it) => [h('dt', { class: it.level ? `lvl-${it.level}` : '', text: it.label }), richEl('dd', it.text)]))) : null);
  }
  const fact = (k, v) => (v === undefined || v === null || v === '') ? null : [h('dt', { text: k }), h('dd', { class: k === 'Branch' ? 'mono small' : '', text: String(v) })];

  // ── Data flow: one map of what comes in, what processes it, where it is stored, what goes out ──
  const ENTITY = Object.fromEntries(((S.data_model && S.data_model.entities) || []).map((en) => [en.id, en]));
  const ENDPOINT = Object.fromEntries(((S.api && S.api.endpoints) || []).map((ep) => [ep.id || slug(ep.method + ep.path), ep]));
  const INPUT = Object.fromEntries(((S.api && S.api.inputs) || []).map((inp) => [inp.id || inp.name, inp]));

  function entityCard(en) {
    return h('article', { class: 'entity', id: `entity-${slug(en.id || en.name)}` },
      h('div', { class: 'entity-head' },
        h('div', { class: 'entity-kicker' }, h('span', { class: `kind kind-${slug(en.kind || '')}`, text: en.kind || 'entity' }), en.store ? h('span', { class: 'mono small muted', text: en.store }) : null, changeBadge(en.change)),
        h('h3', { class: 'mono entity-name', text: en.name }),
        en.summary ? richEl('p', en.summary, 'entity-sum') : null),
      fieldTable(en.fields),
      (en.writers || en.readers) ? h('div', { class: 'rw' },
        (en.writers || []).length ? h('div', null, h('span', { class: 'label', text: 'Written by' }), h('div', { class: 'chips' }, en.writers.map((w) => symButton(w, { compact: true })))) : null,
        (en.readers || []).length ? h('div', null, h('span', { class: 'label', text: 'Read by' }), h('div', { class: 'chips' }, en.readers.map((w) => symButton(w, { compact: true })))) : null) : null,
      (en.notes || []).length ? h('ul', { class: 'notes' }, en.notes.map((n) => richEl('li', n))) : null,
      en.example !== undefined ? disclosure([h('span', { text: en.example_label || 'Example document' })], () => codeBlock(en.example, 'json'), false) : null,
      en.ref ? h('div', { class: 'card-foot' }, refButton(en.ref, `Source · ${shortRef(en.ref)}`)) : null);
  }
  function ioPanel(title, io) {
    if (!io) return null;
    return h('div', { class: 'io-panel' },
      h('div', { class: 'io-head' }, h('span', { class: 'label', text: title }), io.model ? h('code', { class: 'model-name', text: io.model }) : null, io.ref ? refButton(io.ref) : null),
      fieldTable(io.fields),
      io.example !== undefined ? disclosure([h('span', { text: 'Example' })], () => codeBlock(io.example, 'json'), !io.fields) : null);
  }
  function endpointCard(ep, stacked) {
    return h('article', { class: `endpoint${stacked ? ' stacked' : ''}`, id: `ep-${slug(ep.method + ep.path)}` },
      h('div', { class: 'ep-head' },
        h('span', { class: `method m-${(ep.method || '').toLowerCase()}`, text: ep.method }),
        h('code', { class: 'ep-path', text: ep.path }), changeBadge(ep.change)),
      ep.summary ? richEl('p', ep.summary, 'ep-sum') : null,
      h('div', { class: 'ep-meta' },
        ep.auth ? h('div', null, h('span', { class: 'label', text: 'Auth' }), richEl('span', ep.auth)) : null,
        ep.handler ? h('div', null, h('span', { class: 'label', text: 'Handler' }), symButton(ep.handler, { compact: true })) : null),
      h('div', { class: 'io' }, ioPanel('Request', ep.request), ioPanel('Response', ep.response)),
      (ep.errors || []).length ? h('div', { class: 'errors' }, h('div', { class: 'label', text: 'Errors' }),
        h('ul', null, ep.errors.map((er) => h('li', null, h('code', { class: 'status', text: String(er.status) }), richEl('span', er.when))))) : null,
      (ep.notes || []).length ? h('ul', { class: 'notes' }, ep.notes.map((n) => richEl('li', n))) : null);
  }
  function inputsTable(inputs) {
    return h('div', { class: 'table-wrap' }, h('table', { class: 'fields inputs' },
      h('thead', null, h('tr', null, h('th', { text: 'Kind' }), h('th', { text: 'Name' }), h('th', { text: 'Default' }), h('th', { text: 'What it does' }))),
      h('tbody', null, inputs.map((inp) => h('tr', null,
        h('td', null, h('span', { class: `kind kind-${slug(inp.kind || '')}`, text: inp.kind })),
        h('td', null, h('code', { class: 'field-name', text: inp.name }), changeBadge(inp.change)),
        h('td', null, inp.default !== undefined ? h('code', { text: String(inp.default) }) : h('span', { class: 'muted', text: '—' })),
        h('td', null, richEl('div', inp.desc || ''), inp.ref ? refButton(inp.ref) : null))))));
  }
  function lifecyclePanel(lc) {
    return h('div', { class: 'panel lifecycle' },
      h('div', { class: 'panel-head' }, h('h3', { text: lc.title || 'State lifecycle' }), lc.description ? richEl('p', lc.description, 'muted') : null),
      renderGraph({
        title: lc.title, lanes: false, direction: lc.direction || 'LR',
        nodes: (lc.states || []).map((st) => ({ id: st.id, label: st.label || st.id, sub: st.sub, shape: st.kind === 'final' ? 'box' : 'pill', col: st.col, tip: st.desc, cls: `sk-${st.kind || 'state'}` })),
        edges: (lc.transitions || []).map((t) => ({ from: t.from, to: t.to, label: t.label, kind: t.kind || (t.from === t.to ? 'retry' : 'call') })),
      }),
      h('div', { class: 'state-legend' }, (lc.states || []).map((st) => h('div', { class: `state-item sk-${st.kind || 'state'}` },
        h('code', { text: st.label || st.id }), richEl('span', st.desc || '')))));
  }

  function openEntity(id) {
    const en = ENTITY[id];
    if (!en) return;
    showDrawer({ crumb: `Stored data / ${en.store || en.kind || ''}`, build: () => h('div', { class: 'detail' }, entityCard(en)) });
  }
  function openEndpoint(id) {
    const ep = ENDPOINT[id];
    if (!ep) return;
    showDrawer({ crumb: `Endpoint / ${ep.router || ''}`, build: () => h('div', { class: 'detail' }, endpointCard(ep, true)) });
  }
  function openInput(id) {
    const inp = INPUT[id];
    if (!inp) return;
    showDrawer({
      crumb: `Input / ${inp.kind}`,
      build: () => h('div', { class: 'detail' },
        h('div', { class: 'detail-kicker' }, h('span', { class: 'kind', text: inp.kind }), changeBadge(inp.change)),
        h('h3', { class: 'detail-title mono', text: inp.name }),
        inp.default !== undefined ? h('div', { class: 'small muted' }, 'Default ', h('code', { text: String(inp.default) })) : null,
        richEl('p', inp.desc || '', 'detail-text'),
        inp.ref ? snippet(inp.ref) : null),
    });
  }
  function openMapItem(item) {
    if (item.entity && ENTITY[item.entity]) return openEntity(item.entity);
    if (item.endpoint && ENDPOINT[item.endpoint]) return openEndpoint(item.endpoint);
    if (item.input && INPUT[item.input]) return openInput(item.input);
    if (item.symbol && SYM[item.symbol]) return openSymbol(item.symbol);
    if (item.ref) return openRef(item.ref);
  }

  const DEFAULT_COLUMNS = [
    { id: 'in', label: 'Comes in' }, { id: 'process', label: 'Processed by' },
    { id: 'store', label: 'Stored in' }, { id: 'out', label: 'Goes out' },
  ];
  const ITEM_BADGE = { endpoint: 'HTTP', request: 'HTTP', response: 'HTTP', scheduler: 'CRON', setting: 'SETTINGS', env: 'ENV', external: 'EXTERNAL', mailbox: 'MAILBOX', 'existing-data': 'EXISTING DATA', function: 'CODE', collection: 'MONGO', embedded: 'MONGO', file: 'FILE', queue: 'QUEUE' };

  function renderDataMap(df) {
    const cols = df.columns && df.columns.length ? df.columns : DEFAULT_COLUMNS;
    const colIndex = Object.fromEntries(cols.map((c, i) => [c.id, i]));
    const items = df.items || [];
    const links = df.links || [];
    const byId = {};
    const wrap = h('div', { class: 'dmap' });
    const scroller = h('div', { class: 'dmap-scroll' }, wrap);
    const grid = h('div', { class: 'dmap-grid', style: `--cols:${cols.length}` });
    const svg = s('svg', { class: 'dmap-links', 'aria-hidden': 'true' });
    svg.appendChild(arrowDefs());
    const labelLayer = h('div', { class: 'dmap-labels', 'aria-hidden': 'true' });
    cols.forEach((c, i) => grid.appendChild(h('div', { class: `dmap-colhead dmc-${slug(c.id)}`, style: `grid-column:${i + 1};grid-row:1;order:${i * 100}` },
      h('span', { class: 'dmap-colnum', text: String(i + 1) }), h('span', { text: c.label }), c.sub ? h('span', { class: 'muted small', text: c.sub }) : null)));

    items.forEach((item) => {
      const ci = colIndex[item.column] ?? 0;
      const row = (item.row || 1) + 1;
      const fields = item.fields || (item.entity && ENTITY[item.entity] ? ENTITY[item.entity].fields.map((f) => f.name) : []);
      const out = links.filter((l) => l.from === item.id);
      const card = h('button', {
        type: 'button', class: `dmap-card dk-${slug(item.kind || 'item')}${item.layer ? ` lc-${layerColor(item.layer)}` : ''}`,
        style: `grid-column:${ci + 1};grid-row:${row} / span ${item.span || 1};order:${ci * 100 + row}`,
        'data-id': item.id, onclick: () => openMapItem(item),
      },
        h('div', { class: 'dmap-kicker' },
          h('span', { class: 'dmap-badge', text: item.badge || ITEM_BADGE[item.kind] || (item.kind || '').toUpperCase() }),
          changeBadge(item.change)),
        h('div', { class: 'dmap-title', html: rich(item.title) }),
        item.sub ? h('div', { class: 'dmap-sub', html: rich(item.sub) }) : null,
        fields.length ? h('ul', { class: 'dmap-fields' }, fields.slice(0, item.max_fields || 6).map((f) => {
          const name = typeof f === 'string' ? f : f.name;
          const meta = item.entity && ENTITY[item.entity] ? (ENTITY[item.entity].fields || []).find((x) => x.name === name) : null;
          return h('li', { class: meta && meta.change === 'added' ? 'fadd' : '' }, h('code', { text: name }), typeof f === 'object' && f.note ? h('span', { class: 'muted', text: ` ${f.note}` }) : null);
        }), fields.length > (item.max_fields || 6) ? h('li', { class: 'muted more', text: `+${fields.length - (item.max_fields || 6)} more` }) : null) : null,
        (item.bullets || []).length ? h('ul', { class: 'dmap-bullets' }, item.bullets.map((b) => richEl('li', b))) : null,
        // Stacked (phone) layout has no connector lines, so each card lists where its data goes.
        out.length ? h('ul', { class: 'dmap-out' }, out.map((l) => h('li', null, '→ ', h('strong', { text: (items.find((x) => x.id === l.to) || {}).title || l.to }), l.label ? ` · ${l.label}` : ''))) : null);
      byId[item.id] = card;
      card.addEventListener('mouseenter', () => focusCard(item.id, true));
      card.addEventListener('mouseleave', () => focusCard(item.id, false));
      card.addEventListener('focus', () => focusCard(item.id, true));
      card.addEventListener('blur', () => focusCard(item.id, false));
      grid.appendChild(card);
    });
    appendKids(wrap, [svg, grid, labelLayer]);

    let drawn = [];
    function focusCard(id, on) {
      wrap.classList.toggle('focusing', on);
      drawn.forEach((d) => {
        const lit = on && (d.l.from === id || d.l.to === id);
        d.path.classList.toggle('lit', lit); d.label.classList.toggle('lit', lit);
        if (lit) { byId[d.l.from].classList.add('lit'); byId[d.l.to].classList.add('lit'); }
      });
      if (!on) Object.values(byId).forEach((c) => c.classList.remove('lit'));
      else byId[id].classList.add('lit');
    }
    function draw() {
      // Phones get a stacked list; anything wider keeps the map and scrolls sideways if needed.
      const stacked = scroller.clientWidth < 600;
      wrap.classList.toggle('stacked', stacked);
      svg.innerHTML = ''; svg.appendChild(arrowDefs()); labelLayer.innerHTML = ''; drawn = [];
      if (stacked) return;
      const base = wrap.getBoundingClientRect();
      svg.setAttribute('width', wrap.clientWidth); svg.setAttribute('height', wrap.clientHeight);
      svg.setAttribute('viewBox', `0 0 ${wrap.clientWidth} ${wrap.clientHeight}`);
      const rect = (id) => { const r = byId[id].getBoundingClientRect(); return { l: r.left - base.left, r: r.right - base.left, t: r.top - base.top, b: r.bottom - base.top, cy: (r.top + r.bottom) / 2 - base.top, cx: (r.left + r.right) / 2 - base.left }; };
      // Spread several connectors on the same card side so they don't share one point.
      const ports = {};
      const plan = links.filter((l) => byId[l.from] && byId[l.to]).map((l) => {
        const a = rect(l.from), b = rect(l.to);
        const ca = colIndex[(items.find((x) => x.id === l.from) || {}).column] ?? 0;
        const cb = colIndex[(items.find((x) => x.id === l.to) || {}).column] ?? 0;
        const dir = cb > ca ? 1 : cb < ca ? -1 : 0;
        const fromSide = dir > 0 ? 'r' : dir < 0 ? 'l' : 'b';
        const toSide = dir > 0 ? 'l' : dir < 0 ? 'r' : 't';
        const p = { l, a, b, dir, fromSide, toSide };
        (ports[l.from + fromSide] = ports[l.from + fromSide] || []).push({ p, end: 'from', other: b.cy });
        (ports[l.to + toSide] = ports[l.to + toSide] || []).push({ p, end: 'to', other: a.cy });
        return p;
      });
      Object.values(ports).forEach((list) => {
        list.sort((x, y) => x.other - y.other);
        list.forEach((entry, k) => { entry.p[entry.end + 'Frac'] = list.length === 1 ? 0.5 : 0.3 + (0.4 * k) / (list.length - 1); });
      });
      const placed = [];
      plan.forEach((p) => {
        const { a, b } = p;
        let x1, y1, x2, y2, d;
        if (p.dir === 0) {
          x1 = a.cx; y1 = a.b; x2 = b.cx; y2 = b.t;
          d = `M${x1},${y1} C${x1},${y1 + 30} ${x2},${y2 - 30} ${x2},${y2}`;
        } else {
          x1 = p.dir > 0 ? a.r : a.l; x2 = p.dir > 0 ? b.l : b.r;
          y1 = a.t + (a.b - a.t) * p.fromFrac; y2 = b.t + (b.b - b.t) * p.toFrac;
          const dx = (x2 - x1) / 2;
          d = `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`;
        }
        const kind = p.l.kind || 'data';
        const path = s('path', { class: `edge dmap-edge ek-${kind}`, d, 'marker-end': `url(#arrow-${kind})` });
        svg.appendChild(path);
        const label = h('div', { class: `dmap-label ek-${kind}`, html: rich(p.l.label || '') });
        labelLayer.appendChild(label);
        const lw = Math.min(160, Math.max(70, Math.abs(x2 - x1) - 10));
        label.style.maxWidth = `${lw}px`;
        const mx = (x1 + x2) / 2;
        let my = (y1 + y2) / 2;
        const lh = label.offsetHeight || 16;
        for (let k = 0; k < 10 && placed.some((q) => Math.abs(q.x - mx) < (q.w + label.offsetWidth) / 2 && Math.abs(q.y - my) < (q.h + lh) / 2 + 2); k++) my += (k % 2 ? -1 : 1) * (k + 1) * 9;
        placed.push({ x: mx, y: my, w: label.offsetWidth, h: lh });
        label.style.left = `${mx}px`; label.style.top = `${my}px`;
        if (!p.l.label) label.hidden = true;
        drawn.push({ l: p.l, path, label });
      });
    }
    if ('ResizeObserver' in window) { const ro = new ResizeObserver(() => requestAnimationFrame(draw)); ro.observe(wrap); ro.observe(scroller); }
    requestAnimationFrame(draw);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => requestAnimationFrame(draw));
    return scroller;
  }

  function renderDataFlow() {
    const df = S.data_flow;
    const dm = S.data_model || {};
    const api = S.api || {};
    const entities = dm.entities || [];
    const endpoints = api.endpoints || [];
    const inputs = api.inputs || [];
    if (!df && !entities.length && !endpoints.length && !inputs.length) return null;
    const reference = [];
    if (entities.length) reference.push(disclosure([h('span', { class: 'ref-title', text: 'Stored data' }), h('span', { class: 'muted small', text: `${entities.length} shape${entities.length > 1 ? 's' : ''} · every field with type and meaning` })],
      () => h('div', { class: 'entities' }, entities.map(entityCard)), !df));
    if (endpoints.length) reference.push(disclosure([h('span', { class: 'ref-title', text: 'Endpoint contract' }), h('span', { class: 'muted small', text: endpoints.map((ep) => `${ep.method} ${ep.path}`).join(' · ') })],
      () => h('div', { class: 'endpoints' }, endpoints.map((ep) => endpointCard(ep))), !df));
    if (inputs.length) reference.push(disclosure([h('span', { class: 'ref-title', text: api.inputs_title || 'Other inputs' }), h('span', { class: 'muted small', text: `${inputs.length} scheduler, setting, env and external entries` })],
      () => inputsTable(inputs), !df));
    return h('section', null,
      sectionHead('data', '1 · Data flow', (df && df.title) || 'What data moves where', (df && df.intro) || dm.intro),
      df ? h('div', { class: 'panel dmap-panel' }, renderDataMap(df),
        h('p', { class: 'muted small hint', text: 'Hover a card to trace its data. Click a card for every field, the endpoint contract, or the code.' })) : null,
      dm.lifecycle ? lifecyclePanel(dm.lifecycle) : null,
      reference.length ? h('div', { class: 'reference' }, h('div', { class: 'label', text: 'Reference' }), reference) : null);
  }

  function renderFlows() {
    const flows = S.flows || [];
    if (!flows.length) return null;
    const tabs = h('div', { class: 'tabs', role: 'tablist' });
    const panes = h('div', { class: 'tab-panes' });
    const built = {};
    const select = (i) => {
      tabs.querySelectorAll('button').forEach((b, k) => { b.setAttribute('aria-selected', String(k === i)); });
      panes.querySelectorAll('.tab-pane').forEach((p, k) => { p.hidden = k !== i; });
      if (!built[i]) { built[i] = true; buildFlow(flows[i], panes.children[i]); }
      store.set('flow', String(i));
    };
    flows.forEach((f, i) => {
      tabs.appendChild(h('button', { type: 'button', role: 'tab', class: 'tab', onclick: () => select(i) },
        h('span', { class: 'tab-kind', text: f.kind === 'sequence' ? 'Sequence' : f.kind === 'flowchart' ? 'Flowchart' : 'Flow' }), f.title));
      panes.appendChild(h('div', { class: 'tab-pane', role: 'tabpanel', hidden: true }));
    });
    const node = h('section', null,
      sectionHead('flows', '2 · Code flow', S.flows_title || 'How the code runs', S.flows_intro),
      tabs, panes,
      h('p', { class: 'muted small hint', text: 'Hover a box to trace its connections. Click a box or a numbered step to open its code in the side panel.' }));
    const saved = parseInt(store.get('flow') || '0', 10);
    select(saved >= 0 && saved < flows.length ? saved : 0);
    return node;
  }
  function buildFlow(flow, pane) {
    const legend = h('div', { class: 'edge-legend' }, Object.entries({ call: 'call', data: 'data / read', write: 'write', async: 'async / scheduled', external: 'external I/O', return: 'return', retry: 'retry / loop' })
      .filter(([k]) => ((flow.edges || []).concat(flow.messages || [])).some((e) => (e.kind || 'call') === k))
      .map(([k, label]) => h('span', { class: 'el-item' }, s('svg', { class: 'el-line', viewBox: '0 0 28 8', width: 28, height: 8 }, s('line', { class: `edge ek-${k}`, x1: 1, y1: 4, x2: 27, y2: 4 })), label)));
    appendKids(pane, [
      flow.description ? richEl('p', flow.description, 'flow-desc') : null,
      h('div', { class: 'panel diagram-panel' }, flow.kind === 'sequence' ? renderSequence(flow) : flow.kind === 'flowchart' ? renderFlowchart(flow) : renderGraph(flow), flow.kind === 'flowchart' ? null : legend),
      (flow.steps || []).length ? h('ol', { class: 'steps' }, flow.steps.map((st) => h('li', null, richEl('span', st.text), st.symbol ? symButton(st.symbol, { compact: true }) : null, st.ref ? refButton(st.ref) : null))) : null,
    ]);
  }

  function renderLayout() {
    const groups = (S.layout && S.layout.groups) || [];
    if (!groups.length) return null;
    // Program map: one band per layer, file tiles inside (click to jump to the file's detail).
    const map = h('div', { class: 'progmap' }, groups.map((g) => h('div', { class: `band lc-${layerColor(g.layer)}` },
      h('div', { class: 'band-label', text: layerLabel(g.layer) }),
      h('div', { class: 'band-files' }, (g.files || []).map((f) => h('button', { type: 'button', class: `file-tile chg-border-${f.change || 'modified'}`, onclick: () => { const d = document.getElementById(`file-${slug(f.path)}`); if (d && d._set) d._set(true); scrollToId(`file-${slug(f.path)}`); } },
        h('span', { class: 'mono ft-name', text: f.path.split('/').pop() }),
        h('span', { class: 'ft-sub', text: `${(f.symbols || []).length} symbol${(f.symbols || []).length === 1 ? '' : 's'}` })))))));

    const filter = h('input', { id: 'layout-filter', type: 'search', class: 'filter', placeholder: 'Filter symbols…', 'aria-label': 'Filter symbols' });
    const onlyChanged = h('input', { id: 'layout-only-changed', type: 'checkbox', checked: true });
    const list = h('div', { class: 'layout-list' });
    const renderList = () => {
      list.innerHTML = '';
      const q = filter.value.trim().toLowerCase();
      groups.forEach((g) => {
        const files = (g.files || []).map((f) => ({ f, syms: (f.symbols || []).filter((sym) => (!onlyChanged.checked || sym.change !== 'unchanged') && (!q || (sym.name + ' ' + (sym.summary || '')).toLowerCase().includes(q))) }))
          .filter(({ f, syms }) => syms.length || (!q && !(f.symbols || []).length));
        if (!files.length) return;
        list.appendChild(h('div', { class: 'layer-group' },
          h('div', { class: 'layer-title' }, layerChip(g.layer), g.summary ? richEl('span', g.summary, 'muted small') : null),
          files.map(({ f, syms }) => {
            const disc = disclosure([
              h('span', { class: 'mono file-path', text: f.path }), changeBadge(f.change),
              DIFF_BY_PATH[f.path] ? h('span', { class: 'mono small' }, h('span', { class: 'add', text: `+${DIFF_BY_PATH[f.path].additions}` }), ' ', h('span', { class: 'del', text: `−${DIFF_BY_PATH[f.path].deletions}` })) : null,
            ], () => h('div', { class: 'file-body' },
              f.summary ? richEl('p', f.summary, 'file-sum') : null,
              h('div', { class: 'sym-list' }, syms.map((sym) => symbolRow(sym.id)))), !!q || f.change === 'added');
            disc.id = `file-${slug(f.path)}`;
            return disc;
          })));
      });
      if (!list.children.length) list.appendChild(h('p', { class: 'muted', text: 'No symbols match.' }));
    };
    filter.addEventListener('input', renderList);
    onlyChanged.addEventListener('change', renderList);
    renderList();
    return h('section', null,
      sectionHead('layout', '4 · Program layout', S.layout.title || 'Where the code lives', S.layout.intro),
      map,
      h('div', { class: 'toolbar' }, filter,
        h('label', { class: 'check', for: 'layout-only-changed' }, onlyChanged, 'Changed symbols only'),
        h('button', { type: 'button', class: 'btn ghost', onclick: () => list.querySelectorAll('.disc').forEach((d) => d._set(true)) }, 'Expand all'),
        h('button', { type: 'button', class: 'btn ghost', onclick: () => list.querySelectorAll('.disc').forEach((d) => d._set(false)) }, 'Collapse all')),
      list);
  }
  function symbolRow(id) {
    const sym = SYM[id];
    return h('div', { class: `sym-row chg-row-${sym.change || 'unchanged'}` },
      h('div', { class: 'sym-row-head' },
        h('span', { class: 'kind', text: sym.kind || '' }),
        symButton(id),
        changeBadge(sym.change), tagChips(sym.tags),
        sym.ref ? refButton(sym.ref) : null),
      sym.signature ? h('code', { class: 'sig', text: sym.signature }) : null,
      sym.summary ? richEl('p', sym.summary, 'sym-sum') : null,
      (sym.calls || []).length ? h('div', { class: 'calls' }, h('span', { class: 'label', text: 'calls' }), sym.calls.map((c) => symButton(c, { compact: true }))) : null);
  }

  function renderStacks() {
    const stacks = S.call_stacks || [];
    if (!stacks.length) return null;
    const cards = stacks.map((st) => {
      const depthOpen = st.expand_depth ?? 3;
      const tree = h('div', { class: 'stack-tree', role: 'tree' }, frameNode(st.root || {}, 0, depthOpen));
      return h('article', { class: 'panel stack', id: `stack-${slug(st.id || st.title)}` },
        h('div', { class: 'panel-head stack-head' },
          h('div', null,
            st.trigger ? h('div', { class: 'trigger mono', text: st.trigger }) : null,
            h('h3', { text: st.title }),
            st.description ? richEl('p', st.description, 'muted') : null),
          h('div', { class: 'stack-tools' },
            h('button', { type: 'button', class: 'btn ghost', onclick: () => tree.querySelectorAll('.frame').forEach((f) => f._set && f._set(true)) }, 'Expand all'),
            h('button', { type: 'button', class: 'btn ghost', onclick: () => tree.querySelectorAll('.frame').forEach((f) => f._set && f._set(false)) }, 'Collapse'))),
        tree);
    });
    return h('section', null,
      sectionHead('stacks', '3 · Call stacks', S.call_stacks_title || 'Who calls what, in order', S.call_stacks_intro || 'Each tree starts at an entry point. Branch labels show the condition under which a call happens. Click a name to read its code.'),
      cards);
  }
  function frameNode(frame, depth, openDepth) {
    const sym = frame.symbol ? SYM[frame.symbol] : null;
    const kids = frame.children || [];
    const ref = frame.ref || (sym && sym.ref);
    const childBox = h('div', { class: 'frame-children', role: 'group' });
    const toggle = kids.length ? h('button', { type: 'button', class: 'frame-toggle', 'aria-label': 'Toggle children' }, h('span', { class: 'caret' })) : h('span', { class: 'frame-leaf' });
    const node = h('div', { class: `frame lc-${layerColor(sym ? sym.layer : frame.layer)}${frame.outcome ? ' outcome' : ''}`, role: 'treeitem' },
      h('div', { class: 'frame-row' },
        toggle,
        frame.branch ? h('span', { class: 'branch-pill', text: frame.branch }) : null,
        sym ? symButton(frame.symbol) : h('span', { class: `frame-label mono${frame.outcome ? ' outcome-label' : ''}`, text: frame.label || '' }),
        tagChips(frame.tags),
        ref ? refButton(ref) : null),
      frame.note ? richEl('div', frame.note, 'frame-note') : null,
      kids.length ? childBox : null);
    if (kids.length) {
      let built = false;
      const set = (on) => {
        if (on && !built) { kids.forEach((k) => childBox.appendChild(frameNode(k, depth + 1, openDepth))); built = true; }
        childBox.hidden = !on; node.classList.toggle('open', on); toggle.setAttribute('aria-expanded', String(on));
      };
      toggle.addEventListener('click', () => set(childBox.hidden));
      node._set = set;
      set(depth < openDepth);
    }
    return node;
  }

  // ── Diff ─────────────────────────────────────────────────────────────────
  const ANN = {};
  ((S.diff && S.diff.annotations) || []).forEach((a) => { ((ANN[a.file] = ANN[a.file] || {})[a.line] = ANN[a.file][a.line] || []).push(a); });
  const diffDiscs = {};
  function renderDiff() {
    if (!DIFF.length) return null;
    const order = (S.diff && S.diff.order) || [];
    const groupsOrder = Object.keys(FILE_LAYER);
    const rank = (p) => { const i = order.indexOf(p); if (i >= 0) return i; const g = groupsOrder.indexOf(p); return g >= 0 ? 1000 + g : 5000; };
    const files = DIFF.slice().sort((a, b) => rank(a.path) - rank(b.path));
    const annotatedOnly = h('input', { id: 'diff-annotated-only', type: 'checkbox' });
    const list = h('div', { class: 'diff-list' });
    files.forEach((f) => {
      const annCount = Object.values(ANN[f.path] || {}).reduce((a, l) => a + l.length, 0);
      const disc = disclosure([
        h('span', { class: `fstat fs-${f.status}`, text: f.status[0].toUpperCase() }),
        h('span', { class: 'mono file-path', text: f.path }),
        layerChip(guessLayer(f.path)),
        annCount ? h('span', { class: 'ann-count', text: `${annCount} note${annCount > 1 ? 's' : ''}` }) : null,
        h('span', { class: 'mono small diffstat' }, h('span', { class: 'add', text: `+${f.additions}` }), ' ', h('span', { class: 'del', text: `−${f.deletions}` })),
      ], () => diffTable(f), !f.collapsed && f.additions + f.deletions < 400);
      disc.classList.add('diff-file');
      disc.id = `diff-${slug(f.path)}`;
      disc.dataset.annotated = annCount ? '1' : '0';
      diffDiscs[f.path] = disc;
      list.appendChild(disc);
    });
    annotatedOnly.addEventListener('change', () => list.querySelectorAll('.diff-file').forEach((d) => { d.hidden = annotatedOnly.checked && d.dataset.annotated !== '1'; }));
    return h('section', null,
      sectionHead('diff', '5 · Diff', 'Code changes', (S.diff && S.diff.intro) || 'Full diff with review notes inline. Tests and docs start collapsed.'),
      h('div', { class: 'toolbar' },
        h('label', { class: 'check', for: 'diff-annotated-only' }, annotatedOnly, 'Only files with notes'),
        h('button', { type: 'button', class: 'btn ghost', onclick: () => list.querySelectorAll('.diff-file').forEach((d) => d._set(true)) }, 'Expand all'),
        h('button', { type: 'button', class: 'btn ghost', onclick: () => list.querySelectorAll('.diff-file').forEach((d) => d._set(false)) }, 'Collapse all')),
      list);
  }
  function diffTable(f) {
    if (f.binary) return h('p', { class: 'muted', text: 'Binary file.' });
    const lang = langOf(f.path);
    const anns = ANN[f.path] || {};
    const rows = [];
    f.hunks.forEach((hunk) => {
      rows.push(`<tr class="hunk"><td colspan="3"></td><td class="hunk-h mono">${esc(hunk.header)}</td></tr>`);
      let state = {};
      hunk.lines.forEach(([t, o, n, text]) => {
        const r = highlightLine(text, lang, state); state = r.state;
        const cls = t === '+' ? 'd-add' : t === '-' ? 'd-del' : 'd-ctx';
        rows.push(`<tr class="${cls}"${n ? ` id="dl-${slug(f.path)}-${n}"` : ''}><td class="ln-no">${o ?? ''}</td><td class="ln-no">${n ?? ''}</td><td class="d-sign">${t === ' ' ? '' : t === '-' ? '−' : '+'}</td><td class="ln-code">${r.html || ' '}</td></tr>`);
        if (n && t !== '-' && anns[n]) anns[n].forEach((a) => rows.push(`<tr class="ann-row"><td colspan="3"></td><td><div class="ann ann-${esc(a.kind || 'note')}"><span class="ann-kind">${esc(a.kind || 'note')}</span><span>${rich(a.text)}</span></div></td></tr>`));
      });
    });
    return h('div', { class: 'code-wrap diff-wrap' }, h('table', { class: 'code-table diff-table', html: rows.join('') }));
  }
  function revealDiff(path, line) {
    const disc = diffDiscs[path];
    if (!disc) return;
    disc.hidden = false;
    disc._set(true);
    const target = line && (document.getElementById(`dl-${slug(path)}-${line}`) || nearestLine(path, line));
    if (target) {
      target.scrollIntoView({ block: 'center', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
      target.classList.remove('flash'); void target.offsetWidth; target.classList.add('flash');
    } else scrollToId(disc.id);
  }
  function nearestLine(path, line) {
    const rows = Array.from(document.querySelectorAll(`[id^="dl-${slug(path)}-"]`));
    let best = null, bestDist = Infinity;
    rows.forEach((r) => { const n = +r.id.split('-').pop(); if (n >= line && n - line < bestDist) { best = r; bestDist = n - line; } });
    return best;
  }

  // ── Review ───────────────────────────────────────────────────────────────
  function renderReview() {
    const rv = S.review;
    if (!rv) return null;
    const order = { high: 0, medium: 1, low: 2, info: 3 };
    const findings = (rv.findings || []).slice().sort((a, b) => (order[a.severity] ?? 9) - (order[b.severity] ?? 9));
    return h('section', null,
      sectionHead('review', '6 · Review', rv.title || 'Review notes', rv.intro),
      rv.verdict ? h('div', { class: `verdict vd-${slug(rv.verdict_level || 'neutral')}` }, h('div', { class: 'label', text: 'Verdict' }), richEl('p', rv.verdict)) : null,
      findings.length ? h('div', { class: 'findings' }, findings.map((f) => h('article', { class: `finding fsev-${f.severity || 'info'}`, id: f.id ? `finding-${slug(f.id)}` : null },
        h('div', { class: 'finding-head' }, h('span', { class: `sev-chip sev-${f.severity || 'info'}`, text: f.severity || 'info' }), f.category ? h('span', { class: 'tag', text: f.category }) : null, richEl('h3', f.title)),
        richEl('p', f.detail || ''),
        f.suggestion ? h('div', { class: 'suggestion' }, h('span', { class: 'label', text: 'Suggestion' }), richEl('p', f.suggestion)) : null,
        (f.refs || []).length ? h('div', { class: 'chips' }, f.refs.map((r) => refButton(r))) : null))) : null,
      h('div', { class: 'review-grid' },
        (rv.tests || []).length ? h('div', { class: 'panel' }, h('div', { class: 'panel-head' }, h('h3', { text: 'Tests in this PR' })),
          h('div', { class: 'table-wrap' }, h('table', { class: 'fields' },
            h('thead', null, h('tr', null, h('th', { text: 'File' }), h('th', { text: 'Covers' }), h('th', { class: 'num', text: 'Tests' }))),
            h('tbody', null, rv.tests.map((t) => h('tr', null, h('td', null, h('code', { class: 'small', text: t.file.split('/').pop() })), h('td', null, richEl('span', t.what)), h('td', { class: 'num mono', text: t.count ?? '' }))))))) : null,
        (rv.untested || []).length ? h('div', { class: 'panel' }, h('div', { class: 'panel-head' }, h('h3', { text: 'Not covered' })), h('ul', { class: 'notes' }, rv.untested.map((u) => richEl('li', u)))) : null,
        (rv.deployment || []).length ? h('div', { class: 'panel' }, h('div', { class: 'panel-head' }, h('h3', { text: 'Deployment notes' })), h('ul', { class: 'notes' }, rv.deployment.map((u) => richEl('li', u)))) : null));
  }

  // ── Navigation (built after sections exist) ──────────────────────────────
  function renderNav() {
    const nav = document.getElementById('sidenav');
    const links = SECTIONS.map((sec) => h('a', { href: `#${sec.id}`, class: 'nav-link', 'data-target': sec.id, onclick: (e) => { e.preventDefault(); scrollToId(sec.id); try { window.history.replaceState(null, '', `#${sec.id}`); } catch (err) { /* sandboxed */ } } },
      h('span', { text: sec.navLabel }), sec.count !== undefined && sec.count !== null ? h('span', { class: 'nav-count mono', text: String(sec.count) }) : null));
    appendKids(nav, h('div', { class: 'nav-inner' }, links,
      h('div', { class: 'nav-foot muted small' }, `Generated ${M.generatedAt || ''}`, M.headOid ? h('div', { class: 'mono', text: `head ${M.headOid.slice(0, 9)}` }) : null)));
    if ('IntersectionObserver' in window) {
      const io = new IntersectionObserver((entries) => {
        entries.forEach((en) => { if (en.isIntersecting) nav.querySelectorAll('.nav-link').forEach((a) => a.classList.toggle('active', a.dataset.target === en.target.id)); });
      }, { rootMargin: '-20% 0px -70% 0px' });
      SECTIONS.forEach((sec) => { const el = document.getElementById(sec.id); if (el) io.observe(el); });
    }
  }

  // ── Boot ─────────────────────────────────────────────────────────────────
  renderTopbar();
  addSection('overview', 'Overview', renderOverview());
  addSection('data', 'Data flow', renderDataFlow(), ((S.data_flow && S.data_flow.items) || []).length || null);
  addSection('flows', 'Code flow', renderFlows(), (S.flows || []).length);
  addSection('stacks', 'Call stacks', renderStacks(), (S.call_stacks || []).length);
  addSection('layout', 'Program layout', renderLayout(), Object.keys(SYM).length);
  addSection('diff', 'Diff', renderDiff(), DIFF.length);
  addSection('review', 'Review', renderReview(), ((S.review && S.review.findings) || []).length);
  renderNav();
  const initial = (location.hash || '').slice(1);
  if (initial && /^[\w.~-]+$/.test(initial)) setTimeout(() => scrollToId(initial), 50);
})();
