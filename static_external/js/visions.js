(function () {
  'use strict';

  // Mobile navigation toggle
  var toggle = document.querySelector('[data-menu-toggle]');
  var nav = document.getElementById('site-nav');
  if (toggle && nav) {
    toggle.addEventListener('click', function () {
      var open = nav.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  // Prevent double submission of uploads (server sends an e-mail, which can be slow)
  document.querySelectorAll('form[data-once]').forEach(function (form) {
    form.addEventListener('submit', function (event) {
      if (form.dataset.busy) { event.preventDefault(); return; }
      form.dataset.busy = '1';
      var btn = event.submitter || form.querySelector('[type="submit"]');
      // Отключаем кнопки после того, как браузер собрал данные формы (иначе name/value кнопки потеряются)
      setTimeout(function () {
        form.querySelectorAll('[type="submit"]').forEach(function (b) { b.disabled = true; });
        if (btn && btn.dataset.busyLabel) btn.textContent = btn.dataset.busyLabel;
      }, 0);
    });
  });

  // Enable upload button only after a file is chosen
  document.querySelectorAll('input[type="file"][data-enables]').forEach(function (input) {
    var btn = document.getElementById(input.dataset.enables);
    if (!btn) return;
    var sync = function () { btn.disabled = !input.files || input.files.length === 0; };
    input.addEventListener('change', sync);
    sync();
  });
})();
