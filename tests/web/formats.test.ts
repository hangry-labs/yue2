import assert from 'node:assert/strict';
import { test } from 'node:test';
import { audioExtension, audioMime } from '../../web/src/lib/config.ts';

test('downloads retain each compressed container extension and MIME type', () => {
  for (const format of ['opus', 'ogg', 'flac', 'aac', 'm4a', 'mp3']) {
    assert.equal(audioExtension(format), format);
    assert.ok(audioMime(format).startsWith('audio/'));
  }
  assert.equal(audioMime('opus'), 'audio/ogg; codecs=opus');
  assert.equal(audioMime('m4a'), 'audio/mp4');
  for (const format of ['wav', 'wav16', 'wav24', 'wav32']) {
    assert.equal(audioExtension(format), 'wav');
    assert.equal(audioMime(format), 'audio/wav');
  }
});
