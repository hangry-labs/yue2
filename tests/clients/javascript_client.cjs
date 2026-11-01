// Explicit live SDK check. Run with openai installed in this script's parent tree.
const fs = require('node:fs');
const crypto = require('node:crypto');
const { OpenAI } = require(process.env.YUE2_OPENAI_MODULE || 'openai');

async function main() {
  const [baseURL, fixture, output] = process.argv.slice(2);
  const original = JSON.parse(fs.readFileSync(fixture, 'utf8'));
  const { style, lyrics, output_format, ...settings } = original;
  const client = new OpenAI({ baseURL: baseURL.replace(/\/$/, '') + '/v1', apiKey: process.env.YUE2_API_KEY || 'local',
    timeout: 180000, maxRetries: 0 });
  if ((await client.models.list()).data[0].id !== 'yue2') throw new Error('Wrong model');
  const response = await client.audio.speech.create({ ...settings, model: 'yue2', input: lyrics,
    instructions: style, voice: 'auto', response_format: 'wav' });
  const bytes = Buffer.from(await response.arrayBuffer());
  if (response.headers.get('x-audio-sample-rate') !== '48000' || response.headers.get('x-audio-channels') !== '2')
    throw new Error('Audio quality contract differs');
  if (bytes.subarray(0, 4).toString() !== 'RIFF') throw new Error('Expected WAV bytes');
  fs.writeFileSync(output, bytes);
  console.log(JSON.stringify({ sdk: 'javascript', version: OpenAI.VERSION, wav_sha256: crypto.createHash('sha256').update(bytes).digest('hex') }));
}
main().catch(error => { console.error(error); process.exit(1); });
