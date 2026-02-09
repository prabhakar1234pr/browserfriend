/**
 * BrowserFriend - Background Service Worker
 *
 * Tracks active tab changes and sends page visit data to the local
 * FastAPI server at http://localhost:8000/api/track.
 *
 * Listens to:
 *   - chrome.tabs.onActivated   (user switches tabs)
 *   - chrome.tabs.onUpdated     (URL changes within same tab)
 *   - chrome.windows.onFocusChanged (user switches windows)
 *
 * Persists state via chrome.storage.local so it survives service-worker
 * restarts imposed by Manifest V3.
 */

// ─── Constants ───────────────────────────────────────────────────────
const API_BASE = "http://localhost:8000";
const API_TRACK = `${API_BASE}/api/track`;
const API_STATUS = `${API_BASE}/api/status`;

/** Minimum duration (seconds) a tab must be active before we report it. */
const MIN_DURATION_SECONDS = 2;

/** URL prefixes that should never be tracked. */
const IGNORED_URL_PREFIXES = [
  "chrome://",
  "chrome-extension://",
  "edge://",
  "about:",
  "devtools://",
  "chrome-search://",
  "chrome-native://",
  "brave://",
];

// ─── Logging helpers ─────────────────────────────────────────────────

/**
 * Structured console logger.  Every message is prefixed with
 * [BrowserFriend] so it stands out in the DevTools console.
 */
const log = {
  info: (...args) => console.log("[BrowserFriend]", ...args),
  warn: (...args) => console.warn("[BrowserFriend]", ...args),
  error: (...args) => console.error("[BrowserFriend]", ...args),
  debug: (...args) => console.debug("[BrowserFriend]", ...args),
};

// ─── Helper functions ────────────────────────────────────────────────

/**
 * Decide whether a URL should be tracked.
 * Returns false for internal browser pages, empty URLs, and localhost.
 *
 * @param {string|undefined} url
 * @returns {boolean}
 */
function shouldTrackUrl(url) {
  if (!url) {
    log.debug("shouldTrackUrl: empty/undefined URL — skipping");
    return false;
  }

  for (const prefix of IGNORED_URL_PREFIXES) {
    if (url.startsWith(prefix)) {
      log.debug(`shouldTrackUrl: "${url}" matches ignored prefix "${prefix}" — skipping`);
      return false;
    }
  }

  // Ignore localhost URLs (the BrowserFriend server itself)
  try {
    const parsed = new URL(url);
    if (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1") {
      log.debug(`shouldTrackUrl: "${url}" is localhost — skipping`);
      return false;
    }
  } catch {
    log.warn(`shouldTrackUrl: failed to parse URL "${url}" — skipping`);
    return false;
  }

  return true;
}

/**
 * Calculate duration in whole seconds between a start timestamp and now.
 *
 * @param {number} startTime  epoch ms (Date.now() value)
 * @returns {number} seconds (floored)
 */
function calculateDuration(startTime) {
  const duration = Math.floor((Date.now() - startTime) / 1000);
  log.debug(`calculateDuration: startTime=${startTime}, now=${Date.now()}, duration=${duration}s`);
  return duration;
}

/**
 * Retrieve the stored email from chrome.storage.local.
 *
 * @returns {Promise<string|null>}
 */
async function getStoredEmail() {
  return new Promise((resolve) => {
    chrome.storage.local.get(["email"], (result) => {
      if (chrome.runtime.lastError) {
        log.error("getStoredEmail: storage error —", chrome.runtime.lastError.message);
        resolve(null);
        return;
      }
      log.debug(`getStoredEmail: retrieved email="${result.email || "(not set)"}"`);
      resolve(result.email || null);
    });
  });
}

/**
 * Retrieve current tab state from chrome.storage.local.
 *
 * @returns {Promise<{url: string, title: string, startTime: number, tabId: number}|null>}
 */
async function getCurrentTabState() {
  return new Promise((resolve) => {
    chrome.storage.local.get(["currentTab"], (result) => {
      if (chrome.runtime.lastError) {
        log.error("getCurrentTabState: storage error —", chrome.runtime.lastError.message);
        resolve(null);
        return;
      }
      resolve(result.currentTab || null);
    });
  });
}

/**
 * Persist the current tab state to chrome.storage.local.
 *
 * @param {{url: string, title: string, startTime: number, tabId: number}|null} tabState
 * @returns {Promise<void>}
 */
