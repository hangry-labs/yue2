import assert from "node:assert/strict";
import { test } from "node:test";
import {
  generationRequest,
  editablePrompt,
  variationCount,
} from "../../web/src/lib/generation.ts";

const input = () => ({
  style: "piano pop",
  lyrics: "Sing the current words",
  abc: "old tune",
  semantic_tokens: "1,2",
  source_tokens: "3,4",
  source_start: 1,
  source_end: 2,
  steps: 8,
  abc_sampling: { temperature: 0.8 },
  semantic_sampling: {},
  adapters: [{ name: "example", scale: 0.5 }],
});

test("ordinary takes use current text and independent seeds without changing the form", () => {
  const form = input();
  const before = structuredClone(form);
  const a = generationRequest(form, "fresh", () => 0.1);
  form.lyrics = "New lyrics: Don’t forget the moon";
  const b = generationRequest(form, "fresh", () => 0.2);
  assert.equal(a.synth_batch_size, 2);
  assert.equal(b.synth_batch_size, 2);
  for (const key of [
    "abc",
    "semantic_tokens",
    "source_tokens",
    "source_start",
    "source_end",
  ]) {
    assert.equal(a[key], undefined);
    assert.equal(b[key], undefined);
  }
  assert.notEqual(a.lm_seed, b.lm_seed);
  assert.notEqual(a.seed, b.seed);
  assert.equal(b.lyrics, form.lyrics);
  assert.deepEqual({ ...form, lyrics: before.lyrics }, before);
  a.abc_sampling.temperature = 100;
  a.adapters![0].scale = 10;
  assert.equal(form.abc_sampling.temperature, 0.8);
  assert.equal(form.adapters[0].scale, 0.5);
});

test("fixed seeds remain an explicit override and negative seeds request fresh randomness", () => {
  const form = { ...input(), lm_seed: 42, seed: -1 };
  const r = generationRequest(form, "fresh", () => 0.5);
  assert.equal(r.lm_seed, 42);
  assert.equal(r.seed, 2147483648);
  assert.equal(form.seed, -1);
});

test("reuse is deliberate and each input mode excludes unrelated conditioning", () => {
  const score = generationRequest(input(), "score");
  assert.equal(score.abc, "old tune");
  assert.equal(score.semantic_tokens, undefined);
  assert.equal(score.source_tokens, undefined);
  const replay = generationRequest(input(), "replay");
  assert.equal(replay.synth_batch_size, 1);
  assert.equal(replay.semantic_tokens, "1,2");
  assert.equal(replay.source_tokens, undefined);
  const source = generationRequest(input(), "source");
  assert.equal(source.source_tokens, "3,4");
  assert.equal(source.source_start, 1);
  assert.equal(source.abc, undefined);
  assert.equal(source.semantic_tokens, undefined);
});

test("editing a saved prompt removes generated conditioning and resolved replay seeds", () => {
  const saved = { ...input(), lm_seed: 123, seed: 456, synth_batch_size: 1 };
  const prompt = editablePrompt(saved);
  assert.equal(prompt.lyrics, saved.lyrics);
  assert.equal(prompt.steps, 8);
  assert.equal(prompt.synth_batch_size, undefined);
  assert.equal(generationRequest(prompt, "fresh").synth_batch_size, 2);
  assert.equal(prompt.lm_seed, undefined);
  assert.equal(prompt.seed, undefined);
  assert.equal(prompt.abc, undefined);
  assert.equal(prompt.semantic_tokens, undefined);
  assert.equal(saved.abc, "old tune");
});

test("variation choices retain explicit values and bound older saved settings", () => {
  assert.equal(variationCount(undefined), 2);
  assert.equal(variationCount(""), 2);
  assert.equal(variationCount(2.5), 2);
  assert.equal(variationCount(true), 2);
  for (const count of [1, 2, 3]) {
    assert.equal(generationRequest({ ...input(), synth_batch_size: count }, "fresh").synth_batch_size, count);
    assert.equal(generationRequest({ ...input(), synth_batch_size: count }, "replay").synth_batch_size, count);
  }
  const old = { ...input(), synth_batch_size: 9 };
  assert.equal(generationRequest(old, "fresh").synth_batch_size, 3);
  assert.equal(old.synth_batch_size, 9);
});
