/* ==========================================================
   系统实时监测 · 语言包
   设计取舍：
     · 用扁平 key + 一个 t()，不引框架、不引构建步骤（这个项目零依赖）
     · 字典直接内联，不异步加载——语言切换要立即生效，不能白屏一下
     · 缺 key 时回退中文（宁可看到中文，也不要看到 "i18n.missing.key"）
   ========================================================== */
'use strict';

const I18N = {
  /* ------------------------------------------------------------------ 中文 */
  zh: {
    'app.title': '系统实时监测',
    'app.subline.collecting': '正在采集…',

    'top.grade.evaluating': '评估中',
    'top.health': '健康评分',
    'top.theme.hint': '切换配色：副屏看不清时试试「亮」',
    'top.theme.dark': '暗',
    'top.theme.light': '亮',
    'top.lang.hint': '切换界面语言（中 / EN）',
    'conn.connecting': '连接中',
    'conn.live': '实时采集中',
    'conn.dead': '连接断开，重试中',

    'kpi.cpu': 'CPU',
    'kpi.gpu': '显卡',
    'kpi.mem': '内存',
    'kpi.disk': '磁盘 I/O',
    'kpi.down': '下行',
    'kpi.lat': '延迟',
    'kpi.loss': '丢包',
    'kpi.cpu.sub': '{threads} 线程',
    'kpi.gpu.sub': '{temp} · 显存 {used}/{total}G',
    'kpi.gpu.notemp': '温度未知',
    'kpi.gpu.off': '不可用',
    'kpi.gpu.wait': '采集中',
    'kpi.disk.sub': '读 {r} / 写 {w} MB/s',
    'kpi.down.sub': '上行 {up} Mbps · {bytes}',
    'kpi.lat.sub': '网关 {gw}ms · DNS {dns}ms',
    'kpi.loss.probing': '探测中',
    'kpi.loss.sub': '超时 {to}/{att} 次 · 网关 {gw}%',
    'kpi.loss.err': '{err} 次失败',
    'kpi.loss.tip': '探测目标 {target}　超时窗口 {timeout}ms\n有效探测 {att} 次，其中超时 {to} 次，发包失败 {err} 次\n丢包率 = 超时 ÷ 有效探测；发包失败不计入',

    'sec.system': '系统资源',
    'sec.network': '网络状态',

    'card.cpu': 'CPU',
    'card.gpu': '显卡',
    'card.mem': '内存',
    'card.disk': '硬盘',
    'card.temp': '温度',
    'card.proc': '进程监控',
    'card.thru': '实时吞吐',
    'card.lat': '延迟趋势',
    'card.link': '链路',

    'grade.critical': '严重',
    'grade.warn': '注意',
    'grade.info': '提示',
    'grade.ok': '正常',
    'grade.excellent': '优秀',
    'grade.good': '良好',
    'grade.fair': '一般',
    'grade.poor': '较差',
    'adv.none': '暂无分析结论',
    'adv.wait': '等待分析…',
    'adv.count.crit': '{crit} 项严重 · {warn} 项注意',
    'adv.count.warn': '{warn} 项待改善',
    'adv.count.ok': '无异常',
    'adv.howto': '怎么做',

    'cpu.badge.nofreq': '频率不可读',
    'cpu.foot': '{threads} 线程 · {state}',
    'cpu.state.full': '已满载',
    'cpu.state.high': '负载偏高',
    'cpu.state.normal': '负载正常',
    'cpu.state.throttle': ' · 降频中',

    'mem.used': '已用',
    'mem.free': '可用',
    'mem.top': '占用最高',
    'mem.pressured': '内存压力偏大，缓冲区可能被压缩',
    'mem.ok': '内存充足，不影响网络缓冲',

    'gpu.unavailable': '显卡实时数据不可用',
    'gpu.noiface': '未检测到可用的显卡监控接口',
    'gpu.count': '{n} 张显卡',
    'gpu.util': 'GPU 利用率',
    'gpu.coretemp': '核心温度',
    'gpu.vram': '显存',
    'gpu.power': '功耗',
    'gpu.fan': '风扇转速',
    'gpu.clock': '核心频率',
    'gpu.membw': '显存带宽占用',

    'temp.collecting': '采集中…（温度按 15 秒周期采集）',
    'temp.na': '不可用',
    'temp.gpu': '显卡 GPU',
    'temp.board': '主板',
    'temp.diskmax': '硬盘 最高',
    'temp.diskcount': '{n} 块盘',
    'temp.disk': '硬盘',
    'temp.nodata': '无数据',
    'temp.note.lhm': '来源 LHM · 15 秒',
    'temp.foot.lhm': 'CPU / 主板 / 硬盘温度由 LibreHardwareMonitor 读取（它需常驻托盘）。LHM 未运行时自动回退到 ACPI，读不到则如实标不可用。',
    'temp.note.nolhm': '温度源未连接',
    'temp.foot.nolhm': '启动温度组件（开始菜单里的 LibreHardwareMonitor，或程序目录下的 LibreHardwareMonitor.exe），UAC 点「是」。它常驻托盘，温度就在；关掉它就断。',
    'temp.note.plain': '每 15 秒刷新',
    'temp.foot.plain': '温度是慢变量，按 15 秒周期采集，不拖慢其他指标。',

    'disk.io': '读 {r} / 写 {w} MB/s',
    'disk.used': '已用 {pct}%',
    'disk.free': '可用 {v}',
    'disk.healthy': '全部健康',
    'disk.bad': '{n} 块盘健康异常',
    'disk.reading': '物理磁盘信息读取中…',

    'rank.empty': '无数据',
    'rank.probing': '采样中…首次需 2 秒建立 CPU 时间基线',
    'rank.waiting': '采样中…',
    'rank.note': '同名已合并 · Top 10 · {state}',
    'rank.note.live': '每 5 秒刷新',
    'rank.note.baseline': '建立基线中',
    'rank.head.cpu': 'CPU 占用',
    'rank.head.mem': '内存占用',

    'link.nic': '网卡',
    'link.type': '类型',
    'link.wireless': '无线',
    'link.wired': '有线',
    'link.speed': '链路',
    'link.up': '上行',
    'link.conns': '连接',
    'link.count': '{n} 条',
    'link.jitter': '抖动',
    'link.signal': '信号',
    'link.band': '频段',
    'link.radio': '协议',
    'link.channel': '信道',
    'link.nego': '协商',
    'link.gateway': '网关',
    'link.err': '错误/丢弃',
    'link.total': '累计',
    'link.spare': '可插线提速',
    'link.spare.detail': '{desc} · {speed} Mbps 未连接',
    'link.unknown': '未知',
    'link.wifi': '无线接入',
    'link.wiredap': '有线接入',

    'foot.sample': '1s 采样',
    'foot.uptime': '运行 {t}',
    'foot.privacy': '仅本机 · 数据不上传',

    'range.1m': '1分',
    'range.5m': '5分',
    'range.15m': '15分',

    'unit.down': '下行',
    'unit.up': '上行',
    'unit.gw': '网关',
    'unit.pub': '公网',
  },

  /* ------------------------------------------------------------------ 英文 */
  en: {
    'app.title': 'System Monitor',
    'app.subline.collecting': 'Collecting…',

    'top.grade.evaluating': 'Evaluating',
    'top.health': 'Health score',
    'top.theme.hint': 'Switch palette — try "Light" if your monitor is dim',
    'top.theme.dark': 'Dark',
    'top.theme.light': 'Light',
    'top.lang.hint': 'Switch language (中文 / EN)',
    'conn.connecting': 'Connecting',
    'conn.live': 'Live',
    'conn.dead': 'Disconnected — retrying',

    'kpi.cpu': 'CPU',
    'kpi.gpu': 'GPU',
    'kpi.mem': 'Memory',
    'kpi.disk': 'Disk I/O',
    'kpi.down': 'Download',
    'kpi.lat': 'Latency',
    'kpi.loss': 'Loss',
    'kpi.cpu.sub': '{threads} threads',
    'kpi.gpu.sub': '{temp} · VRAM {used}/{total}G',
    'kpi.gpu.notemp': 'temp n/a',
    'kpi.gpu.off': 'n/a',
    'kpi.gpu.wait': 'collecting',
    'kpi.disk.sub': 'R {r} / W {w} MB/s',
    'kpi.down.sub': 'Upload {up} Mbps · {bytes}',
    'kpi.lat.sub': 'Gateway {gw}ms · DNS {dns}ms',
    'kpi.loss.probing': 'probing',
    'kpi.loss.sub': 'timeout {to}/{att} · gateway {gw}%',
    'kpi.loss.err': '{err} send failures',
    'kpi.loss.tip': 'Target {target}　timeout window {timeout}ms\n{att} valid probes, {to} timed out, {err} send failures\nLoss = timeouts ÷ valid probes; send failures excluded',

    'sec.system': 'System',
    'sec.network': 'Network',

    'card.cpu': 'CPU',
    'card.gpu': 'GPU',
    'card.mem': 'Memory',
    'card.disk': 'Storage',
    'card.temp': 'Temperature',
    'card.proc': 'Processes',
    'card.thru': 'Throughput',
    'card.lat': 'Latency',
    'card.link': 'Link',

    'grade.critical': 'Critical',
    'grade.warn': 'Warning',
    'grade.info': 'Info',
    'grade.ok': 'OK',
    'grade.excellent': 'Excellent',
    'grade.good': 'Good',
    'grade.fair': 'Fair',
    'grade.poor': 'Poor',
    'adv.none': 'No findings yet',
    'adv.wait': 'Waiting for analysis…',
    'adv.count.crit': '{crit} critical · {warn} warning',
    'adv.count.warn': '{warn} to improve',
    'adv.count.ok': 'No issues',
    'adv.howto': 'What to do',

    'cpu.badge.nofreq': 'frequency n/a',
    'cpu.foot': '{threads} threads · {state}',
    'cpu.state.full': 'fully loaded',
    'cpu.state.high': 'high load',
    'cpu.state.normal': 'normal load',
    'cpu.state.throttle': ' · throttling',

    'mem.used': 'Used',
    'mem.free': 'Free',
    'mem.top': 'Top consumer',
    'mem.pressured': 'Memory pressure is high — socket buffers may be compressed',
    'mem.ok': 'Plenty of memory — no effect on network buffers',

    'gpu.unavailable': 'GPU data unavailable',
    'gpu.noiface': 'No usable GPU monitoring interface detected',
    'gpu.count': '{n} GPUs',
    'gpu.util': 'GPU utilization',
    'gpu.coretemp': 'Core temp',
    'gpu.vram': 'VRAM',
    'gpu.power': 'Power',
    'gpu.fan': 'Fan',
    'gpu.clock': 'Core clock',
    'gpu.membw': 'VRAM bandwidth',

    'temp.collecting': 'Collecting… (temperatures refresh every 15s)',
    'temp.na': 'n/a',
    'temp.gpu': 'GPU',
    'temp.board': 'Motherboard',
    'temp.diskmax': 'Storage (max)',
    'temp.diskcount': '{n} drives',
    'temp.disk': 'Storage',
    'temp.nodata': 'no data',
    'temp.note.lhm': 'via LHM · 15s',
    'temp.foot.lhm': 'CPU / motherboard / drive temperatures come from LibreHardwareMonitor, which must stay running in the tray. If it stops, the app falls back to ACPI and reports "n/a" honestly.',
    'temp.note.nolhm': 'Temperature source offline',
    'temp.foot.nolhm': 'Start LibreHardwareMonitor (Start menu, or LibreHardwareMonitor.exe inside the app folder) and accept the UAC prompt. It stays in the tray; close it and readings stop.',
    'temp.note.plain': 'Refresh every 15s',
    'temp.foot.plain': 'Temperature is a slow variable — sampled every 15s so it never slows other metrics.',

    'disk.io': 'R {r} / W {w} MB/s',
    'disk.used': 'Used {pct}%',
    'disk.free': 'Free {v}',
    'disk.healthy': 'all healthy',
    'disk.bad': '{n} drive(s) unhealthy',
    'disk.reading': 'Reading physical disk info…',

    'rank.empty': 'No data',
    'rank.probing': 'Sampling… first CPU sample needs 2s of baseline',
    'rank.waiting': 'Sampling…',
    'rank.note': 'Merged by name · Top 10 · {state}',
    'rank.note.live': 'refresh 5s',
    'rank.note.baseline': 'building baseline',
    'rank.head.cpu': 'CPU usage',
    'rank.head.mem': 'Memory',

    'link.nic': 'NIC',
    'link.type': 'Type',
    'link.wireless': 'Wireless',
    'link.wired': 'Wired',
    'link.speed': 'Link',
    'link.up': 'Upload',
    'link.conns': 'Conns',
    'link.count': '{n}',
    'link.jitter': 'Jitter',
    'link.signal': 'Signal',
    'link.band': 'Band',
    'link.radio': 'Radio',
    'link.channel': 'Channel',
    'link.nego': 'Negotiated',
    'link.gateway': 'Gateway',
    'link.err': 'Err/Drop',
    'link.total': 'Total',
    'link.spare': 'Wired port idle',
    'link.spare.detail': '{desc} · {speed} Mbps not connected',
    'link.unknown': 'unknown',
    'link.wifi': 'Wi-Fi',
    'link.wiredap': 'Wired',

    'foot.sample': '1s sampling',
    'foot.uptime': 'up {t}',
    'foot.privacy': 'Local only · nothing uploaded',

    'range.1m': '1m',
    'range.5m': '5m',
    'range.15m': '15m',

    'unit.down': 'Down',
    'unit.up': 'Up',
    'unit.gw': 'Gateway',
    'unit.pub': 'Public',
  },
};

