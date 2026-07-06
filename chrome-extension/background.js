const API_BASE = 'http://localhost:5001';

// 监听快捷键
chrome.commands.onCommand.addListener(async (command) => {
  if (command === 'start-capture') {
    await startCapture();
  }
});

// 启动框选截图
async function startCapture() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) return;

    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ['content.js']
    });
    await chrome.scripting.insertCSS({
      target: { tabId: tab.id },
      files: ['content.css']
    });
  } catch (e) {
    console.error('启动框选失败:', e);
  }
}

chrome.storage.onChanged.addListener(async (changes, area) => {
  if (area !== 'local') return;

  if (changes.__regionRect && changes.__regionRect.newValue) {
    const rect = changes.__regionRect.newValue;
    chrome.storage.local.remove('__regionRect');
    await processRegion(rect);
  }
});

async function processRegion(rect) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) {
      storeError('未找到活动标签页');
      return;
    }

    // 截取可见区域
    const dataUrl = await captureVisibleTab(tab.windowId);

    // 裁剪选区（service worker 中用 OffscreenCanvas + createImageBitmap）
    const cropped = await cropImage(dataUrl, rect);

    // 存储截图预览
    chrome.storage.local.set({ __ocrPreview: cropped });

    // badge 显示"识别中"
    chrome.action.setBadgeText({ text: '...', tabId: tab.id });
    chrome.action.setBadgeBackgroundColor({ color: '#6366f1', tabId: tab.id });

    // 调用 OCR API
    const resp = await fetch(API_BASE + '/api/ocr', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image: cropped,
        filename: 'screenshot.png',
        last_modified: Date.now()
      })
    });
    const data = await resp.json();

    if (data.error) {
      storeError('识别失败: ' + data.error);
      return;
    }

    const items = data.items || [];

    chrome.storage.local.set({
      __ocrResults: items,
      __ocrRawLines: data.raw_lines || [],
      __ocrError: null
    });

    chrome.action.setBadgeText({ text: items.length ? String(items.length) : '0', tabId: tab.id });
    chrome.action.setBadgeBackgroundColor({ color: items.length ? '#10b981' : '#f59e0b', tabId: tab.id });

  } catch (e) {
    storeError('请求失败: ' + e.message);
  }
}

function storeError(msg) {
  chrome.storage.local.set({
    __ocrResults: [],
    __ocrRawLines: [],
    __ocrError: msg
  });
  chrome.action.setBadgeText({ text: '!' });
  chrome.action.setBadgeBackgroundColor({ color: '#ef4444' });
}

function captureVisibleTab(windowId) {
  return new Promise((resolve, reject) => {
    chrome.tabs.captureVisibleTab(windowId, { format: 'png' }, (dataUrl) => {
      if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
      else resolve(dataUrl);
    });
  });
}

async function cropImage(dataUrl, rect) {
  // dataUrl → Blob
  const resp = await fetch(dataUrl);
  const blob = await resp.blob();

  // Blob → ImageBitmap
  const bitmap = await createImageBitmap(blob);

  // 裁剪
  const canvas = new OffscreenCanvas(rect.width, rect.height);
  const ctx = canvas.getContext('2d');
  ctx.drawImage(bitmap, rect.x, rect.y, rect.width, rect.height, 0, 0, rect.width, rect.height);
  bitmap.close();

  // → dataUrl
  const resultBlob = await canvas.convertToBlob({ type: 'image/png' });
  const reader = new FileReader();
  return new Promise((resolve) => {
    reader.onloadend = () => resolve(reader.result);
    reader.readAsDataURL(resultBlob);
  });
}
