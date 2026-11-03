import { parse, stringify } from 'yaml';
import type { Yue2Request } from './types.js';

function sameValue(expected: unknown, actual: unknown): boolean {
	if (Object.is(expected, actual)) return true;
	if (Array.isArray(expected)) {
		return (
			Array.isArray(actual) &&
			expected.length === actual.length &&
			expected.every((value, index) => sameValue(value, actual[index]))
		);
	}
	if (
		expected === null ||
		actual === null ||
		typeof expected !== 'object' ||
		typeof actual !== 'object'
	)
		return false;
	const left = expected as Record<string, unknown>;
	const right = actual as Record<string, unknown>;
	const keys = Object.keys(left);
	return (
		keys.length === Object.keys(right).length &&
		keys.every((key) => Object.hasOwn(right, key) && sameValue(left[key], right[key]))
	);
}

function preservesRequest(text: string, request: Yue2Request): boolean {
	try {
		return sameValue(request, parse(text));
	} catch {
		return false;
	}
}

export function stringifyYamlRequest(request: Yue2Request): string {
	const readable = stringify(request);
	if (preservesRequest(readable, request)) return readable;

	// Quoted strings preserve whitespace when block formatting changes its value.
	const quoted = stringify(request, {
		blockQuote: false,
		defaultStringType: 'QUOTE_DOUBLE',
		lineWidth: 0
	});
	if (preservesRequest(quoted, request)) return quoted;
	throw new Error('Could not preserve this request in YAML. Try saving as JSON.');
}
