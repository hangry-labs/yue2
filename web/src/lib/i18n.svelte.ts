import {
	LOCALES,
	LOCALE_STORAGE_KEY,
	isLocale,
	localePath,
	resolveLocale,
	translate,
	type Locale
} from './i18n.js';
export { LOCALES };

let stored: string | null = null;
try {
	stored = localStorage.getItem(LOCALE_STORAGE_KEY);
} catch {
	/* Preferences are optional. */
}
export const language = $state({ code: resolveLocale(location.pathname, stored) });
document.documentElement.lang = language.code;
document.title = translate(language.code, 'YuE2 Music Studio · Hangry Labs');

export function setLocale(value: string): void {
	if (!isLocale(value)) return;
	language.code = value;
	document.documentElement.lang = value;
	document.title = translate(value, 'YuE2 Music Studio · Hangry Labs');
	try {
		localStorage.setItem(LOCALE_STORAGE_KEY, value);
	} catch {
		/* Preferences are optional. */
	}
	const url = new URL(location.href);
	url.pathname = localePath(value, url.pathname);
	history.replaceState(history.state, '', url);
}

export function msg(source: string, variables: Record<string, unknown> = {}): string {
	return translate(language.code, source, variables);
}

// Keep backend diagnostics and user text intact; translate known UI wrappers.
export function feedback(source: string): string {
	for (const prefix of [
		'Opened: ',
		'Transcribed: ',
		'Transcription failed: ',
		'Tokenized: ',
		'Tokenization failed: ',
		'Unsupported file type: '
	]) {
		if (source.startsWith(prefix))
			return msg(`${prefix}{value}`, { value: source.slice(prefix.length) });
	}
	const invalid = /^Invalid (JSON|YAML|YML) file$/.exec(source);
	if (invalid) return msg('Invalid {format} file', { format: invalid[1] });
	return msg(source);
}
