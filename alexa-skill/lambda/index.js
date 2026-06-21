'use strict';

let SQSClient;
let SendMessageCommand;

const ACTION_BY_INTENT = {
  PlayIntent: { action: 'play' },
  PauseIntent: { action: 'pause' },
  ToggleIntent: { action: 'toggle' },
  FullscreenIntent: { action: 'fullscreen' },
  EscapeIntent: { action: 'escape' },
  OpenCodexIntent: { action: 'open_codex' },
  CodexStatusIntent: { action: 'codex_status' },
  CancelCodexIntent: { action: 'codex_cancel' },
  QuitCodexIntent: { action: 'codex_quit' },
  BrowserStatusIntent: { action: 'browser_status' },
  SurfsharkDisconnectIntent: { action: 'surfshark_disconnect' },
  SurfsharkConnectIntent: { action: 'surfshark_connect_us' },
};

const SITE_BY_SEARCH_INTENT = {
  SearchPeacockIntent: 'peacock',
  SearchDisneyIntent: 'disney',
  SearchNetflixIntent: 'netflix',
  SearchYoutubeIntent: 'youtube',
  SearchHuluIntent: 'hulu',
  SearchPrimeIntent: 'prime video',
};

exports.handler = async (event) => {
  const request = event && event.request ? event.request : {};
  const sessionAttributes = event && event.session && event.session.attributes ? event.session.attributes : {};

  if (request.type === 'LaunchRequest') {
    const mediaAction = { action: 'open_codex' };
    await sendToBridge(mediaAction);
    return response(
      'Opening Codex. Say Codex followed by what you want me to do.',
      {
        shouldEndSession: false,
        reprompt: 'Say Codex followed by what you want me to do.',
        sessionAttributes: { liveCodexMode: true },
      },
    );
  }

  if (request.type !== 'IntentRequest') {
    return response('I can control play, pause, rewind, fast forward, fullscreen, and exact seek.');
  }

  const intentName = request.intent && request.intent.name;

  if (intentName === 'AMAZON.HelpIntent') {
    return response('Try pause, rewind ten seconds, or go to twelve minutes thirty seconds.');
  }

  if (intentName === 'AMAZON.CancelIntent' || intentName === 'AMAZON.StopIntent') {
    return response('Done.');
  }

  const mediaAction = buildMediaAction(request.intent, sessionAttributes);
  if (!mediaAction) {
    return response('I did not understand that remote command.');
  }

  await sendToBridge(mediaAction);
  return response(spokenConfirmation(mediaAction), responseOptionsForAction(mediaAction, sessionAttributes));
};

function buildMediaAction(intent, sessionAttributes = {}) {
  const intentName = intent && intent.name;

  if (ACTION_BY_INTENT[intentName]) {
    return ACTION_BY_INTENT[intentName];
  }

  if (intentName === 'AskCodexIntent') {
    const prompt = slotValue(intent, 'prompt');
    if (!prompt) return null;
    if (sessionAttributes.liveCodexMode) {
      return { action: 'live_codex_prompt', prompt: stripCodexPrefix(prompt) };
    }
    return actionFromCodexPrompt(prompt);
  }

  if (intentName === 'LiveCodexPromptIntent') {
    const prompt = slotValue(intent, 'prompt');
    if (!prompt) return null;
    return { action: 'live_codex_prompt', prompt };
  }

  if (intentName === 'OpenSiteIntent') {
    const site = slotValue(intent, 'site');
    if (!site) return null;
    return { action: 'browser_open', site };
  }

  if (intentName === 'SearchSiteIntent') {
    const site = slotValue(intent, 'site');
    const query = slotValue(intent, 'query');
    if (!site || !query) return null;
    return { action: 'browser_search', site, query };
  }

  if (SITE_BY_SEARCH_INTENT[intentName]) {
    const query = slotValue(intent, 'query');
    if (!query) return null;
    return { action: 'browser_search', site: SITE_BY_SEARCH_INTENT[intentName], query };
  }

  if (intentName === 'BrowserCommandIntent') {
    const command = slotValue(intent, 'command');
    if (!command) return null;
    return actionFromBrowserCommand(command);
  }

  if (intentName === 'BrowserSeekIntent') {
    const direction = slotValue(intent, 'direction');
    const amount = positiveNumber(slotValue(intent, 'amount')) || 10;
    const unit = slotValue(intent, 'unit') || 'seconds';
    const seconds = unit.startsWith('minute') ? amount * 60 : amount;
    return { action: 'browser_seek', seconds: ['back', 'rewind'].includes(direction) ? -seconds : seconds };
  }

  if (intentName === 'CodexExecIntent') {
    const prompt = slotValue(intent, 'prompt');
    if (!prompt) return null;
    return { action: 'codex_task', prompt };
  }

  if (intentName === 'RelativeSeekIntent') {
    const direction = slotValue(intent, 'direction');
    const amount = positiveNumber(slotValue(intent, 'amount')) || 10;
    const unit = slotValue(intent, 'unit') || 'seconds';
    const seconds = unit.startsWith('minute') ? amount * 60 : amount;
    const action = ['forward', 'ahead', 'skip'].includes(direction) ? 'forward' : 'back';
    return { action, seconds };
  }

  if (intentName === 'AbsoluteSeekIntent') {
    const hours = positiveNumber(slotValue(intent, 'hours')) || 0;
    const minutes = positiveNumber(slotValue(intent, 'minutes')) || 0;
    const seconds = positiveNumber(slotValue(intent, 'seconds')) || 0;
    return { action: 'seek', seconds: hours * 3600 + minutes * 60 + seconds };
  }

  return null;
}

