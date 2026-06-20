'use strict';

const assert = require('assert');
const http = require('http');
const { handler } = require('./index');

async function main() {
  await testDryRun();
  await testBridgePayload();
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

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
