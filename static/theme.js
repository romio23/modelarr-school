// Lichte/donkere weergave: keuze (light | dark | auto) staat in localStorage 'theme'; standaard donker.
(function () {
  var K = 'theme', mq = window.matchMedia && matchMedia('(prefers-color-scheme: light)');
  function pref() { try { return localStorage.getItem(K) || 'dark'; } catch (e) { return 'dark'; } }
  function eff(p) { return p === 'auto' ? (mq && mq.matches ? 'light' : 'dark') : (p === 'light' ? 'light' : 'dark'); }
  function apply() { document.documentElement.dataset.theme = eff(pref()); }
  window.THEME = {
    get: pref, eff: function () { return eff(pref()); },
    set: function (p) { try { localStorage.setItem(K, p); } catch (e) { /* geen opslag: alleen voor deze pagina */ } apply(); }
  };
  apply();
  if (mq && mq.addEventListener) mq.addEventListener('change', function () { if (pref() === 'auto') apply(); });
})();
