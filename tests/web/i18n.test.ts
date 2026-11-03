import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { catalogs, LOCALES, localePath, resolveLocale, translate } from '../../web/src/lib/i18n.ts';

test('all six offline UI catalogs contain every message with the same placeholders', () => {
	const keys = Object.keys(catalogs.en).sort();
	assert(keys.length > 350);
	assert.deepEqual(LOCALES.map(locale => locale.code), ['en', 'nb', 'pl', 'ja', 'zh', 'es']);
	for (const locale of LOCALES) {
		assert.deepEqual(Object.keys(catalogs[locale.code]).sort(), keys);
		for (const key of keys) {
			const value = catalogs[locale.code][key];
			assert(value.length > 0, `${locale.code}: ${key}`);
			assert(!value.includes('\uFFFD'), `${locale.code}: replacement character`);
			assert.deepEqual([...(key.match(/\{\w+\}/g) || [])].sort(), [...(value.match(/\{\w+\}/g) || [])].sort());
		}
	}
});

test('explicit locale routes precede saved preferences and English is the default', () => {
	assert.equal(resolveLocale('/', null), 'en');
	assert.equal(resolveLocale('/', 'pl'), 'pl');
	assert.equal(resolveLocale('/ja', 'pl'), 'ja');
	assert.equal(resolveLocale('/en/docs/', 'nb'), 'en');
	assert.equal(resolveLocale('/invalid', 'invalid'), 'en');
	assert.equal(localePath('zh', '/pl/docs/'), '/zh/docs');
	assert.equal(localePath('es', '/nb/'), '/es');
});

test('translation keeps supplied words literal and falls back for unknown diagnostics', () => {
	assert.equal(translate('pl', 'Lyrics'), 'Tekst piosenki');
	assert.equal(translate('ja', 'Opened: {value}', { value: '[Verse] <b>Hello</b> {title}' }), '開きました：[Verse] <b>Hello</b> {title}');
	assert.equal(translate('zh', 'Unrecognized model diagnostic'), 'Unrecognized model diagnostic');
	assert.equal(translate('es', 'Invalid {format} file'), 'Archivo {format} no válido');
});

test('locale pages keep calls at the API root, including trailing-slash routes', () => {
	const api = readFileSync(new URL('../../web/src/lib/api.ts', import.meta.url), 'utf8');
	assert(!/fetch\((['"`])(?:job|props)/.test(api));
	assert(!/submitJob\((['"])(?:synth|transcribe|tokenize|vae)/.test(api));
	for (const file of ['GpuMonitor', 'QueueMonitor', 'LogCard']) {
		const source = readFileSync(new URL(`../../web/src/components/${file}.svelte`, import.meta.url), 'utf8');
		assert(!/(?:fetch|EventSource)\((['"])(?:system|logs)/.test(source));
	}
});
