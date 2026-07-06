const API_BASE = 'http://localhost:5001';

const btnCapture = document.getElementById('btnCapture');
const btnSave = document.getElementById('btnSave');
const statusEl = document.getElementById('status');
const resultsEl = document.getElementById('results');
const rawTextEl = document.getElementById('rawText');
const previewArea = document.getElementById('previewArea');
const previewImg = document.getElementById('previewImg');

let currentItems = [];
let currentFlatItems = [];

function setStatus(msg, type) {
  statusEl.textContent = msg;
  statusEl.className = 'status status-' + type;
}

function show(el) { el.classList.remove('hidden'); }
function hide(el) { el.classList.add('hidden'); }

function clearOcrStorage() {
  chrome.storage.local.remove(['__ocrResults', '__ocrRawLines', '__ocrError', '__ocrPreview']);
}

// 打开时检查是否有待展示的结果
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
        html += `
        <div class="result-item">
          <div class="result-info">
            <span class="result-name">${key}</span>
            <span class="result-val" id="val-${flatIdx}">${val != null ? val : ''}</span>
          </div>
          <input class="result-edit" id="edit-${flatIdx}" type="number" step="any"
            placeholder="${key}"
            value="${val != null ? val : ''}"
            data-flat="${flatIdx}"
            onchange="onEditValue(this)">
        </div>`;
      });
    }
    html += `</div>`;
  });

  const totalCount = ocrItems.length;
  setStatus(`识别到 ${totalCount} 条记录`, 'success');
  resultsEl.innerHTML = html;
}

window.onEditValue = function(el) {
  const flatIdx = parseInt(el.dataset.flat);
  const val = parseFloat(el.value);
  if (!isNaN(val) && currentFlatItems[flatIdx]) {
    currentFlatItems[flatIdx].value = val;
    const itemIdx = currentFlatItems[flatIdx]._itemIdx;
    const metricKey = currentFlatItems[flatIdx].metricKey;
    currentItems[itemIdx].metrics[metricKey] = val;
    document.getElementById('val-' + flatIdx).textContent = val;
  }
};

btnSave.addEventListener('click', async () => {
  setStatus('保存中...', 'info');
  btnSave.disabled = true;

  try {
    const resp = await fetch(API_BASE + '/api/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
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
    setStatus(msg, 'success');
    hide(btnSave);
    currentItems = [];
    currentFlatItems = [];
    clearOcrStorage();
  } catch (e) {
    setStatus('保存失败: ' + e.message, 'error');
  }
  btnSave.disabled = false;
});
