import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";
import { inputRequest } from "../../web/src/lib/generation.ts";
import { stringifyYamlRequest } from "../../web/src/lib/yaml.ts";

const { parse, stringify } = createRequire(
  new URL("../../web/package.json", import.meta.url),
)("yaml");

const request = () =>
  inputRequest(
    {
      style: "country pop, flute, warm vocals",
      lyrics: "[Verse 1]\nThe morning finds us here\n\n[Chorus]\nWe sing again\n",
      duration: 150,
      steps: 8,
      lm_seed: 123,
      seed: 456,
      synth_batch_size: 2,
      abc_sampling: { temperature: 0.8 },
      semantic_sampling: { top_k: 30 },
      adapters: [{ name: "example", scale: 0.5 }],
    },
    "fresh",
  );

test("ordinary YAML requests keep their readable formatting and values", () => {
  const input = request();
  const text = stringifyYamlRequest(input);
  assert.equal(text, stringify(input));
  assert.match(text, /lyrics: \|/);
  assert.deepEqual(parse(text), input);
});

const longLine = "Sing the morning light and carry our dreams into the sky "
  .repeat(4)
  .trimEnd();
const cases = {
  "first line starts with spaces": "  a\n  b",
  "mixed indentation": "  indented\nlines",
  "long first line starts with a space": ` ${longLine}\nNext line\n`,
  "long first line starts with a tab": `\t${longLine}\nNext line\n`,
  "leading blank line": "\n  a\nb",
  "leading line contains only spaces": "  \nabc",
  "multiple final newlines": "  a\n\n",
  "only spaces and a newline": " \n",
  "only spaces and newlines": " \n \n",
  "Windows newlines": "  hello\r\nworld\r\n",
  Unicode: "  明日の歌\nŻółty świt 🎵\n",
  "long unindented line": `${longLine}\nNext line\n`,
  "YAML punctuation": '[Chorus]\nNo: yes # moon & stars * sing "again"\n',
  "empty text": "",
};

for (const [name, value] of Object.entries(cases)) {
  for (const field of ["lyrics", "style"] as const) {
    test(`YAML export preserves ${field}: ${name}`, () => {
      const input = { ...request(), [field]: value };
      const before = structuredClone(input);
      assert.deepEqual(parse(stringifyYamlRequest(input)), input);
      assert.deepEqual(input, before);
      assert.deepEqual(JSON.parse(JSON.stringify(input)), input);
    });
  }
}

test("affected requests use the quoted fallback without changing other fields", () => {
  const input = { ...request(), lyrics: ` ${longLine}\nNext line\n` };
  assert.notDeepEqual(parse(stringify(input)), input);
  const text = stringifyYamlRequest(input);
  assert.match(text, /"lyrics": "/);
  assert.deepEqual(parse(text), input);
});

test("unsupported request values stop export instead of producing a changed request", () => {
  const input = { ...request(), lyrics: undefined };
  assert.throws(() => stringifyYamlRequest(input), /Try saving as JSON/);
});
