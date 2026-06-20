ObjC.import('Foundation');

function run(argv) {
  const actionName = String(argv[0] || '');
  const amountText = String(argv[1] || '0');

  if (!actionName) {
    throw new Error('Missing action');
  }

  if (actionName === '__selftest') {
    return 'OK:selftest';
  }

  let jsResult = '';
  try {
    jsResult = runVideoJavaScript(actionName, amountText);
    if (String(jsResult).startsWith('OK:')) {
      return jsResult;
    }
  } catch (error) {
    jsResult = `JS_ERROR:${error.message || String(error)}`;
  }

  return fallbackKeys(actionName, amountText, jsResult);
}

function runVideoJavaScript(actionName, amountText) {
  const jsCode = `
(() => {
  function collectVideos(root) {
    const out = [];
    try {
      if (!root || !root.querySelectorAll) return out;
      out.push(...root.querySelectorAll('video'));
      for (const el of root.querySelectorAll('*')) {
        if (el.shadowRoot) out.push(...collectVideos(el.shadowRoot));
      }
      for (const frame of root.querySelectorAll('iframe')) {
        try {
          if (frame.contentDocument) out.push(...collectVideos(frame.contentDocument));
        } catch (error) {}
      }
    } catch (error) {}
    return out;
  }

  const action = ${JSON.stringify(actionName)};
  const amount = Number(${JSON.stringify(amountText)});
  const videos = collectVideos(document).filter((video) =>
    video.readyState > 0 || video.currentTime > 0 || Number.isFinite(video.duration)
  );
  const video =
    videos.find((item) => !item.paused && item.readyState > 0) ||
    videos.find((item) => item.readyState > 0) ||
    videos[0];

  if (!video) return 'NO_VIDEO';

  function play(videoElement) {
    try {
      const result = videoElement.play();
      if (result && result.catch) result.catch(() => {});
    } catch (error) {}
  }

  function clampTime(value) {
    const duration = Number.isFinite(video.duration) ? video.duration : Number.MAX_SAFE_INTEGER;
    return Math.min(duration, Math.max(0, value));
  }

  if (action === 'toggle') {
    if (video.paused) {
      play(video);
      return 'OK:play:' + Math.round(video.currentTime);
    }
    video.pause();
    return 'OK:pause:' + Math.round(video.currentTime);
  }

  if (action === 'play') {
    play(video);
    return 'OK:play:' + Math.round(video.currentTime);
  }

  if (action === 'pause') {
    video.pause();
    return 'OK:pause:' + Math.round(video.currentTime);
  }

  if (action === 'back') {
    video.currentTime = clampTime(video.currentTime - amount);
    return 'OK:back:' + Math.round(video.currentTime);
  }

  if (action === 'forward') {
    video.currentTime = clampTime(video.currentTime + amount);
    return 'OK:forward:' + Math.round(video.currentTime);
  }

  if (action === 'seek') {
    video.currentTime = clampTime(amount);
    return 'OK:seek:' + Math.round(video.currentTime);
  }

  if (action === 'fullscreen') {
    if (video.webkitEnterFullscreen) {
      video.webkitEnterFullscreen();
      return 'OK:fullscreen:video';
    }
    if (video.requestFullscreen) {
      video.requestFullscreen();
      return 'OK:fullscreen:document';
    }
    return 'NO_FULLSCREEN';
  }

  return 'UNKNOWN_ACTION:' + action;
})()
`;

  const safari = Application('Safari');
  if (safari.documents.length === 0) {
    return 'NO_SAFARI_DOCUMENT';
  }

  return String(safari.doJavaScript(jsCode, { in: safari.documents[0] }));
}

function fallbackKeys(actionName, amountText, jsResult) {
  if (actionName === 'seek') {
    throw new Error(
      `Exact seek needs Safari > Develop > Allow JavaScript from Apple Events. Last result: ${jsResult}`
    );
  }

  const safari = Application('Safari');
  safari.activate();
  sleep(0.15);

  const systemEvents = Application('System Events');
  const keyCode = (code) => systemEvents.keyCode(code);

  if (actionName === 'toggle') {
    keyCode(49);
    return `FALLBACK_KEYS:toggle:${jsResult}`;
  }

  if (actionName === 'play') {
    keyCode(49);
    return `FALLBACK_KEYS:play-toggle:${jsResult}`;
  }

  if (actionName === 'pause') {
    keyCode(49);
    return `FALLBACK_KEYS:pause-toggle:${jsResult}`;
  }

  if (actionName === 'back') {
    const repeatsCount = arrowRepeatCount(amountText);
    for (let index = 0; index < repeatsCount; index += 1) {
      keyCode(123);
      sleep(0.05);
    }
    return `FALLBACK_KEYS:back:${repeatsCount}:${jsResult}`;
  }

  if (actionName === 'forward') {
    const repeatsCount = arrowRepeatCount(amountText);
    for (let index = 0; index < repeatsCount; index += 1) {
      keyCode(124);
      sleep(0.05);
    }
    return `FALLBACK_KEYS:forward:${repeatsCount}:${jsResult}`;
  }

  if (actionName === 'fullscreen') {
    keyCode(3);
    return `FALLBACK_KEYS:fullscreen:${jsResult}`;
  }

  if (actionName === 'escape') {
    keyCode(53);
    return `FALLBACK_KEYS:escape:${jsResult}`;
  }

  throw new Error(`Unknown action: ${actionName}`);
}

function arrowRepeatCount(amountText) {
  const amountNumber = Number(amountText);
  const seconds = Number.isFinite(amountNumber) ? amountNumber : 10;
  return Math.max(1, Math.round(seconds / 10));
}

function sleep(seconds) {
  $.NSThread.sleepForTimeInterval(seconds);
}
