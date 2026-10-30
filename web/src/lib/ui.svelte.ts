export type View = 'create' | 'library' | 'api' | 'system';
const KEY = 'yue2-ui-session-v1';
let restored: { view?: View; collapsed?: boolean } = {};
try {
	restored = JSON.parse(sessionStorage.getItem(KEY) || '{}');
} catch {
	/* Storage is optional. */
}
export const ui = $state({
	view: (['create', 'library', 'api', 'system'].includes(restored?.view ?? '')
		? restored.view
		: 'create') as View,
	collapsed: restored?.collapsed === true,
	examplesOpen: false
});
$effect.root(() => {
	$effect(() => {
		const value = JSON.stringify({ view: ui.view, collapsed: ui.collapsed });
		try {
			sessionStorage.setItem(KEY, value);
		} catch {
			/* Storage is optional. */
		}
	});
});
