(() => {
  'use strict';
  const logo = document.querySelector('.brand-logo');
  if (!logo) return;
  const brand = logo.closest('a');
  const motion = document.querySelector('.system-motion');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let visible = false, busy = false, idleTimer = 0, endTimer = 0, firstAppearance = true;

  const enabled = () => visible && !document.hidden && !reduced.matches && motion?.dataset.paused !== 'true';

  function stop() {
    clearTimeout(idleTimer);
    clearTimeout(endTimer);
    idleTimer = endTimer = 0;
    busy = false;
    logo.classList.remove('is-playing');
  }

  function schedule(delay = 6500) {
    clearTimeout(idleTimer);
    idleTimer = 0;
    if (enabled()) idleTimer = setTimeout(play, delay);
  }

  function play() {
    if (!enabled() || busy) return;
    stop();
    // Restart the bounded sequence after a previous run has returned to rest.
    void logo.offsetWidth;
    busy = true;
    logo.classList.add('is-playing');
    endTimer = setTimeout(() => {
      endTimer = 0;
      busy = false;
      logo.classList.remove('is-playing');
      schedule();
    }, 1800);
  }

  function sync() {
    if (!enabled()) stop();
    else if (!busy && !idleTimer) {
      schedule(firstAppearance ? 800 : 6500);
      firstAppearance = false;
    }
  }

  brand.addEventListener('pointerenter', event => {
    if (event.pointerType !== 'touch') play();
  });
  brand.addEventListener('focus', play);
  document.addEventListener('visibilitychange', sync);
  reduced.addEventListener('change', sync);
  if (motion) new MutationObserver(sync).observe(motion, {attributes: true, attributeFilter: ['data-paused']});
  new IntersectionObserver(entries => {
    visible = entries[0].isIntersecting && entries[0].intersectionRatio >= .99;
    sync();
  }, {threshold: [0, 1]}).observe(logo);
})();
