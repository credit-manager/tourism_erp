/*
 * animations.js — تأثيرات دخول وانتقال موحدة لكل صفحات Tourism ERP
 * يُستدعى من base.html فيتم تطبيقه تلقائيًا على كل الصفحات.
 * الصفحات ممكن تستدعيه صراحةً عبر  ERPAnimations.init()  أو  ERPAnimations.animate(el)
 */
(function (global) {
  'use strict';

  var REDUCED = global.matchMedia &&
    global.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // عناصر تشبه البطاقات/اللوحات بشكل عام
  var CARD_SEL = [
    '.erp-card', '.kpi-card', '.stat-card', '.info-card', '.panel', 'table.card',
    '.main-card', '.side-card', '.alert-card', '.allocation-card',
    '.supplier-card', '.expense-card', '.treasury-card', '.hotel-card',
    '.collection-card', '.report-card', '.account-card', '.hotel-detail-card',
    '.supplier-kpi', '.expense-kpi', '.cards-grid',
    '.add-hotel-panel', '.edit-panel', '.detail-form-panel', '.allocate-panel',
    '.filter-card', '.report-card'
  ].join(',');

  var GRID_SEL = ['.kpi-grid', '.suppliers-kpis', '.expenses-kpis',
    '.reports-grid', '.accounts-grid', '.customers-stats', '.form-grid',
    '.detail-form-grid', '.hotel-form-grid'].join(',');

  var TABLE_WRAP_SEL = ['.table-wrap', '.customers-table', '.suppliers-table',
    '.expenses-table', '.treasury-table', '.collections-table', '.hotel-detail-card table',
    '.report-table', '.detail-table-wrap'].join(',');

  function tag(el, cls, delay) {
    if (!el || el.dataset.erpDone) return;
    el.dataset.erpDone = '1';
    el.classList.add(cls);
    if (delay != null) el.style.animationDelay = delay + 's';
  }

  function applyEntrance(root) {
    root = root || document.querySelector('.content-wrap');
    if (!root) return;

    // العنوان الرئيسي
    var title = root.querySelector('h1, .page-title-row');
    tag(title, 'erp-animate');

    // كل العناصر الفرعية المباشرة (بلوكات الصفحة) — تأثير تدريجي مضمون
    var kids = root.children;
    Array.prototype.forEach.call(kids, function (el, i) {
      if (el.dataset.erpDone) return;
      tag(el, i % 2 === 0 ? 'erp-animate' : 'erp-animate-pop', 0.05 + i * 0.05);
    });

    // البطاقات/اللوحات بداخل المحتوى
    root.querySelectorAll(CARD_SEL).forEach(function (el, i) {
      tag(el, i % 2 === 0 ? 'erp-animate' : 'erp-animate-pop', 0.06 + i * 0.04);
    });

    // الشبكات (KPI / grids)
    root.querySelectorAll(GRID_SEL).forEach(function (el) {
      tag(el, 'erp-animate-fade', 0.1);
    });

    // الجداول (مغلفة أو مجردة)
    root.querySelectorAll(TABLE_WRAP_SEL + ', table:not(.card)').forEach(function (el) {
      if (el.closest('.erp-animate, .erp-animate-pop, .erp-card, .main-card, .supplier-card, .expense-card, .treasury-card, .hotel-card, .collection-card, .report-card, .account-card')) return;
      tag(el, 'erp-animate-fade', 0.12);
    });
  }

  function boot() {
    if (REDUCED) return;
    applyEntrance();

    var content = document.querySelector('.content-wrap');
    if (content && typeof MutationObserver !== 'undefined') {
      var mo = new MutationObserver(function (mutations) {
        var changed = false;
        mutations.forEach(function (m) {
          m.addedNodes.forEach(function (n) {
            if (n.nodeType === 1 &&
              ((n.matches && n.matches(CARD_SEL + ',' + GRID_SEL + ',' + TABLE_WRAP_SEL + ',table')) ||
               (n.querySelector && n.querySelector(CARD_SEL + ',' + GRID_SEL + ',table')))) {
              changed = true;
            }
          });
        });
        if (changed) applyEntrance(content);
      });
      mo.observe(content, { childList: true, subtree: true });
    }
  }

  // الواجهة العامة للاستخدام الصريح داخل أي صفحة
  global.ERPAnimations = {
    init: function () { if (!REDUCED) applyEntrance(); },
    animate: function (el) { if (!REDUCED && el) applyEntrance(el); }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})(window);
