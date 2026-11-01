import assert from "node:assert/strict";
import { test } from "node:test";
import {
  DEFAULT_PLAYBACK_VOLUME,
  playbackVolume,
  trackGain,
} from "../../web/src/lib/playback.ts";

test("fresh playback uses the original level for a single track", () => {
  assert.equal(DEFAULT_PLAYBACK_VOLUME, 1);
  assert.equal(trackGain(playbackVolume(undefined), 1), 1);
  assert.equal(trackGain(1, 0), 1);
});

test("saved volume choices including silence are retained and constrained", () => {
  for (const volume of [0, 0.25, 0.5, 1]) {
    assert.equal(playbackVolume(volume), volume);
  }
  assert.equal(playbackVolume(-1), 0);
  assert.equal(playbackVolume(2), 1);
  for (const value of [undefined, null, "0.5", NaN, Infinity]) {
    assert.equal(playbackVolume(value), 1);
  }
});

test("simultaneous tracks retain shared mix headroom without changing the saved level", () => {
  assert.equal(trackGain(1, 2), 1 / Math.sqrt(2));
  assert.equal(trackGain(0.5, 4), 0.25);
  assert.equal(trackGain(0, 4), 0);
});
