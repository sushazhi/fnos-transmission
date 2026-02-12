/**
 * Transmission Update Check - 注入到 WebUI 的更新检测脚本
 *
 * 功能：
 * 1. 检测 GitHub 最新版本
 * 2. 比较版本号判断是否有更新
 * 3. 显示更新通知
 * 4. 支持忽略更新
 */

(function() {
  'use strict';

  const CONFIG = {
    currentVersion: window.TRANSMISSION_APP_VERSION || '4.1.0',
    repoOwner: 'sushazhi',
    repoName: 'fnos-transmission',
    checkInterval: 24 * 60 * 60 * 1000
  };

  // 记录当前版本用于调试
  if (isDebug) {
    console.log('[Update] 当前应用版本:', CONFIG.currentVersion);
  }

  const CACHE_KEY = 'transmission_update_check';
  const IGNORE_KEY = 'transmission_ignore_version';
  const CLOSE_TIME_KEY = 'transmission_close_time';
  const CLOSE_DURATION = 24 * 60 * 60 * 1000; // 24小时

  // 调试模式
  const isDebug = new URLSearchParams(window.location.search).get('debug') === '1';
  function log(msg) {
    if (isDebug) console.log('[Update]', msg);
  }

  function getCachedResult() {
    try {
      const cached = localStorage.getItem(CACHE_KEY);
      if (cached) {
        const data = JSON.parse(cached);
        if (Date.now() - data.timestamp < CONFIG.checkInterval) {
          return data;
        }
      }
    } catch (e) {}
    return null;
  }

  function cacheResult(data) {
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify({
        timestamp: Date.now(),
        ...data
      }));
    } catch (e) {}
  }

  function getIgnoredVersion() {
    try {
      return localStorage.getItem(IGNORE_KEY) || '';
    } catch (e) {
      return '';
    }
  }

  function setIgnoredVersion(version) {
    try {
      localStorage.setItem(IGNORE_KEY, version);
    } catch (e) {}
  }

  function getCloseTime() {
    try {
      const time = localStorage.getItem(CLOSE_TIME_KEY);
      return time ? parseInt(time, 10) : 0;
    } catch (e) {
      return 0;
    }
  }

  function setCloseTime() {
    try {
      localStorage.setItem(CLOSE_TIME_KEY, Date.now().toString());
    } catch (e) {}
  }

  function isRecentlyClosed() {
    return Date.now() - getCloseTime() < CLOSE_DURATION;
  }

  function compareVersions(current, latest) {
    const cur = (current || '').split('.').map(n => parseInt(n, 10) || 0);
    const lat = (latest || '').split('.').map(n => parseInt(n, 10) || 0);
    
    // 首先比较公共部分
    const minLen = Math.min(cur.length, lat.length);
    for (let i = 0; i < minLen; i++) {
      const curNum = cur[i];
      const latNum = lat[i];
      if (latNum > curNum) return 1;  // latest 更大
      if (latNum < curNum) return -1;  // current 更大
    }
    
    // 公共部分相等时，版本号更长的那个更大
    // 例如: 5.1.4.1 > 5.1.4
    if (lat.length > cur.length) return 1;   // latest 版本号更长
    if (cur.length > lat.length) return -1;   // current 版本号更长
    return 0;  // 相等
  }

  function showUpdateNotification(updateInfo) {
    // 检查是否已忽略此版本
    if (getIgnoredVersion() === updateInfo.latestVersion) {
      log('已忽略版本 ' + updateInfo.latestVersion);
      return;
    }

    // 检查是否在24小时内关闭过
    if (isRecentlyClosed()) {
      log('24小时内已关闭，跳过通知');
      return;
    }

    // 创建通知元素
    const notification = document.createElement('div');
    notification.id = 'transmission-update-notification';
    notification.innerHTML = `
      <div class="update-notification-content">
        <div class="update-notification-icon">🚀</div>
        <div class="update-notification-text">
          <div class="update-notification-title">发现新版本</div>
          <div class="update-notification-version">
            当前: v${CONFIG.currentVersion} → 最新: v${updateInfo.latestVersion}
          </div>
        </div>
        <div class="update-notification-actions">
          <a href="${updateInfo.releaseUrl}" target="_blank" class="update-notification-btn update-notification-btn-primary">前往下载</a>
          <button class="update-notification-btn update-notification-btn-secondary ignore-btn">忽略此版本</button>
          <button class="update-notification-close">&times;</button>
        </div>
      </div>
    `;

    // 添加样式
    if (!document.getElementById('update-notification-styles')) {
      const styles = document.createElement('style');
      styles.id = 'update-notification-styles';
      styles.textContent = `
        #transmission-update-notification {
          position: fixed;
          bottom: 20px;
          right: 20px;
          z-index: 99999;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          animation: slideIn 0.3s ease-out;
        }
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
        .update-notification-content {
          display: flex;
          align-items: center;
          gap: 12px;
          background: white;
          padding: 16px 20px;
          border-radius: 12px;
          box-shadow: 0 4px 20px rgba(0,0,0,0.15);
        }
        .update-notification-icon {
          font-size: 32px;
        }
        .update-notification-text {
          flex: 1;
        }
        .update-notification-title {
          font-weight: 600;
          font-size: 15px;
          color: #333;
        }
        .update-notification-version {
          font-size: 13px;
          color: #667eea;
          margin-top: 4px;
        }
        .update-notification-actions {
          display: flex;
          gap: 8px;
          align-items: center;
        }
        .update-notification-btn {
          padding: 8px 16px;
          border-radius: 6px;
          font-size: 12px;
          font-weight: 500;
          text-decoration: none;
          cursor: pointer;
          border: none;
        }
        .update-notification-btn-primary {
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
        }
        .update-notification-btn-primary:hover {
          opacity: 0.9;
        }
        .update-notification-btn-secondary {
          background: #f5f5f5;
          color: #666;
        }
        .update-notification-btn-secondary:hover {
          background: #e8e8e8;
        }
        .update-notification-close {
          background: none;
          border: none;
          font-size: 20px;
          color: #999;
          cursor: pointer;
          padding: 0 4px;
        }
        .update-notification-close:hover {
          color: #333;
        }
      `;
      document.head.appendChild(styles);
    }

    // 绑定关闭事件 - 24小时内不再弹窗
    notification.querySelector('.update-notification-close').onclick = function() {
      setCloseTime();
      log('已关闭通知，24小时内不再弹窗');
      notification.remove();
    };

    // 绑定忽略事件
    notification.querySelector('.ignore-btn').onclick = function() {
      setIgnoredVersion(updateInfo.latestVersion);
      log('已忽略版本 ' + updateInfo.latestVersion);
      notification.remove();
    };

    document.body.appendChild(notification);
    log('显示更新通知: v' + updateInfo.latestVersion);
  }

  async function checkUpdate() {
    log('开始检查更新... 当前版本: ' + CONFIG.currentVersion);

    // 先检查缓存（强制不使用缓存结果，确保每次都检测最新）
    const cached = getCachedResult();
    if (cached && cached.hasUpdate !== undefined) {
      log('缓存结果: hasUpdate=' + cached.hasUpdate + ', latest=' + cached.latestVersion);
      // 强制重新检测，不使用缓存
    }

    // 强制重新检查 GitHub
    try {
      const apiUrl = `https://api.github.com/repos/${CONFIG.repoOwner}/${CONFIG.repoName}/releases/latest`;
      const response = await fetch(apiUrl, {
        headers: { 'Accept': 'application/vnd.github.v3+json' },
        cache: 'no-store'
      });

      if (!response.ok) throw new Error('HTTP ' + response.status);

      const data = await response.json();
      let latestVersion = (data.tag_name || '').replace(/^v/, '').trim();

      log('GitHub 最新版本: ' + latestVersion);
      log('当前版本: ' + CONFIG.currentVersion);

      const cmp = compareVersions(CONFIG.currentVersion, latestVersion);
      log('比较结果: ' + cmp + ' (正数=有更新, 0=相同, 负数=当前更新)');

      const hasUpdate = cmp > 0;

      const result = {
        hasUpdate,
        latestVersion,
        releaseUrl: data.html_url || ''
      };

      // 不缓存结果，每次都重新检测
      log('缓存已禁用，每次都会重新检测');

      if (hasUpdate) {
        log('发现新版本，显示通知');
        showUpdateNotification(result);
      } else {
        log('当前是最新版本');
      }
    } catch (error) {
      log('检查失败: ' + error.message);
    }
  }

  // 页面加载后延迟检查
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
      setTimeout(checkUpdate, 2000);
    });
  } else {
    setTimeout(checkUpdate, 2000);
  }

})();
