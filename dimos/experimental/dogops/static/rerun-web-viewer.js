import { WebViewer } from "/assets/vendor/@rerun-io/web-viewer/index.js";

const mounted = new WeakMap();

function setStatus(root, message, state = "") {
  const status = root.querySelector("[data-rerun-status]");
  if (!status) return;
  status.textContent = message;
  status.dataset.state = state;
}

function showFallback(root, message) {
  const canvasHost = root.querySelector("[data-rerun-canvas]");
  const fallback = root.querySelector("[data-viewer-offline]");
  if (canvasHost) canvasHost.hidden = true;
  if (fallback) fallback.hidden = false;
  setStatus(root, message, "error");
}

function configureOperatorMap(viewer) {
  try {
    viewer.override_panel_state("selection", "hidden");
    viewer.override_panel_state("blueprint", "collapsed");
    viewer.override_panel_state("time", "collapsed");
    viewer.toggle_panel_overrides(true);
  } catch {
    // Older Rerun web-viewer builds may not expose panel overrides.
  }
}

function setMapTimeline(viewer, replay = false) {
  const recordingId = viewer.get_active_recording_id();
  if (!recordingId) return false;
  try {
    viewer.set_active_timeline(recordingId, "sim_step");
    if (replay) {
      viewer.set_current_time(recordingId, "sim_step", 0);
      viewer.set_playing(recordingId, true);
    }
    return true;
  } catch {
    return false;
  }
}

async function focusMap(root, { replay = false, retries = 18 } = {}) {
  const viewer = mounted.get(root);
  if (!viewer) return false;
  configureOperatorMap(viewer);
  for (let attempt = 0; attempt < retries; attempt += 1) {
    if (setMapTimeline(viewer, replay)) {
      setStatus(root, replay ? "Rerun map replaying." : "Rerun WebViewer connected.", "ok");
      return true;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 250));
  }
  return false;
}

function sourceProbeUrl(sourceUrl) {
  if (!sourceUrl || !sourceUrl.startsWith("rerun+")) return "";
  try {
    const url = new URL(sourceUrl.slice("rerun+".length), window.location.href);
    if (!["127.0.0.1", "localhost", "::1"].includes(url.hostname)) return "";
    return url.href;
  } catch {
    return "";
  }
}

async function canReachLocalSource(url, timeoutMs = 1200) {
  if (!url) return true;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    await fetch(url, {
      cache: "no-store",
      mode: "no-cors",
      signal: controller.signal,
    });
    return true;
  } catch {
    return false;
  } finally {
    window.clearTimeout(timeout);
    controller.abort();
  }
}

export async function mountDogOpsRerunViewer(root) {
  if (!root) return;
  const existing = mounted.get(root);
  if (existing) {
    existing.stop();
    mounted.delete(root);
  }

  const canvasHost = root.querySelector("[data-rerun-canvas]");
  const fallback = root.querySelector("[data-viewer-offline]");
  const sourceUrl = root.dataset.rerunSourceUrl;
  const assetBaseUrl = new URL(
    root.dataset.rerunAssetBaseUrl || "/assets/vendor/@rerun-io/web-viewer/",
    window.location.href,
  ).href;

  if (!canvasHost || !sourceUrl) {
    showFallback(root, "Rerun WebViewer mount is incomplete.");
    return;
  }

  canvasHost.hidden = false;
  if (fallback) fallback.hidden = true;
  setStatus(root, "Connecting to Rerun...", "");

  const probeUrl = sourceProbeUrl(sourceUrl);
  if (!(await canReachLocalSource(probeUrl))) {
    showFallback(root, "Rerun stream offline. Showing latest DogOps map artifact.");
    return;
  }

  const viewer = new WebViewer();
  mounted.set(root, viewer);
  viewer.once("ready", () => {
    configureOperatorMap(viewer);
    setStatus(root, "Rerun WebViewer connected.", "ok");
    const replay = window.sessionStorage.getItem("dogops:rerun-replay");
    if (replay) {
      window.sessionStorage.removeItem("dogops:rerun-replay");
      focusMap(root, { replay: true });
    } else {
      focusMap(root, { replay: false });
    }
  });

  try {
    await viewer.start(
      sourceUrl,
      canvasHost,
      {
        width: "100%",
        height: "100%",
        hide_welcome_screen: true,
        base_url: assetBaseUrl,
      },
    );
  } catch (error) {
    mounted.delete(root);
    showFallback(root, `Rerun WebViewer failed: ${error.message || error}`);
  }
}

export function mountDogOpsRerunViewers() {
  return Promise.all(
    [...document.querySelectorAll("[data-map-viewer]")]
      .map((root) => mountDogOpsRerunViewer(root)),
  );
}

export async function replayDogOpsRerunMap(root) {
  return focusMap(root, { replay: true });
}

export async function focusDogOpsRerunMap(root) {
  return focusMap(root, { replay: false });
}

window.DogOpsRerunWebViewer = {
  mount: mountDogOpsRerunViewer,
  mountAll: mountDogOpsRerunViewers,
  replay: replayDogOpsRerunMap,
  focusMap: focusDogOpsRerunMap,
};
