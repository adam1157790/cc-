'use strict';

/* ============================================================
   学期倒数 · app.js
   四层架构：Config / DateUtils / UI / Main
   纯静态 · 零依赖 · file:// 双击可运行（刻意不用 ES Module）
   ============================================================ */

/* ==================== Config 层 ==================== */

var STORAGE_KEY = 'cc.countdown.config';

// 内置默认校历（2026-2027 学年）· 首次打开兜底
var DEFAULT_CALENDAR = {
  semesterStart: '2026-09-07',
  semesterEnd: '2027-01-15',
  nextSemesterStart: '2027-02-22'
};

// 读取配置：localStorage 为空 / 损坏 / 校验不通过时回退默认校历
function loadConfig() {
  var fallback = {
    semesterStart: DEFAULT_CALENDAR.semesterStart,
    semesterEnd: DEFAULT_CALENDAR.semesterEnd,
    nextSemesterStart: DEFAULT_CALENDAR.nextSemesterStart,
    isDefault: true
  };
  try {
    var raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return fallback;
    var cfg = JSON.parse(raw);
    if (!isValidCalendar(cfg)) return fallback;
    return {
      semesterStart: cfg.semesterStart,
      semesterEnd: cfg.semesterEnd,
      nextSemesterStart: cfg.nextSemesterStart,
      isDefault: false
    };
  } catch (err) {
    // 手动篡改或旧版数据导致的 JSON 解析错误：回退默认校历
    return fallback;
  }
}

// 写入配置（附 updatedAt，为 V2 多学期历史预留）
function saveConfig(cfg) {
  var data = {
    semesterStart: cfg.semesterStart,
    semesterEnd: cfg.semesterEnd,
    nextSemesterStart: cfg.nextSemesterStart,
    updatedAt: Date.now()
  };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch (err) {
    // 隐私模式或存储满：静默降级为"本次会话生效"，不阻塞用户
  }
}

// 校验字段合法性 + 顺序约束 S < E < N（ISO 字符串字典序即时间序）
function isValidCalendar(cfg) {
  if (!cfg) return false;
  var s = cfg.semesterStart,
      e = cfg.semesterEnd,
      n = cfg.nextSemesterStart;
  return isValidDateStr(s) &&
         isValidDateStr(e) &&
         isValidDateStr(n) &&
         s < e && e < n;
}

function isValidDateStr(str) {
  if (typeof str !== 'string') return false;
  var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(str);
  if (!m) return false;
  var y = +m[1], mo = +m[2], d = +m[3];
  var dt = new Date(y, mo - 1, d);
  return dt.getFullYear() === y &&
         dt.getMonth() === mo - 1 &&
         dt.getDate() === d;
}

/* ==================== DateUtils 层 ==================== */

// 关键：统一用本地时区构造日期。
// 禁用 new Date('YYYY-MM-DD')——它会按 UTC 解析，在中国时区偏移导致"少一天"。
function parseDate(str) {
  var p = str.split('-').map(Number);
  return new Date(p[0], p[1] - 1, p[2]);
}

function toDateStr(d) {
  var y = d.getFullYear();
  var mo = String(d.getMonth() + 1).padStart(2, '0');
  var day = String(d.getDate()).padStart(2, '0');
  return y + '-' + mo + '-' + day;
}

// 今天（本地零点，舍去时分秒）
function todayLocal() {
  var n = new Date();
  return new Date(n.getFullYear(), n.getMonth(), n.getDate());
}

// b - a 的天数差（跨 DST 用 round 吸收 23/25 小时误差）
function diffDays(a, b) {
  return Math.round((b - a) / 86400000);
}

// 距目标日期还有几天（不含今天）
function daysUntil(targetStr, t) {
  return diffDays(t, parseDate(targetStr));
}

// 状态机：核心业务逻辑。返回 { key, target, label, stateText }
//   T < S      → before  假期(未开学)   距 S 开学
//   S ≤ T ≤ E  → semester 学期中        距 E 结束
//   E < T < N  → holiday  假期(寒假)    距 N 开学
//   T ≥ N      → expired  校历过期      请更新
function getPhase(T, S, E, N) {
  var s = parseDate(S), e = parseDate(E), n = parseDate(N);
  if (T < s) {
    return { key: 'before', target: S, label: '距本学期开学', stateText: '⏳ 假期 · 新学期倒计时' };
  }
  if (T <= e) {
    return { key: 'semester', target: E, label: '距本学期结束', stateText: null };
  }
  if (T < n) {
    return { key: 'holiday', target: N, label: '距下学期开学', stateText: '🌸 假期 · 开学倒计时' };
  }
  return { key: 'expired', target: null, label: '', stateText: '🔄 校历已过期 · 请更新' };
}

