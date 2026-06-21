'use strict';

const assert = require('assert');
const http = require('http');
const { handler } = require('./index');

async function main() {
  await testDryRun();
  await testBridgePayload();
  await testCodexPromptPayload();
  await testBrowserPromptPayload();
  await testLiveCodexPayload();
  console.log('OK:lambda-tests');
}

async function testDryRun() {
  delete process.env.ALEXA_SAFARI_REMOTE_QUEUE_URL;
  delete process.env.REMOTE_ENDPOINT_URL;

  const result = await handler({
    request: {
      type: 'IntentRequest',
      intent: { name: 'PauseIntent', slots: {} },
    },
  });

  assert.strictEqual(result.response.outputSpeech.text, 'Paused.');
}

async function testBridgePayload() {
  delete process.env.ALEXA_SAFARI_REMOTE_QUEUE_URL;

  const receivedBodies = [];
  const server = http.createServer((request, response) => {
    let body = '';
    request.on('data', (chunk) => {
      body += chunk;
    });
    request.on('end', () => {
      receivedBodies.push(JSON.parse(body));
      response.writeHead(204);
      response.end();
    });
  });

  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  process.env.REMOTE_ENDPOINT_URL = `http://127.0.0.1:${address.port}/command`;

  try {
    const result = await handler({
      request: {
        type: 'IntentRequest',
        intent: {
          name: 'RelativeSeekIntent',
          slots: {
            direction: { value: 'forward' },
            amount: { value: '30' },
            unit: { value: 'seconds' },
          },
        },
      },
    });

    assert.strictEqual(result.response.outputSpeech.text, 'Skipping forward 30 seconds.');
    assert.deepStrictEqual(receivedBodies, [{ action: 'forward', seconds: 30 }]);
  } finally {
    await new Promise((resolve) => server.close(resolve));
    delete process.env.REMOTE_ENDPOINT_URL;
  }
}

async function testCodexPromptPayload() {
  delete process.env.ALEXA_SAFARI_REMOTE_QUEUE_URL;

  const receivedBodies = [];
  const server = http.createServer((request, response) => {
    let body = '';
    request.on('data', (chunk) => {
      body += chunk;
    });
    request.on('end', () => {
      receivedBodies.push(JSON.parse(body));
      response.writeHead(204);
      response.end();
    });
  });

  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  process.env.REMOTE_ENDPOINT_URL = `http://127.0.0.1:${address.port}/command`;

  try {
    const result = await handler({
      request: {
        type: 'IntentRequest',
        intent: {
          name: 'AskCodexIntent',
          slots: {
            prompt: { value: 'summarize the repo status' },
          },
        },
      },
    });

    assert.strictEqual(result.response.outputSpeech.text, 'Sent to Codex.');
    assert.deepStrictEqual(receivedBodies, [{ action: 'codex_task', prompt: 'summarize the repo status' }]);
  } finally {
    await new Promise((resolve) => server.close(resolve));
    delete process.env.REMOTE_ENDPOINT_URL;
  }
}

async function testBrowserPromptPayload() {
  delete process.env.ALEXA_SAFARI_REMOTE_QUEUE_URL;

  const receivedBodies = [];
  const server = http.createServer((request, response) => {
    let body = '';
    request.on('data', (chunk) => {
      body += chunk;
    });
    request.on('end', () => {
      receivedBodies.push(JSON.parse(body));
      response.writeHead(204);
      response.end();
    });
  });

  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  process.env.REMOTE_ENDPOINT_URL = `http://127.0.0.1:${address.port}/command`;

  try {
    const result = await handler({
      request: {
        type: 'IntentRequest',
        intent: {
          name: 'OpenSiteIntent',
          slots: {
            site: { value: 'peacock' },
          },
        },
      },
    });

    assert.strictEqual(result.response.outputSpeech.text, 'Opening peacock.');
    assert.deepStrictEqual(receivedBodies, [{ action: 'browser_open', site: 'peacock' }]);
  } finally {
    await new Promise((resolve) => server.close(resolve));
    delete process.env.REMOTE_ENDPOINT_URL;
  }
}

async function testLiveCodexPayload() {
  delete process.env.ALEXA_SAFARI_REMOTE_QUEUE_URL;

  const receivedBodies = [];
  const server = http.createServer((request, response) => {
    let body = '';
    request.on('data', (chunk) => {
      body += chunk;
    });
    request.on('end', () => {
      receivedBodies.push(JSON.parse(body));
      response.writeHead(204);
      response.end();
    });
  });

  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  process.env.REMOTE_ENDPOINT_URL = `http://127.0.0.1:${address.port}/command`;

  try {
    const result = await handler({
      request: {
        type: 'IntentRequest',
        intent: {
          name: 'LiveCodexPromptIntent',
          slots: {
            prompt: { value: 'use chrome and find peacock' },
          },
        },
      },
    });

    assert.strictEqual(result.response.outputSpeech.text, 'Sent to live Codex.');
    assert.deepStrictEqual(receivedBodies, [{ action: 'live_codex_prompt', prompt: 'use chrome and find peacock' }]);
  } finally {
    await new Promise((resolve) => server.close(resolve));
    delete process.env.REMOTE_ENDPOINT_URL;
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
