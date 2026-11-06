// 把看板 HTML 整页导出成一张长图
// 用法: node export_long.js <html绝对路径> <输出png> [视口宽度=1080] [输出像素宽]
//   默认出高清图：视口 1080、输出 2160 宽（2x 像素，2026-10-19 起定为标准产物）。
//   第五个参数显式传 1080 才走「2x 栅格化后降采样」的老路径，体积小，给微信等低分辨率场景。
//
// 依赖 playwright-core 与一个 Chromium 内核浏览器，两者都按「环境变量 → PATH → 常见安装位置」找，
// 不写死任何机器路径，也不需要外部设 NODE_PATH。找不到时的报错会告诉你该装什么 / 该设哪个变量。
const path = require('path');
const fs = require('fs');
const os = require('os');

const HOME = os.homedir();
const IS_WIN = process.platform === 'win32';
const IS_MAC = process.platform === 'darwin';

// 找出「含 playwright-core 的 node_modules 目录」。顺序：环境变量 → 本地 → 全局 → 工具自带
function resolveNodeModules() {
  const has = dir => {
    try { return !!dir && fs.existsSync(path.join(dir, 'playwright-core')); } catch (e) { return false; }
  };
  const splitEnv = v => String(v).split(/[;:]/).map(s => s.trim()).filter(Boolean);

  for (const k of ['THERMO_NODE_MODULES', 'NODE_PATH']) {
    if (!process.env[k]) continue;
    for (const d of splitEnv(process.env[k])) if (has(d)) return d;
  }

  const cands = [
    path.join(__dirname, '..', 'node_modules'),   // skill 目录下 npm i
    path.resolve('node_modules'),                 // 当前工作目录
    path.join(HOME, '.workbuddy', 'binaries', 'node', 'workspace', 'node_modules'),
  ];
  // node 安装位置旁边的全局 node_modules
  const prefix = path.dirname(process.execPath);
  if (IS_WIN) {
    cands.push(path.join(prefix, 'node_modules'));
    cands.push(path.join(process.env.APPDATA || '', 'npm', 'node_modules'));
  } else {
    cands.push(path.join(prefix, '..', 'lib', 'node_modules'));
  }
  return cands.find(has) || null;
}

function loadPlaywright() {
  const dir = resolveNodeModules();
  const tries = dir ? [path.join(dir, 'playwright-core'), 'playwright-core'] : ['playwright-core'];
  for (const t of tries) {
    try { return require(t); } catch (e) { /* 继续下一个 */ }
  }
  return null;
}

const pw = loadPlaywright();
if (!pw) {
  console.error([
    '找不到 playwright-core。任选一种：',
    '  1) 在本 skill 目录执行  npm i playwright-core',
    '  2) 全局装：npm i -g playwright-core',
    '  3) 已装在别处：设环境变量 THERMO_NODE_MODULES=<含 playwright-core 的 node_modules 目录>',
  ].join('\n'));
  process.exit(1);
}
const { chromium } = pw;

