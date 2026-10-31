import { buildSparse } from './fields.ts';
import type { Yue2Request } from './types.js';

export type InputMode = 'fresh' | 'score' | 'replay' | 'source';

// Only deliberate reuse can condition a new request on an earlier performance.
// Resolve seeds on the snapshot, never on the editable form.
export function inputRequest(input: Yue2Request, mode: InputMode): Yue2Request {
	const request = buildSparse(input);
	if (mode !== 'score' && mode !== 'replay') delete request.abc;
	if (mode !== 'replay') delete request.semantic_tokens;
	if (mode !== 'source') {
		delete request.source_tokens;
		delete request.source_start;
		delete request.source_end;
	}
	return request;
}

export function generationRequest(
	input: Yue2Request,
	mode: InputMode,
	random: () => number = Math.random
): Yue2Request {
	const request = inputRequest(input, mode);
	for (const key of ['lm_seed', 'seed'] as const) {
		if (request[key] == null || request[key]! < 0)
			request[key] = Math.floor(random() * 0x100000000);
	}
	return request;
}

export function editablePrompt(input: Yue2Request): Yue2Request {
	const request = buildSparse(input);
	for (const key of [
		'abc',
		'semantic_tokens',
		'source_tokens',
		'source_start',
		'source_end',
		'lm_seed',
		'seed'
	] as const)
		delete request[key];
	return request;
}
