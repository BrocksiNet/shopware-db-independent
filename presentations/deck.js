(() => {
  'use strict';
  const $ = (s, root = document) => root.querySelector(s);
  const slides = [...document.querySelectorAll('.slide')];
  const stage = $('.stage');
  let index = 0, panel = null, started = Date.now(), returnFocus = null;
  const clamp = n => Math.max(0, Math.min(slides.length - 1, n));
  const fromHash = () => {
    const hash = location.hash.slice(1), n = Number(hash);
    if (Number.isInteger(n) && n > 0) return clamp(n - 1);
    const redirect = JSON.parse(document.body.dataset.redirects || '{}')[hash];
    if (redirect) { location.replace(redirect); return 0; }
    const found = slides.findIndex(slide => slide.dataset.slug === hash || JSON.parse(slide.dataset.aliases || '[]').includes(hash));
    return found >= 0 ? found : 0;
  };
  const titleOf = slide => [...$('h1,h2', slide).childNodes].map(node => node.nodeName === 'BR' ? ' ' : node.textContent).join('').replace(/\s+/g, ' ').trim();
  function resize() {
    const width = window.innerWidth - (panel ? Math.min(370, window.innerWidth * .45) : 0);
    const scale = Math.min(width / 1600, window.innerHeight / 900);
    stage.style.transform = `scale(${scale})`;
    stage.style.left = `${Math.max(0, (width - 1600 * scale) / 2)}px`;
    stage.style.top = `${Math.max(0, (window.innerHeight - 900 * scale) / 2)}px`;
    $('.panel').style.width = `${Math.min(370, window.innerWidth * .45)}px`;
  }
  function focusCode(block, step) {
    const groups = JSON.parse(block.dataset.focus || '[]');
    if (!groups.length) return;
    block.dataset.step = String((step + groups.length + 1) % (groups.length + 1));
    const current = Number(block.dataset.step), group = groups[current - 1];
    block.querySelectorAll('.code-line').forEach(line => {
      const n = Number(line.dataset.line), selected = group?.lines.includes(n);
      line.classList.toggle('focus', !!selected);
      line.classList.toggle('dim', current !== 0 && !selected);
    });
    const control = $('.focus-control', block);
    $('.focus-count', control).textContent = current ? `${current}/${groups.length}` : 'ALL';
    $('.focus-label', control).textContent = group?.label || 'Full snippet · press H to focus';
  }
  function cycleHighlights() {
    slides[index].querySelectorAll('.code[data-focus]').forEach(block => focusCode(block, Number(block.dataset.step || 0) + 1));
  }
  function renderPanel() {
    const slide = slides[index], title = titleOf(slide);
    $('.panel-title').textContent = title;
    const content = $('.panel-content'); content.replaceChildren();
    if (panel === 'notes') {
      content.innerHTML = $('.speaker-notes', slide)?.innerHTML || '<p>No notes for this slide.</p>';
      const next = document.createElement('p');
      next.className = 'next-title'; next.textContent = index + 1 < slides.length ? `Next: ${titleOf(slides[index + 1])}` : 'End of presentation';
      content.append(next);
    } else {
      const sources = JSON.parse(slide.dataset.sources || '[]');
      if (!sources.length) content.innerHTML = '<p>See the reference slide for the source map.</p>';
      sources.forEach(source => {
        const p = document.createElement('p'), a = document.createElement('a');
        a.href = source.url; a.textContent = source.label; a.target = '_blank'; a.rel = 'noopener noreferrer';
        p.append(a); content.append(p);
      });
      const p = document.createElement('p');
      p.textContent = 'Code excerpts use pinned commits. Documentation describes recorded runs. GitHub links may require repository access.';
      content.append(p);
    }
  }
  function show(n, updateHash = true) {
    index = clamp(n);
    slides.forEach((slide, i) => { slide.classList.toggle('active', i === index); slide.setAttribute('aria-hidden', String(i !== index)); slide.inert = i !== index; });
    $('.counter').textContent = `${String(index + 1).padStart(2, '0')} / ${slides.length}`;
    $('.progress').style.width = `${(index + 1) / slides.length * 100}%`;
    $('.prev').disabled = index === 0; $('.next').disabled = index === slides.length - 1;
    document.title = `${index + 1}. ${titleOf(slides[index])} · ${document.body.dataset.title}`;
    $('.announcer').textContent = `Slide ${index + 1} of ${slides.length}: ${titleOf(slides[index])}`;
    if (updateHash) history.replaceState(null, '', `#${index + 1}`);
    if (panel) renderPanel();
    document.querySelectorAll('.overview-card').forEach((card, i) => card.classList.toggle('current', i === index));
  }
  function togglePanel(name) {
    panel = panel === name ? null : name;
    $('.panel').classList.toggle('open', !!panel);
    $('.panel').inert = !panel;
    $('.notes-button').setAttribute('aria-expanded', String(panel === 'notes'));
    $('.sources-button').setAttribute('aria-expanded', String(panel === 'sources'));
    $('.panel-mode').textContent = panel === 'notes' ? 'SPEAKER NOTES' : 'SOURCES';
    if (panel) renderPanel();
    resize();
  }
  function closeOverlay() {
    document.querySelectorAll('.overlay').forEach(x => { x.classList.remove('open'); x.inert = true; });
    stage.inert = false;
    returnFocus?.focus();
  }
  function openOverlay(selector) {
    const overlay = $(selector);
    if (overlay.classList.contains('open')) { closeOverlay(); return; }
    closeOverlay(); returnFocus = document.activeElement;
    overlay.inert = false; overlay.classList.add('open'); overlay.scrollTop = 0; stage.inert = true;
    $('.close', overlay).focus();
  }
  slides.forEach((slide, i) => {
    slide.dataset.print = `${document.body.dataset.title} / ${String(i + 1).padStart(2, '0')}`;
    slide.querySelectorAll('.code[data-focus]').forEach(block => {
      focusCode(block, 1);
      $('.focus-control', block).addEventListener('click', () => focusCode(block, Number(block.dataset.step) + 1));
    });
    const card = document.createElement('button'); card.className = 'overview-card';
    const number = document.createElement('span'); number.textContent = String(i + 1).padStart(2, '0');
    const title = document.createElement('strong'); title.textContent = titleOf(slide);
    card.append(number, title); card.addEventListener('click', () => { show(i); closeOverlay(); });
    $('.overview-grid').append(card);
  });
  $('.prev').addEventListener('click', () => show(index - 1));
  $('.next').addEventListener('click', () => show(index + 1));
  $('.notes-button').addEventListener('click', () => togglePanel('notes'));
  $('.sources-button').addEventListener('click', () => togglePanel('sources'));
  $('.panel .close').addEventListener('click', () => togglePanel(panel));
  $('.overview-button').addEventListener('click', () => openOverlay('.overview'));
  $('.counter').addEventListener('click', () => openOverlay('.overview'));
  document.querySelectorAll('.go-start').forEach(button => button.addEventListener('click', () => { closeOverlay(); show(0); }));
  $('.help-button').addEventListener('click', () => openOverlay('.help'));
  document.querySelectorAll('.overlay .close').forEach(x => x.addEventListener('click', closeOverlay));
  async function fullscreen() { try { if (document.fullscreenElement) await document.exitFullscreen(); else await document.documentElement.requestFullscreen(); } catch { $('.announcer').textContent = 'Fullscreen is unavailable in this browser.'; } }
  $('.fullscreen-button').addEventListener('click', fullscreen);
  $('.reset').addEventListener('click', () => { started = Date.now(); tick(); });
  function tick() { const s = Math.floor((Date.now() - started) / 1000); $('.timer').textContent = `${String(Math.floor(s / 60)).padStart(2,'0')}:${String(s % 60).padStart(2,'0')}`; }
  setInterval(tick, 1000);
  document.addEventListener('keydown', e => {
    if (e.metaKey || e.ctrlKey || e.altKey || /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
    if (e.key === 'Escape') { closeOverlay(); if (panel) togglePanel(panel); return; }
    if (e.key === '1') { e.preventDefault(); closeOverlay(); show(0); return; }
    const overlay = $('.overlay.open');
    if (overlay) {
      if (e.key === 'Tab') {
        const focusable = [...overlay.querySelectorAll('button,a[href]')];
        const first = focusable[0], last = focusable.at(-1);
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
      return;
    }
    if (e.key === ' ' && /BUTTON|A/.test(e.target.tagName)) return;
    const actions = {ArrowRight:()=>show(index+1),PageDown:()=>show(index+1),' ':()=>show(index+1),ArrowLeft:()=>show(index-1),PageUp:()=>show(index-1),Home:()=>show(0),End:()=>show(slides.length-1),h:cycleHighlights,n:()=>togglePanel('notes'),s:()=>togglePanel('sources'),o:()=>openOverlay('.overview'),f:fullscreen,'?':()=>openOverlay('.help')};
    const action = actions[e.key.length === 1 ? e.key.toLowerCase() : e.key];
    if (action) { e.preventDefault(); action(); }
  });
  let touchX = null;
  stage.addEventListener('touchstart', e => { if (!e.target.closest('a,button,pre')) touchX=e.touches[0].clientX; }, {passive:true});
  stage.addEventListener('touchend', e => { if(touchX!==null){const dx=e.changedTouches[0].clientX-touchX;if(Math.abs(dx)>70)show(index+(dx<0?1:-1));touchX=null;} }, {passive:true});
  window.addEventListener('resize', resize);
  window.addEventListener('hashchange', () => show(fromHash(), false));
  document.querySelectorAll('.overlay,.panel').forEach(x => { x.inert = true; });
  show(fromHash(), false); resize(); tick();
})();
