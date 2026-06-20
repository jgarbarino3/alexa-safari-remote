'use strict';

let SQSClient;
let SendMessageCommand;

const ACTION_BY_INTENT = {
  PlayIntent: { action: 'play' },
  PauseIntent: { action: 'pause' },
  ToggleIntent: { action: 'toggle' },
  FullscreenIntent: { action: 'fullscreen' },
  EscapeIntent: { action: 'escape' },
};

exports.handler = async (event) => {
  const request = event && event.request ? event.request : {};

  if (request.type === 'LaunchRequest') {
    return response('TV remote is ready.');
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

  const mediaAction = buildMediaAction(request.intent);
  if (!mediaAction) {
    return response('I did not understand that remote command.');
  }

  await sendToBridge(mediaAction);
  return response(spokenConfirmation(mediaAction));
};

function buildMediaAction(intent) {
  const intentName = intent && intent.name;

  if (ACTION_BY_INTENT[intentName]) {
    return ACTION_BY_INTENT[intentName];
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

function response(outputSpeech) {
  return {
    version: '1.0',
    response: {
      outputSpeech: {
        type: 'PlainText',
        text: outputSpeech,
      },
      shouldEndSession: true,
    },
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
