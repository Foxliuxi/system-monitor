/* ==========================================================
   网络实时监测 · 前端
   图表全部自绘 Canvas，无任何外部依赖（断网也能看）
   ========================================================== */
'use strict';

const S = {
  hist: [],        // [{t,d,u,g,p,c,m}]
  latest: null,
  profile: null,
  advSig: '',
  advOpen: false,  // 提醒面板是否展开（默认收起，把空间留给监控数据）
  winThru: 60,
  winLat: 60,
};

let rafPending = false;   // 必须声明在使用它的 schedule() 之前，否则 TDZ 报错

const $ = (id) => document.getElementById(id);

/* 图表画笔颜色统一从 CSS 变量取：换主题只改样式表，JS 不用动 */
const COL = {
  blue: '#45c4fb', purple: '#b39bff', cyan: '#2ad4ee', violet: '#c58fff',
  green: '#3fd8a4', amber: '#fdc036', red: '#fb8585',
  grid: '#26364a', axis: '#93a6bb', zero: '#46607c',
};
function readTheme() {
  const cs = getComputedStyle(document.documentElement);
  const v = (n, fb) => cs.getPropertyValue(n).trim() || fb;
  for (const k of ['blue', 'purple', 'cyan', 'violet', 'green', 'amber', 'red']) {
    COL[k] = v('--' + k, COL[k]);
  }
  COL.grid = v('--chart-grid', COL.grid);
  COL.axis = v('--chart-axis', COL.axis);
  COL.zero = v('--chart-zero', COL.zero);
}
readTheme();

