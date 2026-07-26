(function () {
  'use strict';

  function animateCounters() {
    document.querySelectorAll('.kpi-counter:not(.animated)').forEach(function (el) {
      var target = parseFloat(el.getAttribute('data-target'));
      if (isNaN(target)) return;
      el.classList.add('animated');
      var duration = 1200;
      var step = target / (duration / 16);
      var current = 0;
      function update() {
        current += step;
        if (current >= target) {
          el.textContent = target.toLocaleString();
          return;
        }
        el.textContent = Math.floor(current).toLocaleString();
        requestAnimationFrame(update);
      }
      update();
    });
  }

  function fadeInElements() {
    document.querySelectorAll('.fade-in:not(.fade-visible)').forEach(function (el) {
      el.classList.add('fade-visible');
      el.style.opacity = '1';
      el.style.transform = 'translateY(0)';
    });
  }

  if ('IntersectionObserver' in window) {
    var counterObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.dataset._observed = '1';
        }
      });
    }, { threshold: 0.3 });

    document.querySelectorAll('.kpi-counter').forEach(function (el) {
      counterObserver.observe(el);
    });

    var animObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('fade-visible');
          entry.target.style.opacity = '1';
          entry.target.style.transform = 'translateY(0)';
          animObserver.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1 });

    document.querySelectorAll('.fade-in').forEach(function (el) {
      el.style.opacity = '0';
      el.style.transform = 'translateY(18px)';
      el.style.transition = 'opacity 0.45s ease, transform 0.45s ease';
      animObserver.observe(el);
    });

    var counterCheck = setInterval(function () {
      var allCounters = document.querySelectorAll('.kpi-counter[data-_observed="1"]');
      var anyVisible = false;
      allCounters.forEach(function (el) {
        if (el.dataset._observed === '1' && !el.classList.contains('animated')) {
          anyVisible = true;
        }
      });
      if (anyVisible) {
        animateCounters();
      }
    }, 200);
  } else {
    fadeInElements();
    animateCounters();
  }

  document.addEventListener('DOMContentLoaded', function () {
    var rows = document.querySelectorAll('.hover-lift');
    rows.forEach(function (el) {
      el.addEventListener('mouseenter', function () {
        el.style.transform = 'translateY(-2px)';
        el.style.boxShadow = '0 10px 22px rgba(15, 23, 42, 0.045)';
      });
      el.addEventListener('mouseleave', function () {
        el.style.transform = 'translateY(0)';
        el.style.boxShadow = 'none';
      });
    });
  });
})();