function stripCodexPrefix(prompt) {
  const cleanPrompt = String(prompt || '').trim().toLowerCase();
  return cleanPrompt.startsWith('codex ') ? cleanPrompt.slice(6).trim() : cleanPrompt;
}

function actionFromCodexPrompt(prompt) {
  const cleanPrompt = String(prompt || '').trim().toLowerCase();

  for (const prefix of ['live codex ', 'tell live codex to ', 'ask live codex to ']) {
    if (cleanPrompt.startsWith(prefix)) {
      return { action: 'live_codex_prompt', prompt: cleanPrompt.slice(prefix.length).trim() };
    }
  }

  if (['quit codex', 'close codex', 'shut down codex'].includes(cleanPrompt)) {
    return { action: 'codex_quit' };
  }

  if (/^(?:disconnect|turn off|stop|close) (?:the )?(?:vpn|surfshark|surf shark)$/.test(cleanPrompt)) {
    return { action: 'surfshark_disconnect' };
  }

  if (/^(?:(?:connect|start|turn on|refresh|restart) (?:the )?(?:vpn|surfshark|surf shark)|(?:refresh|restart) (?:the )?(?:usa|u\.s\.|us|united states) (?:vpn|surfshark|surf shark))$/.test(cleanPrompt)) {
    return { action: 'surfshark_connect_us' };
  }

  const searchMatch = cleanPrompt.match(/^(?:search|find) (peacock|peacock tv|disney|disney plus|netflix|youtube|you tube|hulu|prime|prime video) (?:for )?(.+)$/);
  if (searchMatch) {
    return { action: 'browser_search', site: searchMatch[1], query: searchMatch[2] };
  }

  const openMatch = cleanPrompt.match(/^(?:open|launch|go to) (peacock|peacock tv|disney|disney plus|netflix|youtube|you tube|hulu|prime|prime video|[a-z0-9.-]+\.[a-z]{2,})(?: website| app| site)?$/);
  if (openMatch) {
    return { action: 'browser_open', site: openMatch[1] };
  }

  const seekMatch = cleanPrompt.match(/^(?:seek|skip|forward|go forward|rewind|back|go back) (?:to |by )?(\d+) ?(seconds?|minutes?)?$/);
  if (seekMatch) {
    const amount = Number(seekMatch[1]);
    const unit = seekMatch[2] || 'seconds';
    const direction = cleanPrompt.includes('rewind') || cleanPrompt.includes('back') ? -1 : 1;
    return { action: 'browser_seek', seconds: direction * (unit.startsWith('minute') ? amount * 60 : amount) };
  }

  const commandAction = actionFromBrowserCommand(cleanPrompt);
  if (commandAction) return commandAction;

  return { action: 'codex_task', prompt: cleanPrompt };
}

function actionFromBrowserCommand(command) {
  const cleanCommand = String(command || '').trim().toLowerCase();
  if (['play', 'pause', 'toggle', 'play pause', 'fullscreen', 'escape'].includes(cleanCommand)) {
    return { action: 'browser_command', command: cleanCommand };
  }
  return null;
}

async function sendToBridge(mediaAction) {
  if (process.env.ALEXA_SAFARI_REMOTE_QUEUE_URL) {
    await sendToSqs(mediaAction);
    return;
  }

  const endpoint = process.env.REMOTE_ENDPOINT_URL;
  if (!endpoint) {
    console.log('REMOTE_ENDPOINT_URL not set; dry-run action:', JSON.stringify(mediaAction));
    return;
  }

  const headers = { 'content-type': 'application/json' };
  if (process.env.REMOTE_ENDPOINT_TOKEN) {
    headers.authorization = `Bearer ${process.env.REMOTE_ENDPOINT_TOKEN}`;
  }

  const bridgeResponse = await fetch(endpoint, {
    method: 'POST',
    headers,
    body: JSON.stringify(mediaAction),
  });

  if (!bridgeResponse.ok) {
    const body = await bridgeResponse.text();
    throw new Error(`Bridge returned ${bridgeResponse.status}: ${body}`);
  }
}

