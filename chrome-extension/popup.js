const API_BASE = 'http://localhost:5001';

const btnCapture = document.getElementById('btnCapture');
const btnSave = document.getElementById('btnSave');
const btnView = document.getElementById('btnView');
const btnLogin = document.getElementById('btnLogin');
const actionButtons = document.getElementById('actionButtons');
const statusEl = document.getElementById('status');
const resultsEl = document.getElementById('results');
const rawTextEl = document.getElementById('rawText');
const previewArea = document.getElementById('previewArea');
const previewImg = document.getElementById('previewImg');
const loginBanner = document.getElementById('loginBanner');
const loginUsername = document.getElementById('loginUsername');
const loginPassword = document.getElementById('loginPassword');
const loginBannerError = document.getElementById('loginBannerError');

let currentItems = [];
let currentFlatItems = [];
let lastSavedObjectId = null;

const backupToggle = document.getElementById('backupToggle');
chrome.storage.local.get('__backupScreenshot', (data) => {
  backupToggle.checked = data.__backupScreenshot !== false;
});
backupToggle.addEventListener('change', () => {
  chrome.storage.local.set({ __backupScreenshot: backupToggle.checked });
});

function isLoggedIn() { return !!window.__authToken; }

function setStatus(msg, type) {
  statusEl.textContent = msg;
  statusEl.className = 'status status-' + type;
}

function show(el) { el.classList.remove('hidden'); }
function hide(el) { el.classList.add('hidden'); }

function clearOcrStorage() {
  chrome.storage.local.remove(['__ocrResults', '__ocrRawLines', '__ocrError', '__ocrPreview']);
}

// 检查登录状态
async function checkAuth() {
  try {
    const resp = await fetch(API_BASE + '/api/auth-status');
    const data = await resp.json();
    if (data.logged_in) {
      window.__authToken = 'session';
      hide(loginBanner);
      return true;
    }
  } catch(e) {}
  // 尝试从 storage 获取保存的登录信息
  const stored = await chrome.storage.local.get(['__authUsername', '__authPassword']);
  if (stored.__authUsername && stored.__authPassword) {
    const ok = await tryLogin(stored.__authUsername, stored.__authPassword);
    if (ok) return true;
  }
  show(loginBanner);
  return false;
}

async function tryLogin(username, password) {
  try {
    const body = username ? {username: username, password: password} : {password: password};
    const resp = await fetch(API_BASE + '/api/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)
    });
    const data = await resp.json();
    if (data.ok) {
      window.__authToken = password;
      window.__authUsername = username;
      chrome.storage.local.set({ __authUsername: username, __authPassword: password });
      hide(loginBanner);
      return true;
    }
  } catch(e) {}
  return false;
}

