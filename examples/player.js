/* SPDX-License-Identifier: MIT. Local-only listening gallery, with no runtime dependencies. */
(() => {
  const root = document.querySelector('.song-gallery');
  const catalog = window.YUE2_GALLERY;
  const i18n = window.YUE2_I18N;
  const t = (source, variables) => i18n.msg(source, variables);
  if (!root || !catalog?.songs?.length) {
    root?.querySelector('[data-count]')?.replaceChildren(document.createTextNode(t('Recordings are unavailable. Please try again later.')));
    return;
  }
  const grid = root.querySelector('.song-grid');
  const status = root.querySelector('[data-playing]');
  const volume = root.querySelector('[data-volume]');
  const mute = root.querySelector('[data-mute]');
  const languageFilter = root.querySelector('[data-language]');
  const languageCodes = {English: 'en', Chinese: 'zh', Japanese: 'ja', Spanish: 'es'};
  let styleFilter = 'All styles';
  const players = [];
  let muted = false;
  try { const saved = Number(localStorage.getItem('yue2-gallery-volume') ?? 0.7); volume.value = String(Math.max(0, Math.min(1, Number.isFinite(saved) ? saved : 0.7))); } catch { /* Listening still works without storage. */ }
  const time = value => `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, '0')}`;
  const text = (element, selector, value) => { element.querySelector(selector).textContent = value; };
  function sound() {
    for (const {audio} of players) { audio.volume = Number(volume.value); audio.muted = muted; }
    mute.textContent = t(muted ? 'Muted' : 'Sound on');
    mute.setAttribute('aria-label', t(muted ? 'Unmute audio' : 'Mute audio'));
    mute.setAttribute('aria-pressed', String(muted));
  }
  volume.addEventListener('input', () => { sound(); try { localStorage.setItem('yue2-gallery-volume', volume.value); } catch { /* Optional preference. */ } });
  mute.addEventListener('click', () => { muted = !muted; sound(); });

  for (const [index, song] of catalog.songs.entries()) {
    const fragment = root.querySelector('#song-card-template').content.cloneNode(true);
    const card = fragment.querySelector('.song-card');
    card.dataset.category = song.category;
    card.dataset.language = song.language;
    card.id = song.id;
    text(card, '[data-category]', `${String(index + 1).padStart(2, '0')} / ${t(song.category)} · ${t(song.language)}`);
    text(card, '[data-title]', song.title);
    text(card, '[data-description]', t(song.description));
    text(card, '[data-duration]', time(song.audio.seconds));
    text(card, '[data-length]', time(song.audio.seconds));
    text(card, '[data-style]', song.request.style);
    text(card, '[data-lyrics]', song.request.lyrics || t('No lyrics supplied. Instrumental direction.'));
    card.querySelector('[data-lyrics]').lang = languageCodes[song.language] || 'en';
    const languageStatus = ['Japanese', 'Spanish'].includes(song.language) ? 'Experimental language request' : song.request.lyrics ? 'Listed by upstream' : 'No lyrics supplied';
    const facts = [['Score mode', song.request.cot], ['Steps', song.request.steps], ['LM seed', song.request.lm_seed], ['Noise seed', song.request.seed], ['Audio', 'Ogg Opus · 96 kb/s VBR · 48 kHz stereo'], ['Source', song.master ? 'Generated 24-bit PCM' : 'Original MP3 recording'], ['Language', languageStatus], ['Engine', (song.engine || catalog.engine).version]];
    for (const [key, value] of facts) {
      const dt = document.createElement('dt'), dd = document.createElement('dd');
      dt.dataset.factKey = key; dd.dataset.factValue = String(value);
      dt.textContent = t(key); dd.textContent = t(String(value)); card.querySelector('.recipe-facts').append(dt, dd);
    }
    for (const [selector, asset] of [['[data-opus]', song.audio], ['[data-recipe]', song.recipe], ['[data-replay]', song.replay]]) card.querySelector(selector).href = asset.path;
    card.querySelector('[data-copy]').addEventListener('click', async event => {
      const copyButton = event.currentTarget;
      const request = JSON.stringify({title: song.title, ...song.request}, null, 2);
      const live = root.querySelector('[data-copy-status]');
      try { await navigator.clipboard.writeText(request); copyButton.textContent = t('Copied'); live.textContent = t('{title} request copied.', {title:song.title}); }
      catch { copyButton.textContent = t('Clipboard unavailable'); live.textContent = t('Clipboard unavailable. Download Prompt JSON instead.'); }
    });
    const audio = card.querySelector('audio'), button = card.querySelector('[data-play]'), seek = card.querySelector('[data-seek]');
    const source = document.createElement('source'); source.src = song.audio.path; source.type = song.audio.mime; audio.append(source);
    audio.setAttribute('aria-label', song.title);
    seek.setAttribute('aria-label', t('Seek in {title}', {title:song.title}));
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
      button.setAttribute('aria-label', `${t(playing ? 'Pause' : 'Play')} ${song.title}`);
      button.querySelector('path').setAttribute('d', playing ? 'M6 5h4v14H6zm8 0h4v14h-4z' : 'M8 5v14l11-7z');
      button.querySelector('span').textContent = t(playing ? 'Pause' : 'Play');
      text(card, '[data-position]', time(audio.currentTime || 0));
      seek.value = String(Number.isFinite(audio.duration) ? audio.currentTime / audio.duration * 100 : 0);
      seek.disabled = !Number.isFinite(audio.duration);
    }
    button.addEventListener('click', async () => {
      if (!audio.paused) { audio.pause(); status.textContent = t('Paused: {title}', {title:song.title}); return; }
      try { await audio.play(); } catch { status.textContent = t('Could not play {title}. Try downloading its Opus file.', {title:song.title}); }
    });
    audio.addEventListener('play', () => { for (const item of players) if (item.audio !== audio) item.audio.pause(); status.textContent = t('Now playing: {title}', {title:song.title}); render(); });
    for (const event of ['pause', 'timeupdate', 'loadedmetadata', 'ended']) audio.addEventListener(event, render);
    audio.addEventListener('ended', () => { status.textContent = t('Finished: {title}', {title:song.title}); });
    seek.addEventListener('input', () => { if (Number.isFinite(audio.duration)) audio.currentTime = Number(seek.value) / 100 * audio.duration; });
    players.push({audio, card, song, render, index, seek}); render(); grid.append(fragment);
  }
  sound();
  function filter() {
    let count = 0;
    for (const {audio, card} of players) {
      card.hidden = (styleFilter !== 'All styles' && card.dataset.category !== styleFilter) || (languageFilter.value !== 'All languages' && card.dataset.language !== languageFilter.value);
      if (card.hidden) audio.pause(); else count++;
    }
    root.querySelector('[data-count]').textContent = `${t('{count} songs', {count})} · ${t(styleFilter)}`;
    const active = players.find(item => !item.audio.paused);
    status.textContent = active ? t('Now playing: {title}', {title:active.song.title}) : t('Choose a song to listen.');
  }
  for (const language of ['All languages', ...new Set(catalog.songs.map(song => song.language))]) {
    const option = document.createElement('option'); option.value = language; option.textContent = t(language) + (['Japanese','Spanish'].includes(language) ? ' · '+t('experimental') : ''); languageFilter.append(option);
  }
  languageFilter.addEventListener('change', filter);
  const categories = ['All styles', ...new Set(catalog.songs.map(song => song.category))];
  for (const category of categories) {
    const button = document.createElement('button'); button.type = 'button'; button.textContent = t(category); button.dataset.style = category;
    button.setAttribute('aria-pressed', String(category === 'All styles'));
    button.addEventListener('click', () => {
      for (const sibling of button.parentElement.children) sibling.setAttribute('aria-pressed', String(sibling === button));
      styleFilter = category; filter();
    });
    root.querySelector('.style-filters').append(button);
  }
  function localize() {
    i18n.setLocale(i18n.locale(),false);
    root.lang = i18n.locale();
    // Original song data is intentionally preserved; the gallery interface is translated.
    const notice=document.querySelector('#translation-notice');
    if(notice)notice.hidden=true;
    for (const element of document.querySelectorAll('[data-gallery-text]')) element.textContent = t(element.dataset.galleryText);
    for (const element of document.querySelectorAll('[data-gallery-aria]')) element.setAttribute('aria-label', t(element.dataset.galleryAria));
    for (const button of root.querySelectorAll('[data-style]')) if (button.dataset.style) button.textContent = t(button.dataset.style);
    for (const option of languageFilter.options) option.textContent = t(option.value) + (['Japanese','Spanish'].includes(option.value) ? ' · '+t('experimental') : '');
    for (const {card,song,index,render,seek} of players) {
      text(card,'[data-category]',`${String(index+1).padStart(2,'0')} / ${t(song.category)} · ${t(song.language)}`);
      text(card,'[data-description]',t(song.description));
      if (!song.request.lyrics) text(card,'[data-lyrics]',t('No lyrics supplied. Instrumental direction.'));
      for (const dt of card.querySelectorAll('[data-fact-key]')) dt.textContent=t(dt.dataset.factKey);
      for (const dd of card.querySelectorAll('[data-fact-value]')) dd.textContent=t(dd.dataset.factValue);
      seek.setAttribute('aria-label',t('Seek in {title}',{title:song.title}));
      render();
    }
    const cta=root.querySelector('.gallery-cta');
    cta.href='../README'+(i18n.locale()==='en'?'':'.'+i18n.locale())+'.md#quick-start';
    sound(); filter();
  }
  const uiLanguage=root.querySelector('[data-ui-language]');
  for (const [code,name] of Object.entries(i18n.languages)) uiLanguage.append(new Option(name,code));
  uiLanguage.value=i18n.locale();
  root.querySelector('[data-locale-picker]').hidden=!!document.querySelector('#site-language');
  uiLanguage.addEventListener('change',()=>{i18n.setLocale(uiLanguage.value);localize();});
  document.addEventListener('hangry:language',event=>{i18n.setLocale(event.detail.language,false);uiLanguage.value=i18n.locale();localize();});
  localize();
})();