// 学期第几周（S 当天为第 1 周）
function weekOf(T, S) {
  return Math.floor(diffDays(parseDate(S), T) / 7) + 1;
}

// 日期在学期轴 [S, N] 上的归一化位置，夹取到 [0, 1]
function timelinePos(dateStr, S, N) {
  var total = diffDays(parseDate(S), parseDate(N));
  if (total <= 0) return 0;
  return Math.max(0, Math.min(1, diffDays(parseDate(S), parseDate(dateStr)) / total));
}

// 格式化：'2026-09-07' → '9.07' / '2026.09.07'
function fmtMD(str) {
  var d = parseDate(str);
  return (d.getMonth() + 1) + '.' + String(d.getDate()).padStart(2, '0');
}
function fmtFull(str) {
  var d = parseDate(str);
  return d.getFullYear() + '.' +
         String(d.getMonth() + 1).padStart(2, '0') + '.' +
         String(d.getDate()).padStart(2, '0');
}

// 中文日期：'2026.09.07' → '2026年9月7日'
function fmtCN(d) {
  return d.getFullYear() + '年' + (d.getMonth() + 1) + '月' + d.getDate() + '日';
}

/* ==================== UI 层 ==================== */

var els = {};

function cacheDom() {
  els.tlFill = document.getElementById('tlFill');
  els.tlNodeStart = document.getElementById('tlNodeStart');
  els.tlNodeEnd = document.getElementById('tlNodeEnd');
  els.tlNodeNext = document.getElementById('tlNodeNext');
  els.tlToday = document.getElementById('tlToday');
  els.tlLabelToday = document.getElementById('tlLabelToday');
  els.lblStart = document.getElementById('tlLabelStart');
  els.lblEnd = document.getElementById('tlLabelEnd');
  els.lblNext = document.getElementById('tlLabelNext');

  els.phaseLine = document.getElementById('phaseLine');

  els.countdownBlock = document.getElementById('countdownBlock');
  els.countdownLabel = document.getElementById('countdownLabel');
  els.daysNum = document.getElementById('daysNum');
  els.countdownTarget = document.getElementById('countdownTarget');
  els.todayDate = document.getElementById('todayDate');
  els.expiredCard = document.getElementById('expiredCard');

  els.cardStart = document.getElementById('cardStart');
  els.cardEnd = document.getElementById('cardEnd');
  els.cardNext = document.getElementById('cardNext');
  els.dateStartVal = document.getElementById('dateStartVal');
  els.dateEndVal = document.getElementById('dateEndVal');
  els.dateNextVal = document.getElementById('dateNextVal');

  els.resetBtn = document.getElementById('resetBtn');
  els.expiredUpdateBtn = document.getElementById('expiredUpdateBtn');

  els.modal = document.getElementById('settingsModal');
  els.form = document.getElementById('settingsForm');
  els.formError = document.getElementById('formError');
  els.cancelBtn = document.getElementById('cancelBtn');
  els.toast = document.getElementById('toast');
}

// 全量渲染：读配置 → 算状态 → 画轴 → 画倒计时 → 画日期卡
function render() {
  var cfg = loadConfig();
  var T = todayLocal();
  var S = cfg.semesterStart,
      E = cfg.semesterEnd,
      N = cfg.nextSemesterStart;
  var phase = getPhase(T, S, E, N);
  var todayStr = toDateStr(T);

  document.body.dataset.phase = phase.key;

  // --- 学期轴 ---
  var posToday = timelinePos(todayStr, S, N);
  var posEnd = timelinePos(E, S, N);

  els.tlNodeStart.style.left = '0%';
  els.tlNodeEnd.style.left = (posEnd * 100) + '%';
  els.tlNodeNext.style.left = '100%';
  els.tlToday.style.left = (posToday * 100) + '%';
  els.tlFill.style.width = (posToday * 100) + '%';

  els.lblStart.style.left = '0%';
  els.lblEnd.style.left = (posEnd * 100) + '%';
  els.lblNext.style.left = '100%';
  els.lblStart.textContent = fmtMD(S);
  els.lblEnd.textContent = fmtMD(E);
  els.lblNext.textContent = fmtMD(N);

  // 「今天」标签：仅当今天严格落在轴内时显示，避免与节点标签重叠
  els.tlLabelToday.style.left = (posToday * 100) + '%';
  els.tlLabelToday.hidden = !(posToday > 0.005 && posToday < 0.995);

  // --- 日期节点卡 ---
  els.dateStartVal.textContent = fmtMD(S);
  els.dateEndVal.textContent = fmtMD(E);
  els.dateNextVal.textContent = fmtMD(N);
  els.cardStart.classList.toggle('is-today', S === todayStr);
  els.cardEnd.classList.toggle('is-today', E === todayStr);
  els.cardNext.classList.toggle('is-today', N === todayStr);

  // --- 状态行 ---
  els.phaseLine.textContent = phase.key === 'semester'
    ? '📖 学期中 · 第' + weekOf(T, S) + '周'
    : '▸ ' + phase.stateText;

  // --- 倒计时 / 过期卡片 ---
  if (phase.key === 'expired') {
    els.countdownBlock.hidden = true;
    els.expiredCard.hidden = false;
  } else {
    els.countdownBlock.hidden = false;
    els.expiredCard.hidden = true;
    els.countdownLabel.textContent = phase.label;
    els.daysNum.textContent = String(daysUntil(phase.target, T));
    els.countdownTarget.textContent = '目标日 ' + fmtFull(phase.target);
    els.todayDate.textContent = '今天 ' + fmtCN(T);
  }
}

