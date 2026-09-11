(() => {
  'use strict';
  const menu = document.querySelector('.menu-toggle'), nav = document.querySelector('#site-nav');
  const close = () => { nav?.classList.remove('is-open'); menu?.setAttribute('aria-expanded','false'); menu?.setAttribute('aria-label','Open navigation'); };
  menu?.addEventListener('click', () => { const open = menu.getAttribute('aria-expanded') !== 'true'; nav.classList.toggle('is-open',open); menu.setAttribute('aria-expanded',String(open)); menu.setAttribute('aria-label',open ? 'Close navigation' : 'Open navigation'); });
  nav?.querySelectorAll('a').forEach(link => link.addEventListener('click',close));
  document.addEventListener('keydown', event => { if(event.key === 'Escape' && menu?.getAttribute('aria-expanded') === 'true') { close(); menu.focus(); } });
  document.addEventListener('click',event => { if (!event.target.closest('.site-header')) close(); });
  if ('IntersectionObserver' in window && nav) {
    const observer = new IntersectionObserver(entries => { for(const entry of entries) { if(!entry.isIntersecting) continue; nav.querySelectorAll('a').forEach(link => { if(link.hash === '#' + entry.target.id) link.setAttribute('aria-current','location'); else link.removeAttribute('aria-current'); }); } },{rootMargin:'-15% 0px -55% 0px',threshold:0});
    document.querySelectorAll('main > section[id]').forEach(section => observer.observe(section));
  }
  document.querySelectorAll('[data-year]').forEach(element => { element.textContent = new Date().getFullYear(); });
})();
