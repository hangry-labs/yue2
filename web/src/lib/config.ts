// UI constants
export const PROPS_POLL_MS = 10000;
export const FETCH_TIMEOUT_MS = 2000;
export const JOB_POLL_MS = 2000;
export const SSE_RECONNECT_MS = 2000;
export const LOG_MAX_LINES = 50;
export const WAVEFORM_HEIGHT = 64;
export const WAVEFORM_BINS = 4096;

// audio output formats (mirror request.h)
export const OUTPUT_FORMATS = [
	'mp3',
	'opus',
	'ogg',
	'flac',
	'aac',
	'm4a',
	'wav16',
	'wav24',
	'wav32'
] as const;
export const INPUT_AUDIO_FORMATS = [
	'mp3',
	'opus',
	'ogg',
	'flac',
	'aac',
	'm4a',
	'mp4',
	'webm',
	'wav'
];
const AUDIO_MIME: Record<string, string> = {
	mp3: 'audio/mpeg',
	opus: 'audio/ogg; codecs=opus',
	ogg: 'audio/ogg',
	flac: 'audio/flac',
	aac: 'audio/aac',
	m4a: 'audio/mp4',
	mp4: 'audio/mp4',
	webm: 'audio/webm',
	wav: 'audio/wav',
	wav16: 'audio/wav',
	wav24: 'audio/wav',
	wav32: 'audio/wav'
};
export function audioExtension(format: string): string {
	return format.startsWith('wav') ? 'wav' : format;
}
export function audioMime(format: string): string {
	return AUDIO_MIME[format] || 'application/octet-stream';
}

// Chain of thought modes of the protocol, a closed set the checkpoint freezes
export const COT_FULL = 'full';
export const COT_MELODY = 'melody';
export const COT_OFF = 'off';