// 为 API 请求添加用户名/密码参数
async function apiFetch(url, options) {
  const body = options.body ? JSON.parse(options.body) : {};
  if (window.__authToken && window.__authToken !== 'session') {
    body.password = window.__authToken;
    if (window.__authUsername) body.username = window.__authUsername;
  }
  return fetch(url, {
    method: options.method || 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
}

function doLogin() {
  const uname = loginUsername.value.trim();
  const pw = loginPassword.value;
  loginBannerError.textContent = '';
  hide(loginBannerError);
  if (!uname && !pw) { loginBannerError.textContent = '请输入用户名和密码'; show(loginBannerError); return; }
  if (!pw) { loginBannerError.textContent = '请输入密码'; show(loginBannerError); return; }
  btnLogin.disabled = true;
  btnLogin.textContent = '验证中...';
  tryLogin(uname || '', pw).then(function(ok) {
    btnLogin.disabled = false;
    btnLogin.textContent = '登录';
    if (ok) {
      setStatus('', '');
      statusEl.classList.add('hidden');
    } else {
      loginBannerError.textContent = '用户名或密码错误';
      show(loginBannerError);
    }
  });
}

loginPassword.addEventListener('keydown', function(e) {
  if (e.key === 'Enter') doLogin();
});

btnLogin.addEventListener('click', doLogin);

// 打开时检查登录状态和待展示的结果
(async function init() {
  const loggedIn = await checkAuth();
  if (!loggedIn) {
    setStatus('需要登录才能使用', 'warning');
  }
  // 后续加载由存储监听处理
})();

chrome.storage.local.get(['__ocrResults', '__ocrError', '__ocrRawLines', '__ocrPreview'], (data) => {
  if (data.__ocrError) {
    setStatus(data.__ocrError, 'error');
    clearOcrStorage();
    return;
  }
  if (data.__ocrPreview) {
    previewImg.src = data.__ocrPreview;
    show(previewArea);
  }
  if (data.__ocrResults && data.__ocrResults.length > 0) {
    currentItems = data.__ocrResults;
    showResultItems(currentItems);
    show(btnSave);
    clearOcrStorage();
  } else if (data.__ocrRawLines && data.__ocrRawLines.length > 0) {
    setStatus('未识别到巡检记录', 'warning');
    rawTextEl.textContent = data.__ocrRawLines.join('\n');
    show(rawTextEl);
    clearOcrStorage();
  }
});

// 监听实时变化
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== 'local') return;

  if (changes.__ocrError && changes.__ocrError.newValue) {
    setStatus(changes.__ocrError.newValue, 'error');
  }

  if (changes.__ocrPreview && changes.__ocrPreview.newValue) {
    previewImg.src = changes.__ocrPreview.newValue;
    show(previewArea);
  }

  if (changes.__ocrResults && changes.__ocrResults.newValue) {
    const items = changes.__ocrResults.newValue;
    currentItems = items;
    if (items.length > 0) {
      showResultItems(items);
      show(btnSave);
      clearOcrStorage();
    } else {
      setStatus('未识别到巡检记录', 'warning');
    }
  }

  if (changes.__ocrRawLines && changes.__ocrRawLines.newValue) {
    const lines = changes.__ocrRawLines.newValue;
    if (lines.length > 0 && currentItems.length === 0) {
      rawTextEl.textContent = lines.join('\n');
      show(rawTextEl);
    }
  }
});

// 点击按钮
btnCapture.addEventListener('click', async () => {
  if (!isLoggedIn()) {
    setStatus('请先登录系统', 'error');
    show(loginBanner);
    return;
  }
  btnCapture.disabled = true;
  btnCapture.innerHTML = '<span class="spinner"></span><span>框选中...</span>';
  setStatus('请在页面上框选区域，松开后自动识别...', 'info');
  resultsEl.innerHTML = '';
  hide(rawTextEl);
  hide(btnSave);
  hide(previewArea);
  currentItems = [];
  currentFlatItems = [];
  clearOcrStorage();

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) {
      setStatus('未找到活动标签页', 'error');
      resetCaptureBtn();
      return;
    }

    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ['content.js']
    });
    await chrome.scripting.insertCSS({
      target: { tabId: tab.id },
      files: ['content.css']
    });

    setTimeout(resetCaptureBtn, 500);
  } catch (e) {
    setStatus('无法注入脚本: ' + e.message, 'error');
    resetCaptureBtn();
  }
});

function resetCaptureBtn() {
  btnCapture.disabled = false;
  btnCapture.innerHTML = `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M15 3h6v6"/><path d="M9 21H3v-6"/><path d="M21 3l-7 7"/><path d="M3 21l7-7"/>
    </svg>
    <span>框选截图识别</span>
  `;
}

function escHtml(s) {
  var d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}
