'use strict';

const assert = require('assert');
const skill = require('../alexa-skill/lambda');

async function invoke(intent) {
  const calls = [];
  const originalFetch = global.fetch;
  global.fetch = async (_url, options) => {
    calls.push(JSON.parse(options.body));
    return { ok: true };
  };
  process.env.REMOTE_ENDPOINT_URL = 'https://bridge.example.test';
  try {
    const result = await skill.handler({
      request: {
        type: 'IntentRequest',
        intent,
      },
    });
    return { result, calls };
  } finally {
    global.fetch = originalFetch;
    delete process.env.REMOTE_ENDPOINT_URL;
  }
}

(async () => {
  {
    const calls = [];
    const originalFetch = global.fetch;
    global.fetch = async (_url, options) => {
      calls.push(JSON.parse(options.body));
      return { ok: true };
    };
    process.env.REMOTE_ENDPOINT_URL = 'https://bridge.example.test';
    try {
      const result = await skill.handler({ request: { type: 'LaunchRequest' } });
      assert.deepStrictEqual(calls[0], { action: 'open_codex' });
      assert.strictEqual(result.response.outputSpeech.text, 'Opening Codex. Prompt intake is armed for ten minutes.');
    } finally {
      global.fetch = originalFetch;
      delete process.env.REMOTE_ENDPOINT_URL;
    }
  }

  {
    const { result, calls } = await invoke({ name: 'OpenCodexIntent', slots: {} });
    assert.deepStrictEqual(calls[0], { action: 'open_codex' });
    assert.strictEqual(result.response.outputSpeech.text, 'Opening Codex. Prompt intake is armed for ten minutes.');
  }

  {
    const { result, calls } = await invoke({
      name: 'AskCodexIntent',
      slots: { prompt: { value: 'open peacock and search ted' } },
    });
    assert.deepStrictEqual(calls[0], {
      action: 'codex_task',
      prompt: 'open peacock and search ted',
    });
    assert.strictEqual(result.response.outputSpeech.text, 'Sent to Codex.');
  }

  {
    const { result, calls } = await invoke({ name: 'CodexStatusIntent', slots: {} });
    assert.deepStrictEqual(calls[0], { action: 'codex_status' });
    assert.strictEqual(result.response.outputSpeech.text, 'Checking Codex status.');
  }

  {
    const { result, calls } = await invoke({ name: 'CancelCodexIntent', slots: {} });
    assert.deepStrictEqual(calls[0], { action: 'codex_cancel' });
    assert.strictEqual(result.response.outputSpeech.text, 'Cancelling Codex.');
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
