import { mount } from 'svelte';
import App from './App.svelte';
import favicon from './assets/yue2_favicon.webp';

// Import through Vite so the standalone HTML contains the favicon data too.
document.querySelector<HTMLLinkElement>('link[rel="icon"]')!.href = favicon;

mount(App, { target: document.getElementById('app')! });
