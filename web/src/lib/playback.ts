// Listening gain only; exported audio always retains its original samples.
export const DEFAULT_PLAYBACK_VOLUME = 1;

export function playbackVolume(value: unknown): number {
	return typeof value === 'number' && Number.isFinite(value)
		? Math.max(0, Math.min(1, value))
		: DEFAULT_PLAYBACK_VOLUME;
}

export function trackGain(volume: number, tracks: number): number {
	return playbackVolume(volume) / Math.sqrt(Math.max(1, tracks));
}
