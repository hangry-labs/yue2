import en from './locales/en.json' with { type: 'json' };
import nb from './locales/nb.json' with { type: 'json' };
import pl from './locales/pl.json' with { type: 'json' };
import ja from './locales/ja.json' with { type: 'json' };
import zh from './locales/zh.json' with { type: 'json' };
import es from './locales/es.json' with { type: 'json' };

export const LOCALES = [
	{ code: 'en', name: 'English' },
	{ code: 'nb', name: 'Norsk bokmål' },
	{ code: 'pl', name: 'Polski' },
	{ code: 'ja', name: '日本語' },
	{ code: 'zh', name: '简体中文' },
	{ code: 'es', name: 'Español' }
] as const;
export type Locale = (typeof LOCALES)[number]['code'];
export const catalogs: Record<Locale, Record<string, string>> = { en, nb, pl, ja, zh, es };
export const LOCALE_STORAGE_KEY = 'yue2-ui-locale-v1';

export function isLocale(value: unknown): value is Locale {
	return LOCALES.some((locale) => locale.code === value);
}

export function resolveLocale(pathname: string, stored: unknown): Locale {
	const direct = /^\/(en|nb|pl|ja|zh|es)(?:\/docs)?\/?$/.exec(pathname)?.[1];
	return isLocale(direct) ? direct : isLocale(stored) ? stored : 'en';
}

export function localePath(locale: Locale, pathname: string): string {
	return `/${locale}${/\/docs\/?$/.test(pathname) ? '/docs' : ''}`;
}

export function translate(
	locale: Locale,
	source: string,
	variables: Record<string, unknown> = {}
): string {
	const template = catalogs[locale][source] ?? catalogs.en[source] ?? source;
	return template.replace(/\{([\w]+)\}/g, (match, key) =>
		Object.hasOwn(variables, key) ? String(variables[key]) : match
	);
}