/* ---------------------------------------------------------- 格式化 */
function fmtRate(v) {
  if (v == null) return '--';
  if (v >= 100) return v.toFixed(0);
  if (v >= 10) return v.toFixed(1);
  if (v >= 1) return v.toFixed(2);
  return v.toFixed(2);
}
function fmtBytes(bps) {
  if (bps == null) return '--';
  const v = bps / 8;
  if (v >= 1024 * 1024) return (v / 1024 / 1024).toFixed(2) + ' MB/s';
  if (v >= 1024) return (v / 1024).toFixed(1) + ' KB/s';
  return v.toFixed(0) + ' B/s';
}
function fmtMs(v) {
  if (v == null) return '--';
  return v >= 100 ? v.toFixed(0) : v.toFixed(1);
}
function hhmmss(ts) {
  const d = new Date(ts * 1000);
  const p = (n) => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
function pulse(el, from) {
  if (el._last === from) return;
  el._last = from;
  if (el.animate) el.animate([{ opacity: 1 }, { opacity: .45 }, { opacity: 1 }], { duration: 300 });
}

/* ---------------------------------------------------------- 刻度计算 */
function niceScale(maxV, ticks) {
  if (!(maxV > 0)) return { max: 1, step: 0.25 };
  const raw = maxV / ticks;
  const exp = Math.floor(Math.log10(raw));
  const base = Math.pow(10, exp);
  const norm = raw / base;
  const mult = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
  const step = mult * base;
  return { max: step * ticks, step };
}

/* ---------------------------------------------------------- 折线图 */
class Chart {
  constructor(canvas, cfg) {
    this.cv = canvas;
    this.ctx = canvas.getContext('2d');
    this.cfg = cfg;                 // {series:[{key,color}], unit, minTop}
    this.pts = [];
    this.n = 60;
    this.w = 10; this.h = 10;
    this._resize();
    const ro = new ResizeObserver(() => { this._resize(); this.draw(); });
    ro.observe(canvas.parentElement);
  }

  _resize() {
    const dpr = window.devicePixelRatio || 1;
    const r = this.cv.parentElement.getBoundingClientRect();
    this.w = Math.max(r.width, 10);
    this.h = Math.max(r.height, 10);
    this.cv.width = Math.round(this.w * dpr);
    this.cv.height = Math.round(this.h * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  draw() {
    const ctx = this.ctx, W = this.w, H = this.h;
    ctx.clearRect(0, 0, W, H);

    const pad = { l: 44, r: 8, t: 10, b: 18 };
    const x0 = pad.l, x1 = W - pad.r, y0 = pad.t, y1 = H - pad.b;
    if (x1 <= x0 || y1 <= y0) return;

    const data = this.pts.slice(-this.n);
    if (!data.length) return;

    // ---- Y 轴范围 ----
    let maxV = 0;
    for (const d of data) {
      for (const s of this.cfg.series) {
        const v = d[s.key];
        if (v != null && v > maxV) maxV = v;
      }
    }
    const sc = niceScale(Math.max(maxV, this.cfg.minTop || 1), 4);
    const yOf = (v) => y1 - (Math.min(v, sc.max) / sc.max) * (y1 - y0);
    const xOf = (i) => x0 + (x1 - x0) * (data.length === 1 ? 0.5 : i / (data.length - 1));

    // ---- 网格与 Y 标签 ----
    ctx.font = '10px ui-monospace, "Cascadia Mono", Consolas, monospace';
    ctx.textBaseline = 'middle';
    for (let i = 0; i <= 4; i++) {
      const v = sc.step * i;
      const y = Math.round(yOf(v)) + .5;
      ctx.beginPath();
      ctx.strokeStyle = i === 0 ? COL.zero : COL.grid;
      ctx.lineWidth = 1;
      ctx.moveTo(x0, y);
      ctx.lineTo(x1, y);
      ctx.stroke();

      ctx.fillStyle = COL.axis;
      ctx.textAlign = 'right';
      const lbl = sc.max < 1 ? v.toFixed(2) : (sc.max < 10 ? v.toFixed(1) : v.toFixed(0));
      ctx.fillText(lbl, x0 - 7, y);
    }

    // ---- X 轴时间 ----
    ctx.textAlign = 'center';
    ctx.fillStyle = COL.axis;
    for (let i = 0; i <= 3; i++) {
      const idx = Math.round((data.length - 1) * i / 3);
      const x = x0 + (x1 - x0) * i / 3;
      const ta = i === 0 ? 'left' : i === 3 ? 'right' : 'center';
      ctx.textAlign = ta;
      ctx.fillText(hhmmss(data[idx].t), x, y1 + 10);
    }

    // ---- 各序列 ----
    for (const s of this.cfg.series) {
      // 颜色在每帧解析，主题切换后下一帧自动生效
      const col = s.ckey ? (COL[s.ckey] || s.color) : s.color;
      // 面积
      const grad = ctx.createLinearGradient(0, y0, 0, y1);
      grad.addColorStop(0, col + '38');
      grad.addColorStop(1, col + '02');

      let started = false, firstX = 0, lastX = 0;
      ctx.beginPath();
      data.forEach((d, i) => {
        const v = d[s.key];
        if (v == null) { started = false; return; }
        const x = xOf(i), y = yOf(v);
        if (!started) { ctx.moveTo(x, y); started = true; firstX = x; }
        else ctx.lineTo(x, y);
        lastX = x;
      });
      // 用同一条路径闭合填充
      if (lastX > firstX) {
        ctx.lineTo(lastX, y1);
        ctx.lineTo(firstX, y1);
        ctx.closePath();
        ctx.fillStyle = grad;
        ctx.fill();
      }

      // 折线
      started = false;
      ctx.beginPath();
      data.forEach((d, i) => {
        const v = d[s.key];
        if (v == null) { started = false; return; }
        const x = xOf(i), y = yOf(v);
        if (!started) { ctx.moveTo(x, y); started = true; }
        else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = col;
      ctx.lineWidth = 1.6;
      ctx.lineJoin = 'round';
      ctx.stroke();

      // 丢包：只给"确实判定为超时"的点打红点。
      // 不能用「值为空」来判断——探测还没跑完、或发包失败也会是空值，
      // 那样会凭空画出并不存在的丢包点。
      if (s.lossKey) {
        data.forEach((d, i) => {
          if (!d[s.lossKey]) return;
          const x = xOf(i);
          ctx.beginPath();
          ctx.arc(x, y1 - 3, 2.2, 0, Math.PI * 2);
          ctx.fillStyle = COL.red;
          ctx.fill();
        });
      }

      // 末端高亮点
      for (let i = data.length - 1; i >= 0; i--) {
        const v = data[i][s.key];
        if (v == null) continue;
        ctx.beginPath();
        ctx.arc(xOf(i), yOf(v), 2.6, 0, Math.PI * 2);
        ctx.fillStyle = col;
        ctx.fill();
        ctx.beginPath();
        ctx.arc(xOf(i), yOf(v), 5, 0, Math.PI * 2);
        ctx.fillStyle = col + '33';
        ctx.fill();
        break;
      }
    }
  }
}

/* ---------------------------------------------------------- 渲染：评分环 + 折叠提醒 */
/* 服务端也支持按语言出 grade，这里是兜底映射：
   万一服务端只发了中文（旧版接口），前端也能切到英文 */
const GRADE_KEYS = { '优秀': 'excellent', '良好': 'good', '一般': 'fair', '较差': 'poor' };

function gradeText(g) {
  const k = GRADE_KEYS[g];
  return k ? t('grade.' + k) : (g || '');
}

function renderScore(a) {
  if (!a) return;
  const score = a.score;
  $('score').textContent = score;
  $('grade').textContent = gradeText(a.grade);

  const circ = 2 * Math.PI * 27;
  const ring = $('ring');
  ring.style.strokeDasharray = circ;
  ring.style.strokeDashoffset = circ * (1 - score / 100);
  ring.style.stroke = score >= 85 ? COL.green : score >= 70 ? COL.cyan
    : score >= 50 ? COL.amber : COL.red;

  const crit = a.items.filter((i) => i.level === 'critical').length;
  const warn = a.items.filter((i) => i.level === 'warn').length;

  const card = $('advice-card');
  if (card) {
    // 保留用户手动展开/收起的选择，不被每秒刷新覆盖
    card.className = 'card a-advice'
      + (S.advOpen ? '' : ' collapsed')
      + (crit ? ' lv-critical' : warn ? ' lv-warn' : '');
  }
  const summary = $('adv-summary');
  if (summary) summary.textContent = a.summary || t('adv.none');

  const icon = $('adv-icon');
  if (icon) icon.textContent = crit ? '▲' : warn ? '◆' : '●';

  const cnt = $('adv-count');
  if (cnt) {
    cnt.textContent = crit
      ? t('adv.count.crit', { crit, warn })
      : warn ? t('adv.count.warn', { warn }) : t('adv.count.ok');
  }
}

/* ---------------------------------------------------------- 渲染：KPI 条
   顺序按"系统优先"：CPU / 显卡 / 内存 / 磁盘 → 下行 / 延迟 / 丢包 */
function renderKPI(snap, hist) {
  const net = snap.net || {}, lat = snap.latency || {}, hw = snap.hardware || {};
  const st = (snap.analysis || {}).stats || {};
  const gpu = snap.gpu && snap.gpu.available && snap.gpu.gpus ? snap.gpu.gpus[0] : null;
  const disk = snap.disk || {};

  const set = (id, val, sub, title) => {
    const el = $(id);
    if (el) el.textContent = val;
    if (sub !== undefined) {
      const s = $(id + '-sub');
      if (s) s.textContent = sub;
    }
    if (title !== undefined) {
      const box = $(id + '-sub') || el;
      if (box) box.title = title;
    }
  };

  // ---- 系统 ----
  const cpu = hw.cpu_pct || 0;
  const f = hw.freq || {};
  set('k-cpu', cpu.toFixed(0),
    t('kpi.cpu.sub', { threads: hw.cpu_per_core ? hw.cpu_per_core.length : 0 })
    + (f.current_mhz ? ` · ${f.current_mhz} MHz` : ''));
  pulse($('k-cpu'), cpu);

  if (gpu) {
    set('k-gpu', (gpu.util_pct || 0).toFixed(0),
      gpu.mem_total_mb
        ? t('kpi.gpu.sub', {
            temp: gpu.temp_c != null ? gpu.temp_c.toFixed(0) + '°C' : t('kpi.gpu.notemp'),
            used: (gpu.mem_used_mb / 1024).toFixed(1),
            total: (gpu.mem_total_mb / 1024).toFixed(0),
          })
        : (gpu.temp_c != null ? gpu.temp_c.toFixed(0) + '°C' : t('kpi.gpu.notemp')));
    pulse($('k-gpu'), gpu.util_pct);
  } else {
    set('k-gpu', '--', snap.gpu ? t('kpi.gpu.off') : t('kpi.gpu.wait'));
  }

  const mem = hw.mem_pct || 0;
  set('k-mem', mem.toFixed(0),
    `${(hw.mem_used_gb || 0).toFixed(1)} / ${(hw.mem_total_gb || 0).toFixed(1)} GB`);
  pulse($('k-mem'), mem);

  const rd = disk.read_mbps || 0, wr = disk.write_mbps || 0;
  set('k-disk', (rd + wr).toFixed(0),
    t('kpi.disk.sub', { r: rd.toFixed(1), w: wr.toFixed(1) }));

  // ---- 网络 ----
  set('k-down', fmtRate(net.down_mbps),
    t('kpi.down.sub', { up: fmtRate(net.up_mbps), bytes: fmtBytes(net.down_bytes) }));
  pulse($('k-down'), net.down_mbps);

  set('k-rtt', fmtMs(lat.public),
    t('kpi.lat.sub', { gw: fmtMs(lat.gateway), dns: fmtMs(lat.dns_ms) }));

  const loss = st.pub_loss_pct;
  // 丢包的口径要能自己核对：分母是真正发出去的探测，不是采样帧数。
  // error（解析失败/无路由）单独报，不混进丢包率。
  const att = st.pub_attempts;
  const to = st.pub_timeout;
  const err = st.pub_error;
  let lossSub = t('kpi.loss.probing');
  if (att) {
    lossSub = t('kpi.loss.sub', {
      to: to ?? 0, att,
      gw: st.gw_loss_pct != null ? st.gw_loss_pct.toFixed(1) : '--',
    });
    if (err) lossSub += ' · ' + t('kpi.loss.err', { err });
  }
  set('k-loss', loss != null ? loss.toFixed(1) : '--', lossSub,
    t('kpi.loss.tip', {
      target: st.target || lat.target || '—',
      timeout: st.timeout_ms || '—',
      att: att || 0, to: to || 0, err: err || 0,
    }));
}

/* ---------------------------------------------------------- 渲染：分析 */
/* 等级文案与评分等级共用 grade.* 命名空间 */
const LEVEL_KEYS = ['critical', 'warn', 'info', 'ok'];
function levelText(lv) {
  return LEVEL_KEYS.indexOf(lv) >= 0 ? t('grade.' + lv) : lv;
}

function renderAdvice(a) {
  if (!a) return;
  const sig = JSON.stringify(a.items.map((i) => [i.level, i.title, i.metric]));
  if (sig === S.advSig) return;
  S.advSig = sig;

  const box = $('advice');
  if (!box) return;
  // 数量统计由 renderScore 统一写进折叠条，这里只负责列表内容
  box.innerHTML = a.items.map((i) => `
    <article class="adv ${i.level}">
      <div class="adv-head">
        <span class="tag">${esc(levelText(i.level))}</span>
        <h3>${esc(i.title)}</h3>
        ${i.metric ? `<span class="metric">${esc(i.metric)}</span>` : ''}
      </div>
      <p class="detail">${esc(i.detail)}</p>
      ${i.advice ? `<p class="fix"><b>${esc(t('adv.howto'))}</b>${esc(i.advice)}</p>` : ''}
    </article>`).join('');
}

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* ---------------------------------------------------------- 渲染：CPU / 内存 */
function renderHW(hw, profile, procs) {
  if (!hw) return;
  const cpu = hw.cpu_pct || 0, mem = hw.mem_pct || 0;

  // 注意：新结构里 <i>%</i> 在 <b> 外面，这里只能写纯数字，
  // 否则会出现 "45%%" 这种重复单位
  $('hw-cpu').textContent = cpu.toFixed(0);
  const bc = $('bar-cpu');
  bc.style.width = Math.min(cpu, 100) + '%';
  bc.className = 'bar-fill ' + (cpu >= 90 ? 'crit' : cpu >= 70 ? 'hot' : 'cyan');

  const cores = hw.cpu_per_core || [];
  const cbox = $('cores');
  if (cbox.childElementCount !== cores.length) {
    cbox.innerHTML = cores.map(() => '<div class="core"><i></i></div>').join('');
  }
  [...cbox.children].forEach((el, i) => {
    const v = cores[i] || 0;
    const bar = el.firstElementChild;
    if (bar) bar.style.height = Math.max(v, 2) + '%';
    el.className = 'core' + (v >= 90 ? ' hot' : '');
  });

  const f = hw.freq || {};
  const throttled = f.max_mhz && f.current_mhz && f.current_mhz < f.max_mhz * 0.6;
  const badge = $('cpu-badge');
  if (badge) badge.textContent = f.current_mhz ? `${f.current_mhz} MHz` : t('cpu.badge.nofreq');
  const cpuFoot = $('hw-cpu-foot');
  if (cpuFoot) {
    cpuFoot.textContent = t('cpu.foot', {
      threads: cores.length,
      state: cpu >= 90 ? t('cpu.state.full')
        : cpu >= 70 ? t('cpu.state.high') : t('cpu.state.normal'),
    }) + (throttled ? t('cpu.state.throttle') : '');
  }

  $('hw-mem').textContent = mem.toFixed(0);
  const bm = $('bar-mem');
  bm.style.width = Math.min(mem, 100) + '%';
  bm.className = 'bar-fill ' + (mem >= 90 ? 'crit' : mem >= 75 ? 'hot' : 'violet');

  const used = hw.mem_used_gb || 0;
  const total = hw.mem_total_gb || 0;
  const mBadge = $('mem-badge');
  if (mBadge) mBadge.textContent = `${used.toFixed(1)} / ${total.toFixed(1)} GB`;

  // 内存卡内容偏少，被拉到与硬盘卡等高时会空出一块。
  // 补两项真实有用的信息填满：可用容量 + 占用最高的应用
  const ms = $('mem-stats');
  if (ms) {
    const top = procs && procs.mem && procs.mem.length ? procs.mem[0] : null;
    ms.innerHTML = `
      <div class="gs"><div class="k">${esc(t('mem.used'))}</div><div class="v">${used.toFixed(1)} GB</div></div>
      <div class="gs"><div class="k">${esc(t('mem.free'))}</div><div class="v">${Math.max(total - used, 0).toFixed(1)} GB</div></div>
      <div class="gs" style="grid-column:span 2">
        <div class="k">${esc(t('mem.top'))}</div>
        <div class="v">${top ? esc(top.name) + ' · ' + (top.mem_mb / 1024).toFixed(1) + ' GB' : esc(t('kpi.gpu.wait'))}</div>
      </div>`;
  }

  const memFoot = $('hw-mem-foot');
  if (memFoot) memFoot.textContent = mem >= 75
    ? t('mem.pressured')
    : t('mem.ok');
}

/* ---------------------------------------------------------- 渲染：显卡 */
function renderGPU(gpu) {
  const body = $('gpu-body');
  const nameEl = $('gpu-name');
  if (!body) return;

  // 区分"还没采到"和"确实不可用"，否则页面刚打开会闪一下"不可用"
  if (gpu === null || gpu === undefined) {
    nameEl.textContent = '';
    body.innerHTML = `<p class="muted pad">${esc(t('kpi.gpu.wait'))}</p>`;
    return;
  }
  if (!gpu.available || !gpu.gpus || !gpu.gpus.length) {
    nameEl.textContent = '';
    body.innerHTML = `<p class="gpu-na"><b>${esc(t('gpu.unavailable'))}</b><br>${
      esc(gpu.reason || t('gpu.noiface'))}</p>`;
    return;
  }
  const g = gpu.gpus[0];
  nameEl.textContent = gpu.gpus.length > 1
    ? t('gpu.count', { n: gpu.gpus.length }) : (g.name || '');
  const util = g.util_pct == null ? 0 : g.util_pct;
  const memPct = (g.mem_total_mb && g.mem_used_mb != null)
    ? (g.mem_used_mb / g.mem_total_mb * 100) : 0;

  body.innerHTML = `
    <div class="gpu-head">
      <div class="gpu-big"><b>${util.toFixed(0)}</b><i>%</i><span class="cap">${esc(t('gpu.util'))}</span></div>
      <div class="gpu-big"><b>${g.temp_c == null ? '--' : g.temp_c.toFixed(0)}</b><i>°C</i><span class="cap">${esc(t('gpu.coretemp'))}</span></div>
    </div>
    <div class="vram">
      <div class="vram-top">
        <span>${esc(t('gpu.vram'))}</span>
        <span>${g.mem_used_mb == null ? '--' : (g.mem_used_mb / 1024).toFixed(1)} / ${
          g.mem_total_mb == null ? '--' : (g.mem_total_mb / 1024).toFixed(0)} GB · ${memPct.toFixed(0)}%</span>
      </div>
      <div class="bar"><div class="bar-fill ${memPct > 90 ? 'crit' : memPct > 75 ? 'hot' : 'cyan'}"
        style="width:${Math.min(memPct, 100)}%"></div></div>
    </div>
    <div class="gpu-stats">
      <div class="gs"><div class="k">${esc(t('gpu.power'))}</div><div class="v">${
        g.power_w == null ? '--'
          : g.power_w.toFixed(0) + (g.power_limit_w == null ? ' W' : ' / ' + g.power_limit_w.toFixed(0) + ' W')}</div></div>
      <div class="gs"><div class="k">${esc(t('gpu.fan'))}</div><div class="v">${
        g.fan_pct == null ? '--' : g.fan_pct.toFixed(0) + '%'}</div></div>
      <div class="gs"><div class="k">${esc(t('gpu.clock'))}</div><div class="v">${
        g.clock_mhz == null ? '--' : g.clock_mhz.toFixed(0) + ' MHz'}</div></div>
      <div class="gs"><div class="k">${esc(t('gpu.membw'))}</div><div class="v">${
        g.mem_util_pct == null ? '--' : g.mem_util_pct.toFixed(0) + '%'}</div></div>
    </div>`;
}

/* ---------------------------------------------------------- 渲染：温度 */
function tempClass(v) {
  if (v == null) return 'na';
  if (v >= 85) return 'hot';
  if (v >= 70) return 'warm';
  return '';
}

function tempCard(label, entry, source) {
  if (!entry || entry.value == null) {
    return `<div class="temp-item na">
      <div class="k">${label}</div>
      <div class="v">${esc(t('temp.na'))}</div>
      <div class="s">${esc((entry && entry.reason) || source || '')}</div>
    </div>`;
  }
  return `<div class="temp-item ${tempClass(entry.value)}">
    <div class="k">${label}</div>
    <div class="v">${entry.value.toFixed(0)}<small>°C</small></div>
    <div class="s">${esc(entry.source || source || '')}</div>
  </div>`;
}

function renderTemp(thermal, gpu) {
  const box = $('temps');
  if (!box) return;
  if (!thermal) {
    box.innerHTML = `<p class="muted pad">${esc(t('temp.collecting'))}</p>`;
    return;
  }

  const cards = [];
  cards.push(tempCard('CPU', thermal && thermal.cpu));

  if (gpu && gpu.available && gpu.gpus && gpu.gpus[0] && gpu.gpus[0].temp_c != null) {
    // 来源随数据走：NVIDIA 是 nvidia-smi，AMD/Intel 是 LibreHardwareMonitor
    cards.push(tempCard(esc(t('temp.gpu')),
      { value: gpu.gpus[0].temp_c, source: gpu.source || 'nvidia-smi' }));
  } else {
    cards.push(`<div class="temp-item na">
      <div class="k">${esc(t('temp.gpu'))}</div><div class="v">${esc(t('temp.na'))}</div>
      <div class="s">${gpu && gpu.reason ? esc(gpu.reason) : esc(t('temp.nodata'))}</div></div>`);
  }

  // 主板温度：由 LHM 提供，读不到就不占位
  if (thermal && thermal.board && thermal.board.value != null) {
    cards.push(tempCard(esc(t('temp.board')), thermal.board));
  }

  // 硬盘温度：可能有多块盘，取最大值展示，详情放脚注
  const dmap = (thermal && thermal.disks) || {};
  const dvals = Object.entries(dmap).filter(([, v]) => v && v.value != null);
  if (dvals.length) {
    const hottest = dvals.reduce((a, b) => (b[1].value > a[1].value ? b : a));
    cards.push(tempCard(esc(t('temp.diskmax')),
      { value: hottest[1].value, source: t('temp.diskcount', { n: dvals.length }) }));
  } else {
    const reason = dmap._ && dmap._.reason ? dmap._.reason : t('temp.nodata');
    cards.push(`<div class="temp-item na">
      <div class="k">${esc(t('temp.disk'))}</div><div class="v">${esc(t('temp.na'))}</div>
      <div class="s">${esc(reason)}</div></div>`);
  }

  box.innerHTML = cards.join('');

  const note = $('temp-note');
  if (note) note.style.color = '';   // 复位，避免上一次的告警色残留
  const foot = $('temp-foot');
  if (thermal && thermal.source === 'lhm') {
    note.textContent = t('temp.note.lhm');
    foot.textContent = t('temp.foot.lhm');
  } else if (thermal && thermal.admin === false) {
    // 温度源没连上时，别只写"不可用"——给能照着做的两步
    note.textContent = t('temp.note.nolhm');
    note.style.color = 'var(--amber)';
    foot.textContent = t('temp.foot.nolhm');
  } else {
    note.textContent = t('temp.note.plain');
    foot.textContent = t('temp.foot.plain');
  }
}

/* ---------------------------------------------------------- 渲染：硬盘 */
function fmtGB(v) {
  if (v == null) return '--';
  return v >= 1000 ? (v / 1000).toFixed(2) + ' TB' : v.toFixed(0) + ' GB';
}

const _diskSig = { v: '' };

function renderDisk(disk) {
  if (!disk) return;
  // IO 速率每秒都变，一行文本更新极便宜，直接刷
  const io = $('disk-io');
  if (io) {
    io.textContent = t('disk.io', {
      r: (disk.read_mbps || 0).toFixed(1), w: (disk.write_mbps || 0).toFixed(1),
    });
  }

  const parts = (disk.partitions || []).slice().sort((a, b) => a.device.localeCompare(b.device));
  const phys = disk.physical || [];
  // 分区容量 10 秒才变一次，用签名挡住无谓的 DOM 重建
  const sig = parts.map((p) => p.device + p.pct).join('|') + '#'
    + phys.map((d) => d.name + d.health).join('|');
  if (sig === _diskSig.v) return;
  _diskSig.v = sig;

  const box = $('disks');
  if (box) {
    // 分区数量不固定（插个 U 盘 / 挂个虚拟盘就多一条），超过 3 个时收紧间距，
    // 否则卡片高度固定，第 4 条会被裁掉
    box.className = 'disks' + (parts.length > 3 ? ' compact' : '');
    box.innerHTML = parts.map((p) => {
      const cls = p.pct >= 90 ? 'crit' : p.pct >= 75 ? 'warnv' : '';
      return `<div>
        <div class="disk-top">
          <b>${esc(p.device)}</b>
          <span class="sz">${fmtGB(p.used_gb)} / ${fmtGB(p.total_gb)}</span>
        </div>
        <div class="disk-bar"><i class="${cls}" style="width:${Math.min(p.pct, 100)}%"></i></div>
        <div class="disk-meta">
          <span>${esc(t('disk.used', { pct: p.pct.toFixed(0) }))}</span>
          <span>${esc(t('disk.free', { v: fmtGB(p.free_gb) }))}</span>
        </div>
      </div>`;
    }).join('');
  }

  const health = $('disk-health');
  if (health) {
    if (phys.length) {
      const bad = phys.filter((d) => d.health && d.health !== 'Healthy');
      health.innerHTML = phys.map((d) =>
        `${esc(d.name)}（${esc(d.media)}${d.size_gb ? ' · ' + fmtGB(d.size_gb) : ''}）`
      ).join(' · ') + (bad.length
        ? `　<span style="color:var(--red)">${esc(t('disk.bad', { n: bad.length }))}</span>`
        : `　<span style="color:var(--green)">${esc(t('disk.healthy'))}</span>`);
    } else {
      health.textContent = t('disk.reading');
    }
  }
}

/* ---------------------------------------------------------- 渲染：进程排行 */
function fmtMemMB(mb) {
  if (mb == null) return '--';
  if (mb >= 1024) return (mb / 1024).toFixed(2) + ' GB';
  return mb.toFixed(0) + ' MB';
}

function rankRow(i, name, count, barPct, valText, color) {
  return `<li class="${i === 0 ? 'top1' : ''}">
    <span class="rk">${i + 1}</span>
    <span class="nm" title="${esc(name)}">${esc(name)}</span>
    <span class="cnt">${count > 1 ? '×' + count : ''}</span>
    <div class="rk-bar"><i style="width:${Math.max(barPct, 1).toFixed(1)}%;
      background:linear-gradient(90deg,${color[0]},${color[1]})"></i></div>
    <span class="vv">${valText}</span>
  </li>`;
}

function renderRank(procs) {
  const cpuEl = $('rank-cpu');
  const memEl = $('rank-mem');
  if (!cpuEl || !memEl || !procs) return;

  const cpu = procs.cpu || [];
  const mem = procs.mem || [];

  if (!cpu.length && !mem.length) {
    cpuEl.innerHTML = `<li class="rk-empty muted">${esc(t('rank.probing'))}</li>`;
    memEl.innerHTML = `<li class="rk-empty muted">${esc(t('rank.waiting'))}</li>`;
    return;
  }

  const maxCpu = Math.max(...cpu.map((r) => r.cpu_pct), 1);
  const maxMem = Math.max(...mem.map((r) => r.mem_mb), 1);
  const none = `<li class="rk-empty muted">${esc(t('rank.empty'))}</li>`;

  cpuEl.innerHTML = cpu.map((r, i) => rankRow(
    i, r.name, r.count, r.cpu_pct / maxCpu * 100,
    r.cpu_pct.toFixed(1) + '%', [COL.cyan, COL.blue]
  )).join('') || none;

  memEl.innerHTML = mem.map((r, i) => rankRow(
    i, r.name, r.count, r.mem_mb / maxMem * 100,
    fmtMemMB(r.mem_mb), [COL.violet, COL.purple]
  )).join('') || none;

  const note = $('rank-note');
  if (note) {
    note.textContent = t('rank.note', {
      state: procs.ready ? t('rank.note.live') : t('rank.note.baseline'),
    });
  }
}

/* ---------------------------------------------------------- 渲染：链路 */
function renderLink(snap) {
  if (!snap) return;
  const p = S.profile || {};
  const nic = snap.nic || {};
  const hwNic = (p.nics || []).find((n) => n.name === nic.name) || {};
  const w = snap.wifi;
  const net = snap.net || {};

  const chips = [];
  const add = (label, value, cls) => chips.push(
    `<span class="chip ${cls || ''}"><b>${label}</b>${value}</span>`
  );

  const isWifi = hwNic.is_wireless || !!w;
  add(esc(t('link.nic')), esc(nic.name || t('link.unknown')));
  add(esc(t('link.type')), isWifi ? esc(t('link.wireless')) : esc(t('link.wired')));
  if (nic.speed_mbps) add(esc(t('link.speed')), `${nic.speed_mbps} Mbps`);

  // 从 KPI 条挪下来的网络指标，避免顶部挤 7 个格子
  add(esc(t('link.up')), `${fmtRate(net.up_mbps)} Mbps`);
  add(esc(t('link.conns')),
    t('link.count', { n: snap.conns != null ? snap.conns : '--' }));
  const st = (snap.analysis || {}).stats || {};
  if (st.jitter != null) {
    add(esc(t('link.jitter')), `${fmtMs(st.jitter)} ms`,
      st.jitter > 40 ? 'warnv' : st.jitter < 8 ? 'good' : '');
  }

  if (w) {
    const s = w.signal_pct;
    const sigCls = s == null ? '' : s >= 70 ? 'good' : s >= 45 ? 'warnv' : 'bad';
    if (s != null) add(esc(t('link.signal')), `${s}%`, sigCls);
    add(esc(t('link.band')), esc(w.band || '-'));
    add(esc(t('link.radio')), esc(w.radio || '-'));
    add(esc(t('link.channel')), esc(w.channel || '-'));
    if (w.rx_mbps || w.tx_mbps) {
      add(esc(t('link.nego')), `${w.rx_mbps || '-'}/${w.tx_mbps || '-'} M`);
    }
  }

  add(esc(t('link.gateway')), esc(p.gateway || t('link.unknown')));

  const err = (net.err_in_total || 0) + (net.err_out_total || 0);
  const drop = (net.drop_in_total || 0) + (net.drop_out_total || 0);
  add(esc(t('link.err')), `${err} / ${drop}`, err > 0 ? 'bad' : 'good');
  add(esc(t('link.total')), `↓${net.total_recv_gb || 0}G ↑${net.total_sent_gb || 0}G`);

  // 空置的千兆口单独一条，占满整行以引起注意
  const spare = (p.nics || []).filter((n) =>
    !n.is_wireless && n.status !== 'Up' && (n.nominal_speed_mbps || 0) >= 100
    && !/tap|vpn/i.test(n.desc || ''));
  if (spare.length && isWifi) {
    add(esc(t('link.spare')),
      t('link.spare.detail', {
        desc: esc(spare[0].desc), speed: spare[0].nominal_speed_mbps,
      }), 'warnv wide');
  }

  $('link').innerHTML = chips.join('');
  const lb = $('link-badge');
  if (lb) lb.textContent = w ? (w.ssid || t('link.wireless')) : t('link.wiredap');
}

/* ---------------------------------------------------------- 图表实例 */
const chartThru = new Chart($('c-thru'), {
  series: [
    { key: 'd', ckey: 'blue' },
    { key: 'u', ckey: 'purple' },
  ],
  minTop: 1,
});
const chartLat = new Chart($('c-lat'), {
  series: [
    { key: 'g', ckey: 'green', lossKey: 'gk' },
    { key: 'p', ckey: 'amber', lossKey: 'pk' },
  ],
  minTop: 10,
});

function redrawCharts() {
  chartThru.pts = S.hist;
  chartThru.n = S.winThru;
  chartLat.pts = S.hist;
  chartLat.n = S.winLat;
  chartThru.draw();
  chartLat.draw();
}

/* ---------------------------------------------------------- 主更新 */
function schedule() {
  if (rafPending) return;
  rafPending = true;
  requestAnimationFrame(() => {
    rafPending = false;
    redrawCharts();
  });
}

/* ---------------------------------------------------------- 慢指标的渲染节流
   显卡 2s、温度 15s、进程 2s、磁盘容量 10s 才变一次，
   而快照是 1s 一次。不节流会导致排行榜文字每秒重排、选中被清掉、视觉闪烁。 */
const _sig = { gpu: '', temp: '', rank: '' };

function renderSlow(snap) {
  const g = snap.gpu;

  const gs = g ? `${g.available}|${(g.gpus || []).map((x) =>
    [x.util_pct, x.mem_used_mb, x.temp_c, x.power_w, x.fan_pct, x.clock_mhz].join('/')).join(';')}` : '';
  if (gs !== _sig.gpu) {
    _sig.gpu = gs;
    renderGPU(g);
  }

  // 温度卡片包含显卡温度，所以显卡变化时也要重绘
  const t = snap.thermal;
  const tsig = t
    ? `${t.ts}|${t.cpu && t.cpu.value}|${t.admin}|${g && g.gpus && g.gpus[0] ? g.gpus[0].temp_c : ''}`
    : '';
  if (tsig !== _sig.temp) {
    _sig.temp = tsig;
    renderTemp(t, g);
  }

  renderDisk(snap.disk);

  const p = snap.procs;
  const psig = p ? `${p.ts}|${p.ready}` : '';
  if (psig !== _sig.rank) {
    _sig.rank = psig;
    renderRank(p);
  }
}

function applySnapshot(snap, hist) {
  S.latest = snap;
  renderKPI(snap, hist);
  renderScore(snap.analysis);
  renderAdvice(snap.analysis);
  renderHW(snap.hardware, S.profile, snap.procs);
  renderLink(snap);
  renderSlow(snap);
  const nic = (snap.nic || {}).name || '—';
  $('foot-nic').textContent = nic + (snap.wifi ? ` · ${snap.wifi.ssid || ''}` : '');
  const up = snap.uptime || 0;
  $('foot-uptime').textContent = t('foot.uptime', {
    t: up >= 3600
      ? Math.floor(up / 3600) + 'h' + Math.floor(up % 3600 / 60) + 'm'
      : Math.floor(up / 60) + 'm' + (up % 60) + 's',
  });
  if (snap.analysis && snap.analysis.summary) {
    $('subline').textContent = `${S.profile?.cpu_model || ''} · ${S.profile?.os || ''}`;
  }
  schedule();
}

/* ---------------------------------------------------------- SSE */
function setConn(state) {
  const box = $('conn-box');
  box.className = 'conn ' + state;
  $('conn-text').textContent = state === 'live' ? t('conn.live')
    : state === 'dead' ? t('conn.dead') : t('conn.connecting');
}

function connect() {
  // 重连前先关掉旧的，避免切换语言后两条流同时往页面写
  if (S.es) { try { S.es.close(); } catch (_) { /* 已关闭 */ } }
  // lang 一起带上：分析文案由服务端生成，服务端得知道用哪种语言
  const es = new EventSource('/api/stream?lang=' + getLang());
  S.es = es;

  es.addEventListener('init', (e) => {
    const d = JSON.parse(e.data);
    S.profile = d.profile || {};
    S.hist = d.history || [];
    setConn('live');
    if (d.latest) applySnapshot(d.latest, S.hist);
    else schedule();
  });

  es.addEventListener('tick', (e) => {
    const snap = JSON.parse(e.data);
    S.hist.push({
      t: snap.ts,
      d: snap.net?.down_mbps ?? 0,
      u: snap.net?.up_mbps ?? 0,
      g: snap.latency?.gateway ?? null,
      p: snap.latency?.public ?? null,
      c: snap.hardware?.cpu_pct ?? null,
      m: snap.hardware?.mem_pct ?? null,
    });
    if (S.hist.length > 1900) S.hist.splice(0, S.hist.length - 1900);
    applySnapshot(snap, S.hist);
    setConn('live');
  });

  es.onerror = () => {
    setConn('dead');
    // EventSource 自带重连，这里只更新界面状态
  };

  es.onopen = () => setConn('live');
}

/* ---------------------------------------------------------- 交互 */
function bindRange(id, key) {
  $(id).addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    [...e.currentTarget.children].forEach((b) => b.classList.remove('on'));
    btn.classList.add('on');
    S[key] = parseInt(btn.dataset.n, 10);
    schedule();
  });
}
bindRange('range-thru', 'winThru');
bindRange('range-lat', 'winLat');

/* ---------------------------------------------------------- 主题 */
const THEME_KEY = 'smon.theme';

function applyTheme(name, persist) {
  const t = name === 'light' ? 'light' : 'dark';
  document.documentElement.dataset.theme = t;
  readTheme();                       // 图表画笔颜色重新取变量
  document.querySelectorAll('[data-theme-set]').forEach((b) => {
    b.classList.toggle('on', b.dataset.themeSet === t);
  });
  if (persist) {
    try { localStorage.setItem(THEME_KEY, t); } catch (_) { /* 隐私模式下忽略 */ }
  }
  redrawCharts();
  // 排行条的配色是内联的，签名不清空就不会重绘
  _sig.gpu = _sig.temp = _sig.rank = '';
  if (S.latest) applySnapshot(S.latest, S.hist);
}

document.querySelectorAll('[data-theme-set]').forEach((b) => {
  b.addEventListener('click', () => applyTheme(b.dataset.themeSet, true));
});
applyTheme(document.documentElement.dataset.theme || 'dark', false);

/* ---------------------------------------------------------- 语言 */
function applyLang(lang) {
  setLang(lang);
  applyStaticI18n();
  // 文案变了，之前那些"内容没变就不重绘"的签名必须作废
  S.advSig = '';
  _sig.gpu = _sig.temp = _sig.rank = '';
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
  if (S.latest) applySnapshot(S.latest, S.hist);
  // 分析结论是服务端生成的，必须换语言重连才会变
  connect();
}

document.querySelectorAll('[data-lang-set]').forEach((b) => {
  b.addEventListener('click', () => applyLang(b.dataset.langSet));
});
applyStaticI18n();

/* 提醒面板：默认收起，只留一行结论；点开才展开详因 */
const advToggle = $('adv-toggle');
if (advToggle) {
  advToggle.addEventListener('click', () => {
    S.advOpen = !S.advOpen;
    const card = $('advice-card');
    if (card) card.classList.toggle('collapsed', !S.advOpen);
  });
}

/* 页面隐藏时暂停重绘，回来再补一帧 */
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) schedule();
});

/* ---------------------------------------------------------- 启动 */
(async function boot() {
  try {
    const r = await fetch('/api/snapshot', { cache: 'no-store' });
    const d = await r.json();
    S.profile = d.profile || {};
    S.hist = d.history || [];
    if (d.latest) applySnapshot(d.latest, S.hist);
    setConn('live');
  } catch (_) {
    setConn('dead');
  }
  connect();
  // 兜底定时重绘（防止某帧丢帧）
  setInterval(schedule, 1000);
})();
