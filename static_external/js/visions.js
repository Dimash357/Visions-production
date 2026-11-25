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
      if (event.defaultPrevented) return;  // отменено, например, в confirm()
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

  // «Выбрать всех» для списков чекбоксов
  document.querySelectorAll('[data-check-all]').forEach(function (master) {
    var name = master.dataset.checkAll;
    var form = master.closest('form');
    var boxes = function () { return form.querySelectorAll('input[type="checkbox"][name="' + name + '"]'); };
    var sync = function () {
      var all = boxes(), on = 0;
      all.forEach(function (b) { if (b.checked) on++; });
      master.checked = all.length > 0 && on === all.length;
      master.indeterminate = on > 0 && on < all.length;
    };
    master.addEventListener('change', function () { boxes().forEach(function (b) { b.checked = master.checked; }); });
    boxes().forEach(function (b) { b.addEventListener('change', sync); });
    sync();
  });

  // Живой предпросмотр карточки задания
  var pvForm = document.querySelector('form[data-preview]');
  if (pvForm) {
    var field = function (n) { return pvForm.querySelector('[name="' + n + '"]'); };
    var out = function (n) { return document.querySelector('[data-pv="' + n + '"]'); };
    var render = function () {
      var title = field('title'), desc = field('description'), dl = field('deadline');
      if (title && out('title')) out('title').textContent = title.value.trim() || 'Название задания';
      if (desc && out('description')) { out('description').textContent = desc.value; out('description').hidden = !desc.value.trim(); }
      if (dl && out('deadline')) {
        var p = (dl.value || '').split('-');
        out('deadline').textContent = p.length === 3 ? p[2] + '.' + p[1] + '.' + p[0] : '—';
      }
    };
    pvForm.addEventListener('input', render);
    render();
  }
})();
