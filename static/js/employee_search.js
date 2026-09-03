/*
employee_search.js
A lightweight, dependency-free "type to search, click to select" widget
for choosing an employee — used anywhere a plain <select> dropdown would
be unusable with a large roster (Overtime, Absences: both the "Employee"
and "Covered By" fields).

Usage: wrap a text input + hidden input + results container in an
element with [data-employee-search], and set data-employees to a JSON
array of {id, label} pairs (e.g. via Jinja's |tojson filter). See
overtime.html / absences.html for the exact markup.
*/

function initEmployeeSearch(root) {
  const input = root.querySelector('[data-role="emp-search-input"]');
  const hidden = root.querySelector('[data-role="emp-search-value"]');
  const results = root.querySelector('[data-role="emp-search-results"]');
  if (!input || !hidden || !results) return;

  let employees = [];
  try {
    employees = JSON.parse(root.dataset.employees || '[]');
  } catch (e) {
    employees = [];
  }
  const allowEmpty = root.dataset.allowEmpty === 'true';
  const emptyLabel = root.dataset.emptyLabel || '— none —';
  const MAX_RESULTS = 50;

  // If editing/re-showing a form with a pre-selected value, the initial
  // input text is already set server-side; nothing else to do here.

  function renderList(list) {
    results.innerHTML = '';
    let shown = 0;

    if (allowEmpty) {
      const item = document.createElement('div');
      item.className = 'emp-search-item emp-search-item-empty';
      item.textContent = emptyLabel;
      item.addEventListener('mousedown', function (e) {
        e.preventDefault();
        hidden.value = '';
        input.value = '';
        closeList();
      });
      results.appendChild(item);
      shown++;
    }

    list.slice(0, MAX_RESULTS).forEach(function (emp) {
      const item = document.createElement('div');
      item.className = 'emp-search-item';
      item.textContent = emp.label;
      item.addEventListener('mousedown', function (e) {
        e.preventDefault();
        hidden.value = emp.id;
        input.value = emp.label;
        closeList();
      });
      results.appendChild(item);
      shown++;
    });

    if (list.length > MAX_RESULTS) {
      const more = document.createElement('div');
      more.className = 'emp-search-item emp-search-item-more';
      more.textContent = 'Keep typing to narrow down (' + list.length + ' matches)…';
      results.appendChild(more);
    }

    if (shown === 0 && !allowEmpty) {
      const none = document.createElement('div');
      none.className = 'emp-search-item emp-search-item-empty';
      none.textContent = 'No matching employees';
      results.appendChild(none);
    }

    results.classList.add('open');
  }

  function closeList() {
    results.classList.remove('open');
  }

  function filtered() {
    const q = input.value.trim().toLowerCase();
    if (!q) return employees;
    return employees.filter(function (emp) {
      return emp.label.toLowerCase().indexOf(q) !== -1;
    });
  }

  input.addEventListener('focus', function () {
    renderList(filtered());
  });

  input.addEventListener('input', function () {
    hidden.value = '';
    renderList(filtered());
  });

  input.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeList();
  });

  document.addEventListener('click', function (e) {
    if (!root.contains(e.target)) closeList();
  });

  // Guard against submitting free-typed text that was never actually
  // matched/selected — the hidden field (what the server reads) would
  // be blank, so block submission and prompt the user to pick a match.
  const form = input.closest('form');
  if (form && !form.dataset.empSearchGuarded) {
    form.dataset.empSearchGuarded = 'true';
    form.addEventListener('submit', function (e) {
      const searchRoots = form.querySelectorAll('[data-employee-search]');
      for (const r of searchRoots) {
        const i = r.querySelector('[data-role="emp-search-input"]');
        const h = r.querySelector('[data-role="emp-search-value"]');
        const needsSelection = i && i.hasAttribute('required');
        if (needsSelection && i.value.trim() !== '' && h.value === '') {
          e.preventDefault();
          i.setCustomValidity('Please pick an employee from the list.');
          i.reportValidity();
          i.focus();
          return;
        }
        if (i) i.setCustomValidity('');
      }
    });
  }
  input.addEventListener('input', function () {
    input.setCustomValidity('');
  });
}

function initTableSearch(root) {
  const input = root.querySelector('[data-table-search]');
  if (!input) return;

  const selector = input.dataset.tableSearchFor || 'table';
  const table = root.querySelector(selector);
  if (!table) return;

  const rows = () => Array.from(table.querySelectorAll('tbody tr'));

  function applyFilter() {
    const q = (input.value || '').trim().toLowerCase();
    rows().forEach(function (row) {
      const text = (row.textContent || '').toLowerCase();
      row.style.display = (!q || text.indexOf(q) !== -1) ? '' : 'none';
    });
  }

  input.addEventListener('input', applyFilter);
  applyFilter();
}

document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('[data-employee-search]').forEach(initEmployeeSearch);
  document.querySelectorAll('[data-table-search-root]').forEach(initTableSearch);
});
