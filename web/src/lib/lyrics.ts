import type { Yue2Request } from './types.js';

// Scores and audio codes describe a particular set of words. Editing those
// words starts a fresh composition instead of quietly retaining the old take.
export function updateLyrics(request: Yue2Request, lyrics: string): boolean {
	if (lyrics === (request.lyrics || '')) return false;
	request.lyrics = lyrics;
	return clearCompositionInputs(request);
}

export function clearCompositionInputs(request: Yue2Request): boolean {
	const cleared = Boolean(
		request.abc?.trim() || request.semantic_tokens?.trim() || request.source_tokens?.trim()
	);
	request.abc = '';
	request.semantic_tokens = '';
	request.source_tokens = '';
	request.source_start = undefined;
	request.source_end = undefined;
	return cleared;
}