async function saveCurrentTabState(tabState) {
  return new Promise((resolve) => {
    chrome.storage.local.set({ currentTab: tabState }, () => {
      if (chrome.runtime.lastError) {
        log.error("saveCurrentTabState: storage error —", chrome.runtime.lastError.message);
      } else {
        log.debug("saveCurrentTabState: saved", tabState);
      }
      resolve();
    });
  });
}

/**
 * Get the currently active tab in the focused window.
 *
 * @returns {Promise<chrome.tabs.Tab|null>}
 */
async function getActiveTab() {
  return new Promise((resolve) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (chrome.runtime.lastError) {
        log.error("getActiveTab: query error —", chrome.runtime.lastError.message);
        resolve(null);
        return;
      }
      resolve(tabs && tabs.length > 0 ? tabs[0] : null);
    });
  });
}

/**
 * Send page-visit data to the BrowserFriend server.
 * Fails silently if the server is unreachable (logs the error).
 *
 * @param {{url: string, title: string, duration: number, timestamp: string, email: string}} data
 * @returns {Promise<boolean>}  true if the request succeeded
 */
async function sendToServer(data) {
  log.info(`sendToServer: sending visit — url="${data.url}", duration=${data.duration}s`);
  log.debug("sendToServer: full payload", JSON.stringify(data));

  try {
    const response = await fetch(API_TRACK, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const errorBody = await response.text();
      log.error(`sendToServer: server returned ${response.status} — ${errorBody}`);
      return false;
    }

    const result = await response.json();
    log.info(`sendToServer: success — session_id=${result.session_id}, message="${result.message}"`);
    return true;
  } catch (err) {
    // Server is likely offline — fail silently
    log.warn(`sendToServer: request failed (server offline?) — ${err.message}`);
    return false;
  }
}

// ─── Core tracking logic ─────────────────────────────────────────────

/**
 * Finalize the previously-active tab: calculate its duration and send
 * the visit data to the server, then clear the stored tab state.
 *
 * @param {string} reason  Human-readable reason for the switch (for logs)
 * @returns {Promise<void>}
 */
async function finalizePreviousTab(reason) {
  log.debug(`finalizePreviousTab: triggered — reason="${reason}"`);

  const prevTab = await getCurrentTabState();
  if (!prevTab) {
    log.debug("finalizePreviousTab: no previous tab state — nothing to finalize");
    return;
  }

  // Check URL is trackable
  if (!shouldTrackUrl(prevTab.url)) {
    log.debug(`finalizePreviousTab: previous URL not trackable — clearing state`);
    await saveCurrentTabState(null);
    return;
  }

  // Calculate duration
  const duration = calculateDuration(prevTab.startTime);
  if (duration < MIN_DURATION_SECONDS) {
    log.debug(
      `finalizePreviousTab: duration ${duration}s < minimum ${MIN_DURATION_SECONDS}s — skipping`
    );
    await saveCurrentTabState(null);
    return;
  }

  // Get email
  const email = await getStoredEmail();
  if (!email) {
    log.warn("finalizePreviousTab: no email configured — skipping server send");
    await saveCurrentTabState(null);
    return;
  }

  // Build payload
  const payload = {
    url: prevTab.url,
    title: prevTab.title || "",
    duration: duration,
    timestamp: new Date().toISOString(),
    email: email,
  };

  // Send to server (fire-and-forget style, errors are logged internally)
  await sendToServer(payload);

  // Clear state
  await saveCurrentTabState(null);
  log.debug("finalizePreviousTab: done");
}

/**
 * Start tracking a new tab.  Saves its URL, title, start time and tab ID
 * to chrome.storage.local.
 *
 * @param {chrome.tabs.Tab} tab
 * @returns {Promise<void>}
 */
async function startTrackingTab(tab) {
  if (!tab || !tab.url) {
    log.debug("startTrackingTab: no tab or URL — skipping");
    return;
  }

  if (!shouldTrackUrl(tab.url)) {
    log.debug(`startTrackingTab: URL "${tab.url}" is not trackable — skipping`);
    return;
  }

  const tabState = {
    url: tab.url,
    title: tab.title || "",
    startTime: Date.now(),
    tabId: tab.id,
  };

  await saveCurrentTabState(tabState);
  log.info(`startTrackingTab: now tracking tab ${tab.id} — "${tab.title}" (${tab.url})`);
}