const LANG_KEY = 'smon.lang';
const SUPPORTED = ['zh', 'en'];

function getLang() {
  let v = null;
  try { v = localStorage.getItem(LANG_KEY); } catch (_) { /* 隐私模式 */ }
  if (SUPPORTED.indexOf(v) >= 0) return v;
  // 没设过就跟随浏览器：非中文环境默认英文，避免中文乱码方块
  const nav = (navigator.language || 'zh').toLowerCase();
  return nav.indexOf('zh') === 0 ? 'zh' : 'en';
}

function setLang(lang) {
  const v = SUPPORTED.indexOf(lang) >= 0 ? lang : 'zh';
  try { localStorage.setItem(LANG_KEY, v); } catch (_) { /* 忽略 */ }
  document.documentElement.lang = v === 'zh' ? 'zh-CN' : 'en';
  return v;
}

/** 取文案。vars 用 {name} 占位，缺失的 key 回退中文，再缺失返回 key 本身 */
function t(key, vars) {
  const lang = getLang();
  let s = (I18N[lang] && I18N[lang][key]);
  if (s === undefined) s = I18N.zh[key];
  if (s === undefined) return key;
  if (vars) {
    for (const k in vars) {
      s = s.split('{' + k + '}').join(String(vars[k]));
    }
  }
  return s;
}

/** 套用 HTML 里的静态文案：data-i18n / data-i18n-title / data-i18n-html */
function applyStaticI18n() {
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll('[data-i18n-html]').forEach((el) => {
    el.innerHTML = t(el.dataset.i18nHtml);
  });
  document.querySelectorAll('[data-i18n-title]').forEach((el) => {
    el.title = t(el.dataset.i18nTitle);
  });
  document.title = t('app.title');
  document.querySelectorAll('[data-lang-set]').forEach((b) => {
    b.classList.toggle('on', b.dataset.langSet === getLang());
  });
}

/* const 声明只存在于上下文的词法作用域里，不会变成全局对象属性。
   浏览器里 script 之间共享词法环境，不暴露也能用；但测试脚本（Node vm）
   需要从外部读到字典，这里显式挂一份。 */
if (typeof globalThis === 'object') globalThis.I18N = I18N;