async function sendToSqs(mediaAction) {
  if (!SQSClient || !SendMessageCommand) {
    ({ SQSClient, SendMessageCommand } = require('@aws-sdk/client-sqs'));
  }

  const client = new SQSClient({});
  const message = {
    ...mediaAction,
    source: 'alexa-custom-skill',
    createdAt: new Date().toISOString(),
  };

  await client.send(new SendMessageCommand({
    QueueUrl: process.env.ALEXA_SAFARI_REMOTE_QUEUE_URL,
    MessageBody: JSON.stringify(message),
  }));
}

function slotValue(intent, slotName) {
  const slot = intent && intent.slots && intent.slots[slotName];
  return slot && slot.value ? String(slot.value).toLowerCase() : '';
}

function positiveNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) return null;
  return number;
}

function spokenConfirmation(mediaAction) {
  if (mediaAction.action === 'play') return 'Playing.';
  if (mediaAction.action === 'pause') return 'Paused.';
  if (mediaAction.action === 'toggle') return 'Toggled playback.';
  if (mediaAction.action === 'back') return `Rewinding ${mediaAction.seconds} seconds.`;
  if (mediaAction.action === 'forward') return `Skipping forward ${mediaAction.seconds} seconds.`;
  if (mediaAction.action === 'seek') return `Going to ${formatTime(mediaAction.seconds)}.`;
  if (mediaAction.action === 'fullscreen') return 'Fullscreen.';
  if (mediaAction.action === 'escape') return 'Exiting fullscreen.';
  if (mediaAction.action === 'open_codex') return 'Opening Codex. Prompt intake is armed for ten minutes.';
  if (mediaAction.action === 'codex_task') return 'Sent to Codex.';
  if (mediaAction.action === 'live_codex_prompt') return 'Sent to live Codex.';
  if (mediaAction.action === 'codex_status') return 'Checking Codex status.';
  if (mediaAction.action === 'codex_cancel') return 'Cancelling Codex.';
  if (mediaAction.action === 'codex_quit') return 'Closing Codex.';
  if (mediaAction.action === 'surfshark_disconnect') return 'Disconnecting Surfshark.';
  if (mediaAction.action === 'surfshark_connect_us') return 'Connecting Surfshark.';
  if (mediaAction.action === 'browser_open') return `Opening ${mediaAction.site}.`;
  if (mediaAction.action === 'browser_search') return `Searching ${mediaAction.site}.`;
  if (mediaAction.action === 'browser_command') return `${mediaAction.command}.`;
  if (mediaAction.action === 'browser_seek') return `Seeking ${mediaAction.seconds} seconds.`;
  if (mediaAction.action === 'browser_status') return 'Checking browser status.';
  return `${mediaAction.action}.`;
}

function formatTime(totalSeconds) {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) return `${hours} hours, ${minutes} minutes, ${seconds} seconds`;
  if (minutes > 0) return `${minutes} minutes, ${seconds} seconds`;
  return `${seconds} seconds`;
}

function responseOptionsForAction(mediaAction, sessionAttributes = {}) {
  if (mediaAction.action === 'open_codex') {
    return {
      shouldEndSession: false,
      reprompt: 'Say Codex followed by what you want me to do.',
      sessionAttributes: { ...sessionAttributes, liveCodexMode: true },
    };
  }
  return {};
}

function response(outputSpeech, options = {}) {
  const shouldEndSession = options.shouldEndSession !== undefined ? options.shouldEndSession : true;
  const result = {
    version: '1.0',
    sessionAttributes: options.sessionAttributes || {},
    response: {
      outputSpeech: {
        type: 'PlainText',
        text: outputSpeech,
      },
      shouldEndSession,
    },
  };
  if (options.reprompt) {
    result.response.reprompt = {
      outputSpeech: {
        type: 'PlainText',
        text: options.reprompt,
      },
    };
  }
  return {
    ...result,
  };
}

if (require.main === module && process.argv.includes('--selftest')) {
  const sample = {
    request: {
      type: 'IntentRequest',
      intent: {
        name: 'AbsoluteSeekIntent',
        slots: {
          minutes: { value: '12' },
          seconds: { value: '30' },
        },
      },
    },
  };

  exports.handler(sample).then((result) => {
    console.log(JSON.stringify(result, null, 2));
  });
}
