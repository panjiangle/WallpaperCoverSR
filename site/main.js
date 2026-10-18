const copyButton = document.getElementById('copy-path');
const copyStatus = document.getElementById('copy-status');
copyButton.addEventListener('click', async () => {
  const value = String.raw`%LOCALAPPDATA%\WallpaperCoverSR`;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
    } else {
      const input = document.createElement('textarea');
      input.value = value;
      input.style.position = 'fixed';
      input.style.opacity = '0';
      document.body.appendChild(input);
      input.select();
      const copied = document.execCommand('copy');
      input.remove();
      if (!copied) throw new Error('Clipboard unavailable');
    }
    copyButton.textContent = '已复制';
    copyStatus.textContent = '数据目录路径已复制。';
    setTimeout(() => { copyButton.textContent = '复制数据目录'; }, 2200);
  } catch {
    copyStatus.textContent = '暂时无法自动复制，请选中目录路径手动复制。';
    copyButton.textContent = '请手动复制路径';
  }
});
