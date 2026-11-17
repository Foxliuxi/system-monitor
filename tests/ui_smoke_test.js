/**
 * UI 冒烟测试（Node 环境，DOM 桩）
 * 目的：在不启动浏览器的前提下验证
 *   1. app.js 里 getElementById 的每个 id 都真的存在于 index.html
 *   2. applySnapshot / 图表绘制 在真实数据结构下不抛异常
 * 运行：node tests/ui_smoke_test.js
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'web/index.html'), 'utf8');
const appSrc = fs.readFileSync(path.join(ROOT, 'web/app.js'), 'utf8');
const i18nSrc = fs.readFileSync(path.join(ROOT, 'web/i18n.js'), 'utf8');
const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixture_snapshot.json'), 'utf8'));

// HTML 中实际存在的 id
const htmlIds = new Set([...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]));
const queriedIds = [...appSrc.matchAll(/getElementById\('([^']+)'\)|\$\('([^']+)'\)/g)]
  .map((m) => m[1] || m[2]);

const missingIds = [...new Set(queriedIds)].filter((id) => !htmlIds.has(id));

// ---------------------------------------------------------------- DOM 桩
const ctxStub = new Proxy({}, {
  get(t, k) {
    if (k in t) return t[k];
    if (k === 'createLinearGradient') return () => ({ addColorStop() {} });
    if (k === 'measureText') return () => ({ width: 12 });
    if (k === 'canvas') return { width: 600, height: 168 };
    return () => {};
  },
  set(t, k, v) { t[k] = v; return true; },
});

const errors = [];

function simpleEl() {
  return {
    style: {}, className: '', dataset: {}, textContent: '', innerHTML: '',
    get firstElementChild() { return { style: {}, className: '' }; },
    set firstElementChild(v) {},
    classList: { add() {}, remove() {}, contains() { return false; } },
    animate() {},
    addEventListener() {},
    closest() { return { dataset: { n: '60' } }; },
  };
}

function mkEl(id) {
  const children = [];
  const el = {
    id, style: {}, dataset: {}, textContent: '', className: '',
    children,
    get childElementCount() { return children.length; },
    classList: { add() {}, remove() {}, contains() { return false; } },
    animate() {},
    addEventListener() {},
    appendChild(c) { children.push(c); },
    getBoundingClientRect() { return { width: 640, height: 168, top: 0, left: 0 }; },
    getContext() { return ctxStub; },
    get parentElement() { return { getBoundingClientRect: () => ({ width: 640, height: 168 }) }; },
    get firstElementChild() { return children[0] || null; },
    closest() { return { dataset: { n: '60' } }; },
  };
  Object.defineProperty(el, 'innerHTML', {
    get() { return el._html || ''; },
    set(v) {
      el._html = v;
      children.length = 0;
      const n = (String(v).match(/<(div|article|span)/g) || []).length;
      for (let i = 0; i < n; i++) children.push(simpleEl());
    },
  });
  return el;
}

const elCache = new Map();
const documentStub = {
  documentElement: { dataset: {} },
  hidden: false,
  getElementById(id) {
    if (!htmlIds.has(id)) { missingIds.push(id); return null; }
    if (!elCache.has(id)) elCache.set(id, mkEl(id));
    return elCache.get(id);
  },
  querySelectorAll() { return []; },   // 主题切换按钮：测试环境无样式层，返回空集合
  addEventListener() {},
};

// ---------------------------------------------------------------- 运行 i18n.js + app.js
let langStore = null;      // 测试里可以改写，用来验证切换语言
const sandbox = {
  console,
  document: documentStub,
  window: { devicePixelRatio: 1 },
  navigator: { language: 'zh-CN' },
  getComputedStyle: () => ({ getPropertyValue: () => '#22d3ee' }),
  localStorage: {
    getItem: (k) => (k === 'smon.lang' ? langStore : null),
    setItem: (k, v) => { if (k === 'smon.lang') langStore = v; },
  },
  ResizeObserver: class { observe() {} disconnect() {} },
  requestAnimationFrame: (cb) => { try { cb(); } catch (e) { errors.push('rAF: ' + e.message); } return 1; },
  setInterval: () => 0,
  setTimeout: () => 0,
  fetch: async () => ({ json: async () => fixture }),
  EventSource: class {
    constructor() { this.listeners = {}; }
    addEventListener(n, f) { this.listeners[n] = f; }
    close() {}
  },
  JSON, Math, Date, Object, Array, String, Number, isNaN, parseInt, parseFloat,
};

vm.createContext(sandbox);
// 语言包必须先加载：app.js 里所有文案都走 t()
try {
  vm.runInContext(i18nSrc, sandbox, { filename: 'i18n.js' });
} catch (e) {
  errors.push('加载 i18n.js 失败: ' + e.message);
}
try {
  vm.runInContext(appSrc, sandbox, { filename: 'app.js' });
} catch (e) {
  errors.push('加载 app.js 失败: ' + e.message + '\n' + (e.stack || ''));
}

// ---------------------------------------------------------------- 模拟数据推送
try {
  const fn = sandbox.applySnapshot;
  if (typeof fn !== 'function') {
    errors.push('applySnapshot 未在全局暴露，无法测试');
  } else {
    // 用真实快照跑首帧
    fn(fixture.latest, fixture.history);
    // 再模拟 5 个 tick，覆盖空值/丢包/极值边界
    const edge = {
      ...fixture.latest,
      net: { ...fixture.latest.net, down_mbps: 942.5, up_mbps: 0, down_bytes: 0 },
      latency: { gateway: null, public: null, dns_ms: null, tcp_ms: null },
      wifi: null,
      analysis: {
        ...fixture.latest.analysis,
        score: 0, grade: '较差',
        items: [{ level: 'critical', title: '测试', detail: 'd', advice: 'a', metric: null }],
        stats: { jitter: null, pub_avg: null, pub_loss_pct: null, gw_loss_pct: null },
      },
    };
    for (let i = 0; i < 5; i++) fn(edge, fixture.history);

    // 首帧场景：慢指标还没采到（gpu/thermal/disk/procs 全为 null），
    // 必须显示"采集中"而不是崩掉 —— 页面打开的头 1-2 秒就是这状态
    const cold = {
      ...fixture.latest,
      gpu: null, thermal: null, disk: null, procs: null,
    };
    fn(cold, []);

    // 显卡不可用场景（AMD/Intel 或驱动异常）
    fn({ ...fixture.latest, gpu: { available: false, reason: 'AMD 显卡无公开接口' } }, fixture.history);

    // 进程为空场景（首次采样，CPU 基线未建立）
    fn({ ...fixture.latest, procs: { cpu: [], mem: [], ts: 1, ready: false } }, fixture.history);
  }
} catch (e) {
  errors.push('applySnapshot 抛错: ' + e.message + '\n' + (e.stack || '').split('\n').slice(0, 4).join('\n'));
}

// ---------------------------------------------------------------- i18n 一致性
const i18nIssues = [];
try {
  const I = sandbox.I18N;
  const zhKeys = Object.keys(I.zh);
  const enKeys = Object.keys(I.en);
  const missEn = zhKeys.filter((k) => enKeys.indexOf(k) < 0);
  const extraEn = enKeys.filter((k) => zhKeys.indexOf(k) < 0);
  if (missEn.length) i18nIssues.push('英文缺 key: ' + missEn.join(', '));
  if (extraEn.length) i18nIssues.push('英文多出 key: ' + extraEn.join(', '));

  // app.js 里 t('...') 用到的 key 必须在字典里，拼错会静默回退中文。
  // 以 '.' 结尾的是运行时拼出来的（如 'grade.' + level），跳过
  const used = [...new Set([...appSrc.matchAll(/\bt\('([a-zA-Z0-9_.]+)'/g)].map((m) => m[1]))]
    .filter((k) => !k.endsWith('.'));
  const unknown = used.filter((k) => zhKeys.indexOf(k) < 0);
  if (unknown.length) i18nIssues.push('app.js 用了不存在的 key: ' + unknown.join(', '));

  // HTML 里的 data-i18n / data-i18n-title 也要存在
  const htmlKeys = [...new Set(
    [...html.matchAll(/data-i18n(?:-html|-title)?="([^"]+)"/g)].map((m) => m[1]))];
  const badHtml = htmlKeys.filter((k) => zhKeys.indexOf(k) < 0);
  if (badHtml.length) i18nIssues.push('HTML 用了不存在的 key: ' + badHtml.join(', '));

  // 英文模式整套渲染跑一遍，确认没有写死中文导致的分支报错
  langStore = 'en';
  if (sandbox.getLang() !== 'en') i18nIssues.push('设了 smon.lang=en 但 getLang 没跟上');
  if (typeof sandbox.applySnapshot === 'function') {
    sandbox.applySnapshot(fixture.latest, fixture.history);
    sandbox.applySnapshot({ ...fixture.latest, gpu: null, thermal: null, disk: null, procs: null }, []);
  }
  if (sandbox.t('card.gpu') !== 'GPU') {
    i18nIssues.push('英文下 card.gpu 应返回 GPU，实际 ' + sandbox.t('card.gpu'));
  }
  langStore = null;
} catch (e) {
  i18nIssues.push('i18n 检查抛错: ' + e.message);
}

// ---------------------------------------------------------------- 结果
const uniqMissing = [...new Set(missingIds)];
console.log('HTML 中 id 总数 :', htmlIds.size);
console.log('JS 引用 id 数   :', new Set(queriedIds).size);
console.log('语言包 key 数   :', Object.keys(sandbox.I18N.zh).length);
if (uniqMissing.length) {
  console.log('\n[FAIL] JS 引用了 HTML 中不存在的 id:');
  uniqMissing.forEach((i) => console.log('   - ' + i));
} else {
  console.log('[PASS] 所有 JS 引用的 id 都存在于 HTML');
}

if (i18nIssues.length) {
  console.log('\n[FAIL] i18n 一致性 ' + i18nIssues.length + ' 处:');
  i18nIssues.forEach((e) => console.log('   - ' + e));
} else {
  console.log('[PASS] 中英文 key 一致，无缺失/拼错，英文渲染无异常');
}

if (errors.length) {
  console.log('\n[FAIL] 运行时错误 ' + errors.length + ' 处:');
  errors.forEach((e) => console.log('   - ' + e));
  process.exitCode = 1;
} else {
  console.log('[PASS] applySnapshot + 图表绘制无异常');
}
process.exit(uniqMissing.length || errors.length || i18nIssues.length ? 1 : 0);
