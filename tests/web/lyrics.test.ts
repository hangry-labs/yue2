import assert from "node:assert/strict";
import { test } from "node:test";
import {
  canAdoptScore,
  clearCompositionInputs,
  updateLyrics,
} from "../../web/src/lib/lyrics.ts";

function request() {
  return {
    style: "pop",
    lyrics: "Original words",
    abc: "old score",
    semantic_tokens: "1,2",
    source_tokens: "3,4",
    source_start: 10,
    source_end: 20,
    steps: 8,
    lm_seed: 42,
    abc_sampling: { temperature: 0.7 },
    semantic_sampling: { top_k: 100 },
  };
}

test("edited lyrics remove old conditioning and retain generation settings", () => {
  const value = request();
  assert.equal(updateLyrics(value, "New words: Don’t forget the moon."), true);
  assert.equal(value.lyrics, "New words: Don’t forget the moon.");
  for (const key of ["abc", "semantic_tokens", "source_tokens"])
    assert.equal(value[key], "");
  assert.equal(value.source_start, undefined);
  assert.equal(value.source_end, undefined);
  assert.equal(value.steps, 8);
  assert.equal(value.lm_seed, 42);
  assert.deepEqual(value.abc_sampling, { temperature: 0.7 });
});

test("an unchanged lyric input preserves an intentional score or replay", () => {
  const value = request();
  const before = structuredClone(value);
  assert.equal(updateLyrics(value, value.lyrics), false);
  assert.deepEqual(value, before);
});

test("a previously saved composition can be cleared without changing lyrics or settings", () => {
  const value = request();
  assert.equal(clearCompositionInputs(value), true);
  assert.equal(value.lyrics, "Original words");
  assert.equal(value.steps, 8);
  assert.equal(value.lm_seed, 42);
  assert.equal(value.abc, "");
  assert.equal(value.semantic_tokens, "");
});

test("a finished job cannot overwrite newer lyrics, musical direction or manual score edits", () => {
  const submitted = request();
  for (const key of ["lyrics", "style", "abc"]) {
    const current = { ...submitted, [key]: "New input" };
    assert.equal(canAdoptScore(current, submitted), false);
  }
  assert.equal(canAdoptScore(request(), submitted), true);
});
