/* SPDX-License-Identifier: MIT. Local-only listening gallery, with no runtime dependencies. */
(() => {
  const root = document.querySelector('.song-gallery');
  const catalog = window.YUE2_GALLERY;
  if (!root || !catalog?.songs?.length) {
    root?.querySelector('[data-count]')?.replaceChildren(document.createTextNode('Recordings are unavailable. Please try again later.'));
    return;
  }
  const grid = root.querySelector('.song-grid');
  const status = root.querySelector('[data-playing]');
  const volume = root.querySelector('[data-volume]');
  const mute = root.querySelector('[data-mute]');
  const players = [];
  let muted = false;
  try { const saved = Number(localStorage.getItem('yue2-gallery-volume') ?? 0.7); volume.value = String(Math.max(0, Math.min(1, Number.isFinite(saved) ? saved : 0.7))); } catch { /* Listening still works without storage. */ }
  const time = value => `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, '0')}`;
  const text = (element, selector, value) => { element.querySelector(selector).textContent = value; };
  function sound() {
    for (const {audio} of players) { audio.volume = Number(volume.value); audio.muted = muted; }
    mute.textContent = muted ? 'Muted' : 'Sound on';
    mute.setAttribute('aria-label', muted ? 'Unmute audio' : 'Mute audio');
    mute.setAttribute('aria-pressed', String(muted));
  }
  volume.addEventListener('input', () => { sound(); try { localStorage.setItem('yue2-gallery-volume', volume.value); } catch { /* Optional preference. */ } });
  mute.addEventListener('click', () => { muted = !muted; sound(); });

  for (const [index, song] of catalog.songs.entries()) {
    const fragment = root.querySelector('#song-card-template').content.cloneNode(true);
    const card = fragment.querySelector('.song-card');
    card.dataset.category = song.category;
    card.id = song.id;
    text(card, '[data-category]', `${String(index + 1).padStart(2, '0')} / ${song.category} · ${song.language}`);
    text(card, '[data-title]', song.title);
    text(card, '[data-description]', song.description);
    text(card, '[data-duration]', time(song.audio.seconds));
    text(card, '[data-length]', time(song.audio.seconds));
    text(card, '[data-style]', song.request.style);
    text(card, '[data-lyrics]', song.request.lyrics || 'No lyrics supplied. Instrumental direction.');
    const facts = [['Score mode', song.request.cot], ['Steps', song.request.steps], ['LM seed', song.request.lm_seed], ['Noise seed', song.request.seed], ['Audio', 'MP3 · 48 kHz · stereo'], ['Engine', catalog.engine.version]];
    for (const [key, value] of facts) {
      const dt = document.createElement('dt'), dd = document.createElement('dd');
      dt.textContent = key; dd.textContent = String(value); card.querySelector('.recipe-facts').append(dt, dd);
    }
    for (const [selector, asset] of [['[data-audio]', song.audio], ['[data-recipe]', song.recipe], ['[data-replay]', song.replay]]) card.querySelector(selector).href = asset.path;
    card.querySelector('[data-copy]').addEventListener('click', async event => {
      const copyButton = event.currentTarget;
      const request = JSON.stringify({title: song.title, ...song.request}, null, 2);
      const live = root.querySelector('[data-copy-status]');
      try { await navigator.clipboard.writeText(request); copyButton.textContent = 'Copied'; live.textContent = `${song.title} request copied.`; }
      catch { copyButton.textContent = 'Clipboard unavailable'; live.textContent = 'Clipboard unavailable. Download Prompt JSON instead.'; }
    });
    const audio = card.querySelector('audio'), button = card.querySelector('[data-play]'), seek = card.querySelector('[data-seek]');
    audio.src = song.audio.path;
    audio.setAttribute('aria-label', song.title);
    seek.setAttribute('aria-label', `Seek in ${song.title}`);
    const waveform = card.querySelector('.waveform');
    for (const [i, peak] of (song.waveform || []).entries()) {
      const bar = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      const height = Math.max(2, Math.min(1, Math.max(0, Number(peak))) * 44);
      bar.setAttribute('x', String(i * 4)); bar.setAttribute('y', String((48 - height) / 2));
      bar.setAttribute('width', '2'); bar.setAttribute('height', String(height)); bar.setAttribute('rx', '1'); waveform.append(bar);
    }
    function render() {
      const playing = !audio.paused;
      card.classList.toggle('is-playing', playing);
      button.setAttribute('aria-label', `${playing ? 'Pause' : 'Play'} ${song.title}`);
      button.querySelector('path').setAttribute('d', playing ? 'M6 5h4v14H6zm8 0h4v14h-4z' : 'M8 5v14l11-7z');
      button.querySelector('span').textContent = playing ? 'Pause' : 'Play';
      text(card, '[data-position]', time(audio.currentTime || 0));
      seek.value = String(Number.isFinite(audio.duration) ? audio.currentTime / audio.duration * 100 : 0);
      seek.disabled = !Number.isFinite(audio.duration);
    }
    button.addEventListener('click', async () => {
      if (!audio.paused) { audio.pause(); status.textContent = `Paused: ${song.title}`; return; }
      try { await audio.play(); } catch { status.textContent = `Could not play ${song.title}. Try its MP3 download.`; }
    });
    audio.addEventListener('play', () => { for (const item of players) if (item.audio !== audio) item.audio.pause(); status.textContent = `Now playing: ${song.title}`; render(); });
    for (const event of ['pause', 'timeupdate', 'loadedmetadata', 'ended']) audio.addEventListener(event, render);
    audio.addEventListener('ended', () => { status.textContent = `Finished: ${song.title}`; });
    seek.addEventListener('input', () => { if (Number.isFinite(audio.duration)) audio.currentTime = Number(seek.value) / 100 * audio.duration; });
    players.push({audio, card}); render(); grid.append(fragment);
  }
  sound();
  const categories = ['All styles', ...new Set(catalog.songs.map(song => song.category))];
  for (const category of categories) {
    const button = document.createElement('button'); button.type = 'button'; button.textContent = category;
    button.setAttribute('aria-pressed', String(category === 'All styles'));
    button.addEventListener('click', () => {
      for (const sibling of button.parentElement.children) sibling.setAttribute('aria-pressed', String(sibling === button));
      let count = 0;
      for (const {audio, card} of players) { card.hidden = category !== 'All styles' && card.dataset.category !== category; if (card.hidden) audio.pause(); else count++; }
      root.querySelector('[data-count]').textContent = `${count} ${count === 1 ? 'song' : 'songs'} · ${category}`;
      const active = players.find(item => !item.audio.paused);
      status.textContent = active ? `Now playing: ${active.audio.getAttribute('aria-label')}` : 'Choose a song to listen.';
    });
    root.querySelector('.style-filters').append(button);
  }
  root.querySelector('[data-count]').textContent = `${catalog.songs.length} songs · All styles`;
})();