// 浏览器：环境变量优先，其次按平台列一串常见位置
function resolveChrome() {
  for (const k of ['THERMO_CHROME', 'WB_CHROME', 'CHROME_PATH', 'CHROME_EXE']) {
    const v = process.env[k];
    if (v && fs.existsSync(v)) return v;
  }

  const home = HOME;
  const isWin = IS_WIN;
  const isMac = IS_MAC;
  const glob = (dir, prefix, suffix) => {
    try {
      return fs.readdirSync(dir)
        .filter(n => n.startsWith(prefix))
        .sort().reverse()                       // 版本号大的优先
        .map(n => path.join(dir, n, suffix))
        .filter(p => fs.existsSync(p));
    } catch (e) { return []; }
  };

  let cands = [];
  // 1) 浏览器自动化工具自带的 Chromium
  cands = cands.concat(glob(path.join(home, '.agent-browser', 'browsers'), 'chrome-',
    isWin ? 'chrome.exe' : 'chrome'));
  if (isWin) {
    cands = cands.concat(glob(path.join(home, 'AppData', 'Local', 'ms-playwright'), 'chromium-',
      path.join('chrome-win', 'chrome.exe')));
  } else if (isMac) {
    cands = cands.concat(glob(path.join(home, 'Library', 'Caches', 'ms-playwright'), 'chromium-',
      path.join('chrome-mac', 'Chromium.app', 'Contents', 'MacOS', 'Chromium')));
  } else {
    cands = cands.concat(glob(path.join(home, '.cache', 'ms-playwright'), 'chromium-',
      path.join('chrome-linux', 'chrome')));
  }

  // 2) 系统安装的 Chrome / Chromium
  if (isWin) {
    cands = cands.concat([
      path.join(process.env['ProgramFiles'] || 'C:\\Program Files', 'Google', 'Chrome', 'Application', 'chrome.exe'),
      path.join(process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)', 'Google', 'Chrome', 'Application', 'chrome.exe'),
      path.join(process.env['LOCALAPPDATA'] || '', 'Google', 'Chrome', 'Application', 'chrome.exe'),
    ]);
  } else if (isMac) {
    cands = cands.concat([
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      '/Applications/Chromium.app/Contents/MacOS/Chromium',
    ]);
  } else {
    cands = cands.concat(['/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser']);
  }

  let hit = cands.find(p => p && fs.existsSync(p));
  if (hit) return hit;

  // 3) 兜底：Windows 上 Edge 也是 Chromium 内核，出图效果一致
  if (isWin) {
    hit = [
      path.join(process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)', 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
      path.join(process.env['ProgramFiles'] || 'C:\\Program Files', 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
    ].find(p => fs.existsSync(p));
    if (hit) return hit;
  }
  return null;
}

const CHROME = resolveChrome();
if (!CHROME) {
  console.error([
    '找不到 Chrome / Chromium。任选一种：',
    '  1) 装 Google Chrome',
    '  2) 已有但不在默认位置：设环境变量 THERMO_CHROME=<浏览器可执行文件绝对路径>',
    '  3) npx playwright install chromium 装一份 Playwright 自带的',
  ].join('\n'));
  process.exit(1);
}

const HTML = process.argv[2];
const OUT = process.argv[3];
const W = parseInt(process.argv[4] || '1080', 10);
const PX = parseInt(process.argv[5] || String(W * 2), 10);

if (!HTML || !OUT) {
  console.error('usage: node export_long.js <html> <out.png> [cssWidth] [pixelWidth=2*cssWidth]');
  process.exit(1);
}

const DPR = Math.max(1, PX / W);
const HI_RES = PX > W;

(async () => {
  const browser = await chromium.launch({
    executablePath: CHROME,
    args: ['--allow-file-access-from-files'],
  });
  // 按 DPR 渲染：DPR=2 时字形以 2 倍分辨率栅格化。
  // 低分辨率平台（微信）用 scale:'css' 降采样回 CSS 尺寸，小字不糊；
  // 高压缩平台（小红书）用 scale:'device' 直接保留 2x 像素，二次压缩还有余量。
  const page = await browser.newPage({
    viewport: { width: W, height: 1400 },
    deviceScaleFactor: HI_RES ? DPR : 2,
  });
  await page.goto('file:///' + path.resolve(HTML).replace(/\\/g, '/'));
  await page.waitForTimeout(1500);

  // 1) 去掉网页外框：灰底 / 圆角 / 投影 → 干净的白底长图
  await page.addStyleTag({ content: `
    html,body{background:#FFFFFF !important;padding:0 !important;margin:0 !important;}
    .sheet{max-width:none !important;width:auto !important;border-radius:0 !important;
            box-shadow:none !important;margin:0 !important;padding:46px 46px 40px !important;}
  `});
  await page.waitForTimeout(400);

  // 2) 静态图里去掉“悬停 / 点击”这类失效的交互提示
  await page.evaluate(() => {
    const rep = (sel, from, to) => document.querySelectorAll(sel).forEach(el => {
      el.innerHTML = el.innerHTML.replace(from, to);
    });
    rep('.duo-note', '悬停曲线可看具体日期。', '');
    rep('.duo-note', '（悬停可看当日标的数）', '');
    rep('.hnote', '（悬停可看当日标的数）', '');
    rep('.sec-r', '点击表头可切换排序', '按行业温度降序');
  });
  await page.waitForTimeout(300);

  const h = await page.evaluate(() => document.documentElement.scrollHeight);
  console.log('page height =', h, 'css px');

  await page.screenshot({ path: path.resolve(OUT), fullPage: true, scale: HI_RES ? 'device' : 'css' });
  await browser.close();

  // 直接读 PNG 头拿尺寸（IHDR: 宽高各 4 字节大端），不依赖 Python/Pillow
  const buf = fs.readFileSync(path.resolve(OUT));
  const w = buf.readUInt32BE(16);
  const hgt = buf.readUInt32BE(20);
  console.log('saved', OUT, `(${w}, ${hgt})`);
})().catch(e => { console.error(e); process.exit(1); });
