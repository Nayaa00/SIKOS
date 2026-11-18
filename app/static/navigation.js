(() => {
  const sidebar = document.getElementById('workspace-sidebar');
  const stage = document.getElementById('workspace-stage');
  const open = document.getElementById('nav-open');
  const close = document.getElementById('nav-close');
  const backdrop = document.getElementById('nav-backdrop');
  const desktop = matchMedia('(min-width:1024px)');
  let previous;
  function setMenu(visible, restore = true) {
    const modal = visible && !desktop.matches;
    document.body.classList.toggle('nav-is-open', modal);
    backdrop.hidden = !modal; stage.inert = modal; sidebar.inert = !desktop.matches && !modal;
    open.setAttribute('aria-expanded', String(modal));
    if (modal) { previous = document.activeElement; close.focus(); }
    else if (restore && previous) { previous.focus(); previous = null; }
  }
  open.addEventListener('click', () => setMenu(true)); close.addEventListener('click', () => setMenu(false));
  backdrop.addEventListener('click', () => setMenu(false));
  document.addEventListener('keydown', event => {
    if (!document.body.classList.contains('nav-is-open')) return;
    if (event.key === 'Escape') setMenu(false);
    if (event.key === 'Tab') {
      const items = [...sidebar.querySelectorAll('a[href],button')].filter(el => el.getClientRects().length);
      if (event.shiftKey && document.activeElement === items[0]) { event.preventDefault(); items.at(-1).focus(); }
      else if (!event.shiftKey && document.activeElement === items.at(-1)) { event.preventDefault(); items[0].focus(); }
    }
  });
  desktop.addEventListener('change', () => setMenu(false,false)); setMenu(false,false);
})();