/* ---------- 弹窗交互 ---------- */

function openSettings() {
  var cfg = loadConfig();
  els.form.elements.semesterStart.value = cfg.semesterStart;
  els.form.elements.semesterEnd.value = cfg.semesterEnd;
  els.form.elements.nextSemesterStart.value = cfg.nextSemesterStart;
  clearFieldErrors();
  els.modal.hidden = false;
  els.form.elements.semesterStart.focus();
}

function closeSettings() {
  els.modal.hidden = true;
  els.resetBtn.focus();
}

// 校验三个日期，返回错误对象或 null
function validateDates(S, E, N) {
  if (!S || !E || !N) {
    return { text: '请填写全部三个日期', field: null };
  }
  if (!isValidDateStr(S) || !isValidDateStr(E) || !isValidDateStr(N)) {
    return { text: '日期格式不正确', field: null };
  }
  var s = parseDate(S), e = parseDate(E), n = parseDate(N);
  if (e <= s) {
    return { text: '本学期结束必须晚于本学期开始（至少间隔 1 天）', field: 'semesterEnd' };
  }
  if (n <= e) {
    return { text: '下学期开学必须晚于本学期结束（至少间隔 1 天）', field: 'nextSemesterStart' };
  }
  return null;
}

function clearFieldErrors() {
  els.formError.hidden = true;
  els.formError.textContent = '';
  var inputs = els.form.querySelectorAll('input.invalid');
  Array.prototype.forEach.call(inputs, function (el) {
    el.classList.remove('invalid');
  });
}

function onSubmit(e) {
  e.preventDefault();
  var S = els.form.elements.semesterStart.value;
  var E = els.form.elements.semesterEnd.value;
  var N = els.form.elements.nextSemesterStart.value;

  clearFieldErrors();
  var err = validateDates(S, E, N);
  if (err) {
    els.formError.textContent = err.text;
    els.formError.hidden = false;
    if (err.field) els.form.elements[err.field].classList.add('invalid');
    return; // 校验失败：红框提示，表单不关闭
  }

  saveConfig({ semesterStart: S, semesterEnd: E, nextSemesterStart: N });
  closeSettings();
  render();
  showToast('已保存 · 校历旅程已更新');
}

function bindEvents() {
  els.resetBtn.addEventListener('click', openSettings);
  els.expiredUpdateBtn.addEventListener('click', openSettings);
  els.cancelBtn.addEventListener('click', closeSettings);
  els.modal.addEventListener('click', function (e) {
    if (e.target === els.modal) closeSettings(); // 点遮罩关闭
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !els.modal.hidden) closeSettings();
  });
  els.form.addEventListener('submit', onSubmit);

  // 编辑时即时清除错误态
  ['semesterStart', 'semesterEnd', 'nextSemesterStart'].forEach(function (name) {
    els.form.elements[name].addEventListener('input', function () {
      this.classList.remove('invalid');
      els.formError.hidden = true;
    });
  });
}

/* ---------- Toast ---------- */

var toastTimer = null;

function showToast(msg) {
  els.toast.textContent = msg;
  els.toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(function () {
    els.toast.classList.remove('show');
  }, 2400);
}

/* ==================== Main 层 ==================== */

function init() {
  cacheDom();
  bindEvents();
  render();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
