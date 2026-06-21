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

async function invokeWithSession(intent, attributes) {
  const calls = [];
  const originalFetch = global.fetch;
  global.fetch = async (_url, options) => {
    calls.push(JSON.parse(options.body));
    return { ok: true };
  };
  process.env.REMOTE_ENDPOINT_URL = 'https://bridge.example.test';
  try {
    const result = await skill.handler({
      session: { attributes },
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
      assert.strictEqual(result.response.outputSpeech.text, 'Opening Codex. Say Codex followed by what you want me to do.');
      assert.strictEqual(result.response.shouldEndSession, false);
      assert.strictEqual(result.sessionAttributes.liveCodexMode, true);
    } finally {
      global.fetch = originalFetch;
      delete process.env.REMOTE_ENDPOINT_URL;
    }
  }

  {
    const { result, calls } = await invoke({ name: 'OpenCodexIntent', slots: {} });
    assert.deepStrictEqual(calls[0], { action: 'open_codex' });
    assert.strictEqual(result.response.outputSpeech.text, 'Opening Codex. Prompt intake is armed for ten minutes.');
    assert.strictEqual(result.response.shouldEndSession, false);
    assert.strictEqual(result.sessionAttributes.liveCodexMode, true);
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
    const { result, calls } = await invoke({
      name: 'AskCodexIntent',
      slots: { prompt: { value: 'open Peacock' } },
    });
    assert.deepStrictEqual(calls[0], { action: 'browser_open', site: 'peacock' });
    assert.strictEqual(result.response.outputSpeech.text, 'Opening peacock.');
  }

  {
    const { result, calls } = await invoke({
      name: 'AskCodexIntent',
      slots: { prompt: { value: 'search Disney for Andor' } },
    });
    assert.deepStrictEqual(calls[0], { action: 'browser_search', site: 'disney', query: 'andor' });
    assert.strictEqual(result.response.outputSpeech.text, 'Searching disney.');
  }

  {
    const { result, calls } = await invoke({
      name: 'SearchYoutubeIntent',
      slots: { query: { value: 'fireplace' } },
    });
    assert.deepStrictEqual(calls[0], { action: 'browser_search', site: 'youtube', query: 'fireplace' });
    assert.strictEqual(result.response.outputSpeech.text, 'Searching youtube.');
  }

  {
    const { result, calls } = await invoke({
      name: 'LiveCodexPromptIntent',
      slots: { prompt: { value: 'use chrome and find my episode' } },
    });
    assert.deepStrictEqual(calls[0], {
      action: 'live_codex_prompt',
      prompt: 'use chrome and find my episode',
    });
    assert.strictEqual(result.response.outputSpeech.text, 'Sent to live Codex.');
  }

  {
    const { result, calls } = await invokeWithSession({
      name: 'AskCodexIntent',
      slots: { prompt: { value: 'codex open chrome and find the episode I was watching' } },
    }, { liveCodexMode: true });
    assert.deepStrictEqual(calls[0], {
      action: 'live_codex_prompt',
      prompt: 'open chrome and find the episode i was watching',
    });
    assert.strictEqual(result.response.outputSpeech.text, 'Sent to live Codex.');
  }

  {
    const { result, calls } = await invoke({
      name: 'CodexExecIntent',
      slots: { prompt: { value: 'summarize repo status' } },
    });
    assert.deepStrictEqual(calls[0], {
      action: 'codex_task',
      prompt: 'summarize repo status',
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