/**
 * Handle a tab switch: finalize the old tab and begin tracking the new one.
 *
 * @param {chrome.tabs.Tab} newTab
 * @param {string} reason
 * @returns {Promise<void>}
 */
async function handleTabSwitch(newTab, reason) {
  log.info(`handleTabSwitch: reason="${reason}", newTab=${newTab ? newTab.id : "none"}`);

  await finalizePreviousTab(reason);

  if (newTab) {
    await startTrackingTab(newTab);
  }
}

// ─── Chrome event listeners ──────────────────────────────────────────

/**
 * Fired when the user switches to a different tab.
 */
chrome.tabs.onActivated.addListener(async (activeInfo) => {
  log.info(`[EVENT] tabs.onActivated — tabId=${activeInfo.tabId}, windowId=${activeInfo.windowId}`);

  try {
    const tab = await chrome.tabs.get(activeInfo.tabId);
    log.debug(`tabs.onActivated: got tab info — url="${tab.url}", title="${tab.title}"`);
    await handleTabSwitch(tab, "tab-activated");
  } catch (err) {
    log.error(`tabs.onActivated: error getting tab info — ${err.message}`);
  }
});

/**
 * Fired when a tab's URL or title changes (e.g. navigation within the same tab).
 * We only care about "complete" status to avoid firing on every intermediate load state.
 */
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  // Only act when navigation completes and URL actually changed
  if (changeInfo.status !== "complete") {
    return;
  }

  log.info(`[EVENT] tabs.onUpdated — tabId=${tabId}, url="${tab.url}"`);

  // Only process if this is the currently active tab
  const currentState = await getCurrentTabState();
  if (!currentState || currentState.tabId !== tabId) {
    log.debug("tabs.onUpdated: not the tracked tab — ignoring");
    return;
  }

  // If URL changed within the same tab, finalize old and track new
  if (currentState.url !== tab.url) {
    log.info(
      `tabs.onUpdated: URL changed in tracked tab — old="${currentState.url}", new="${tab.url}"`
    );
    await handleTabSwitch(tab, "url-changed-in-tab");
  } else {
    // Title may have changed; update stored title
    if (tab.title && currentState.title !== tab.title) {
      log.debug(`tabs.onUpdated: title changed — "${currentState.title}" → "${tab.title}"`);
      currentState.title = tab.title;
      await saveCurrentTabState(currentState);
    }
  }
});

/**
 * Fired when the user switches between browser windows or leaves Chrome entirely.
 * windowId === chrome.windows.WINDOW_ID_NONE means focus left Chrome.
 */
chrome.windows.onFocusChanged.addListener(async (windowId) => {
  log.info(`[EVENT] windows.onFocusChanged — windowId=${windowId}`);

  if (windowId === chrome.windows.WINDOW_ID_NONE) {
    // User left Chrome — finalize current tab
    log.info("windows.onFocusChanged: focus left Chrome — finalizing current tab");
    await finalizePreviousTab("window-focus-lost");
    return;
  }

  // User switched to a different Chrome window — track the active tab in that window
  try {
    const tabs = await chrome.tabs.query({ active: true, windowId: windowId });
    if (tabs && tabs.length > 0) {
      log.debug(`windows.onFocusChanged: active tab in window — url="${tabs[0].url}"`);
      await handleTabSwitch(tabs[0], "window-focus-changed");
    } else {
      log.debug("windows.onFocusChanged: no active tab in focused window");
    }
  } catch (err) {
    log.error(`windows.onFocusChanged: error querying tabs — ${err.message}`);
  }
});

// ─── Service worker lifecycle ────────────────────────────────────────

/**
 * Runs once when the service worker first installs (extension loaded/reloaded).
 * Start tracking whatever tab is currently active.
 */
chrome.runtime.onInstalled.addListener(async (details) => {
  log.info(`[LIFECYCLE] onInstalled — reason="${details.reason}"`);

  const tab = await getActiveTab();
  if (tab) {
    await startTrackingTab(tab);
  } else {
    log.debug("onInstalled: no active tab found");
  }
});

/**
 * Runs every time the service worker wakes up (e.g. after being terminated
 * by Chrome to save memory).  Re-acquire the current tab state.
 */
chrome.runtime.onStartup.addListener(async () => {
  log.info("[LIFECYCLE] onStartup — service worker waking up");

  const tab = await getActiveTab();
  if (tab) {
    await startTrackingTab(tab);
  }
});

log.info("Service worker loaded — BrowserFriend tab tracking active");