function escAttr(s) {
  return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function showResultItems(ocrItems) {
  currentFlatItems = [];
  let html = '';

  ocrItems.forEach((item, itemIdx) => {
    const label = item.point_name || item.location || '巡检记录';
    const location = item.location || '';
    const result = item.result || '';
    const resultClass = result === '正常' ? 'tag-ok' : result === '异常' ? 'tag-err' : 'tag-warn';

    html += `<div class="result-group">`;
    html += `<div class="result-group-header">
      <span class="result-group-name">${label}</span>
      ${location ? `<span class="result-group-loc">${location}</span>` : ''}
      ${result ? `<span class="result-tag ${resultClass}">${result}</span>` : ''}
    </div>`;

    const metrics = item.metrics || {};
    const keys = Object.keys(metrics);
    if (keys.length === 0) {
      html += `<div class="result-item"><div class="result-info"><span class="result-name">无指标数据</span></div></div>`;
    } else {
      keys.forEach((key) => {
        const val = metrics[key];
        const flatIdx = currentFlatItems.length;
        currentFlatItems.push({ metricKey: key, value: val, _itemIdx: itemIdx });
        const numVal = val != null ? parseFloat(String(val).replace(/[^0-9.\-]/g, '')) : '';
        const itemVirtualKeys = item.virtual_keys || [];
        const isVirtual = itemVirtualKeys.indexOf(key) !== -1;
        html += '<div class="result-item">' +
          '<div class="result-info">' +
          '<span class="result-name">' + escHtml(key) + '</span>' +
          '<span class="result-val" id="val-' + flatIdx + '">' + (val != null ? escHtml(String(val)) : '') + '</span>' +
          '</div>';
        if (isVirtual) {
          html += '<span style="font-size:0.7rem;color:var(--text-faint);padding:0.25rem 0.5rem;">计算类</span>';
        } else {
          html += '<input class="result-edit" id="edit-' + flatIdx + '" type="number" step="any" placeholder="' + escAttr(key) + '" value="' + (numVal !== '' && !isNaN(numVal) ? numVal : '') + '" data-flat="' + flatIdx + '" onchange="onEditValue(this)">';
        }
        html += '</div>';
      });
    }
    html += `</div>`;
  });

  const totalCount = ocrItems.length;
  setStatus(`识别到 ${totalCount} 条记录`, 'success');
  resultsEl.innerHTML = html;
  show(actionButtons);
  hide(btnView);
}

window.onEditValue = function(el) {
  const flatIdx = parseInt(el.dataset.flat);
  const val = parseFloat(el.value);
  if (!isNaN(val) && currentFlatItems[flatIdx]) {
    const original = currentFlatItems[flatIdx].value;
    const hasPct = typeof original === 'string' && original.trim().endsWith('%');
    currentFlatItems[flatIdx].value = hasPct ? val + '%' : val;
    const itemIdx = currentFlatItems[flatIdx]._itemIdx;
    const metricKey = currentFlatItems[flatIdx].metricKey;
    currentItems[itemIdx].metrics[metricKey] = hasPct ? val + '%' : val;
    document.getElementById('val-' + flatIdx).textContent = hasPct ? val + '%' : val;
  }
};

btnSave.addEventListener('click', async () => {
  setStatus('保存中...', 'info');
  btnSave.disabled = true;

  try {
    const resp = await apiFetch(API_BASE + '/api/save', {
      method: 'POST',
      body: JSON.stringify({ items: currentItems })
    });
    const data = await resp.json();

    if (data.error) {
      setStatus('保存失败: ' + data.error, 'error');
      return;
    }

    let msg = `成功保存 ${data.saved} 条`;
    if (data.created > 0) msg += `，新建 ${data.created} 个位置`;
    if (data.skipped_no_match > 0) msg += `，${data.skipped_no_match} 条未匹配`;
    if (data.skipped_duplicate > 0) msg += `，${data.skipped_duplicate} 条重复`;
    if (data.skipped_incomplete > 0) {
      var reasons = (data.skipped_reasons || []).map(r => `${r.name}: ${r.reason}`).join('\n');
      msg += `\n\n⚠ ${data.skipped_incomplete} 条指标不完整跳过:\n${reasons}`;
    }
    setStatus(msg, data.skipped_incomplete > 0 ? 'warning' : 'success');

    // 记录保存的 object_id 用于跳转
    if (data.object_id) {
      lastSavedObjectId = data.object_id;
    }

    hide(btnSave);
    show(btnView);
    currentFlatItems = [];
  } catch (e) {
    setStatus('保存失败: ' + e.message, 'error');
  }
  btnSave.disabled = false;
});

// 点击查看按钮跳转到详情页
btnView.addEventListener('click', () => {
  if (lastSavedObjectId) {
    chrome.tabs.create({ url: API_BASE + '/object/' + lastSavedObjectId });
  } else {
    chrome.tabs.create({ url: API_BASE });
  }
});
