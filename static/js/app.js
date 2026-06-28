(function () {
  function parseNumber(value) {
    const num = Number(value);
    return Number.isFinite(num) ? num : 0;
  }

  function initLitreSwitchers(scope) {
    (scope || document).querySelectorAll('.litre-switcher').forEach(function (group) {
      const unit = group.querySelector('.litre-unit');
      const targetId = group.dataset.target;
      const input = targetId ? document.getElementById(targetId) : group.querySelector('input[name$="litre"]');
      if (!unit || !input) return;

      const initial = group.dataset.initialUnit || 'litre';
      unit.value = initial;

      function applyUnit() {
        if (unit.value === 'ml') {
          input.value = '500';
          input.readOnly = true;
          input.step = '1';
        } else {
          if (input.readOnly && input.value === '500') {
            input.value = '1.00';
          }
          input.readOnly = false;
          input.step = '0.01';
        }
      }

      unit.addEventListener('change', applyUnit);

      const form = group.closest('form');
      if (form && !form.dataset.litreUnitHooked) {
        form.addEventListener('submit', function () {
          form.querySelectorAll('.litre-switcher').forEach(function (innerGroup) {
            const innerUnit = innerGroup.querySelector('.litre-unit');
            const innerTargetId = innerGroup.dataset.target;
            const innerInput = innerTargetId
              ? document.getElementById(innerTargetId)
              : innerGroup.querySelector('input[name$="litre"]');
            if (!innerUnit || !innerInput) return;
            if (innerUnit.value === 'ml') {
              innerInput.value = '0.50';
            }
          });
        });
        form.dataset.litreUnitHooked = '1';
      }

      applyUnit();
    });
  }

  const swipeArea = document.getElementById('swipe-area');
  if (swipeArea) {
    let startX = null;
    swipeArea.addEventListener('touchstart', function (e) {
      startX = e.touches[0].clientX;
    });
    swipeArea.addEventListener('touchend', function (e) {
      if (startX === null) return;
      const endX = e.changedTouches[0].clientX;
      const diff = endX - startX;
      if (Math.abs(diff) > 60) {
        if (diff < 0 && swipeArea.dataset.nextUrl) {
          window.location.href = swipeArea.dataset.nextUrl;
        }
        if (diff > 0 && swipeArea.dataset.prevUrl) {
          window.location.href = swipeArea.dataset.prevUrl;
        }
      }
      startX = null;
    });
  }

  initLitreSwitchers(document);

  let deferredPrompt;
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
  });

  window.installApp = function() {
    if (deferredPrompt) {
      deferredPrompt.prompt();
      deferredPrompt.userChoice.then((choiceResult) => {
        if (choiceResult.outcome === 'accepted') {
          console.log('App installed');
        }
        deferredPrompt = null;
      });
    }
  };

  const dayModalEl = document.getElementById('dayModal');
  if (dayModalEl) {
    const payloadEl = document.getElementById('entryPayload');
    const payload = payloadEl ? JSON.parse(payloadEl.textContent || '{}') : {};

    document.querySelectorAll('.day-cell[data-date]').forEach(function (button) {
      button.addEventListener('click', function () {
        const date = button.dataset.date;
        const info = payload[date] || {
          morning_litre: button.dataset.defaultMorning || '0',
          morning_status: 'delivered',
          evening_litre: button.dataset.defaultEvening || '0',
          evening_status: 'delivered',
          amount: '0',
          total_litre: '0',
        };

        document.getElementById('modalDate').value = date;
        document.getElementById('modalDateLabel').innerText = date;
        document.getElementById('id_morning_litre').value = info.morning_litre;
        document.getElementById('id_evening_litre').value = info.evening_litre;
        document.getElementById('id_morning_status').value = info.morning_status;
        document.getElementById('id_evening_status').value = info.evening_status;
        document.getElementById('modalTotal').innerText = info.total_litre + ' L';
        document.getElementById('modalAmount').innerText = 'Rs ' + info.amount;

        const morningUnit = document.getElementById('id_morning_unit');
        const eveningUnit = document.getElementById('id_evening_unit');
        if (morningUnit) {
          morningUnit.value = Math.abs(parseNumber(info.morning_litre) - 0.5) < 0.0001 ? 'ml' : 'litre';
          morningUnit.dispatchEvent(new Event('change'));
        }
        if (eveningUnit) {
          eveningUnit.value = Math.abs(parseNumber(info.evening_litre) - 0.5) < 0.0001 ? 'ml' : 'litre';
          eveningUnit.dispatchEvent(new Event('change'));
        }

        dayModalEl.classList.remove('hidden');
        dayModalEl.classList.add('flex');
      });
    });

    dayModalEl.querySelectorAll('[data-close-modal]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        dayModalEl.classList.add('hidden');
        dayModalEl.classList.remove('flex');
      });
    });

    dayModalEl.addEventListener('click', function (e) {
      if (e.target === dayModalEl) {
        dayModalEl.classList.add('hidden');
        dayModalEl.classList.remove('flex');
      }
    });
  }

  const sexField = document.getElementById('id_sex');
  if (sexField) {
    const pregWrap = document.getElementById('pregnancy-wrap');
    const milkWrap = document.getElementById('milk-wrap');

    function toggleFemaleFields() {
      const female = sexField.value === 'female';
      if (pregWrap) pregWrap.style.display = female ? '' : 'none';
      if (milkWrap) milkWrap.style.display = female ? '' : 'none';
    }

    sexField.addEventListener('change', toggleFemaleFields);
    toggleFemaleFields();
  }
})();
