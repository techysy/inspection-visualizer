(() => {
  if (window.__inspectionOverlayActive) return;
  window.__inspectionOverlayActive = true;

  const overlay = document.createElement('div');
  overlay.id = 'inspection-overlay';
  overlay.innerHTML = `
    <div id="inspection-tip">拖拽框选需要识别的区域，松开自动截图</div>
    <div id="inspection-selection"></div>
  `;
  document.body.appendChild(overlay);

  const sel = document.getElementById('inspection-selection');
  const tip = document.getElementById('inspection-tip');
  let startX, startY, isDragging = false;

  overlay.addEventListener('mousedown', (e) => {
    if (e.target === tip) return;
    isDragging = true;
    startX = e.clientX;
    startY = e.clientY;
    sel.style.left = startX + 'px';
    sel.style.top = startY + 'px';
    sel.style.width = '0px';
    sel.style.height = '0px';
    sel.style.display = 'block';
    tip.style.display = 'none';
    e.preventDefault();
  });

  document.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    const x = Math.min(e.clientX, startX);
    const y = Math.min(e.clientY, startY);
    const w = Math.abs(e.clientX - startX);
    const h = Math.abs(e.clientY - startY);
    sel.style.left = x + 'px';
    sel.style.top = y + 'px';
    sel.style.width = w + 'px';
    sel.style.height = h + 'px';
  });

  document.addEventListener('mouseup', (e) => {
    if (!isDragging) return;
    isDragging = false;

    const x = Math.min(e.clientX, startX);
    const y = Math.min(e.clientY, startY);
    const w = Math.abs(e.clientX - startX);
    const h = Math.abs(e.clientY - startY);

    if (w < 10 || h < 10) {
      cleanup();
      return;
    }

    const dpr = window.devicePixelRatio || 1;
    const rect = {
      x: Math.round(x * dpr),
      y: Math.round(y * dpr),
      width: Math.round(w * dpr),
      height: Math.round(h * dpr),
      screenX: x,
      screenY: y,
      screenWidth: w,
      screenHeight: h
    };

    cleanup();

    chrome.storage.local.set({ __regionRect: rect });
  });

  function cleanup() {
    overlay.remove();
    window.__inspectionOverlayActive = false;
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') cleanup();
  });
})();
