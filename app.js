(function () {
  fetch('/api/me.php', { credentials: 'same-origin' }).then(function (r) {
    if (!r.ok) { location.replace('/'); return null; } return r.json();
  }).then(function (j) { if (j) document.getElementById('who').textContent = j.login; }).catch(function () { location.replace('/'); });
  document.getElementById('out').addEventListener('click', function () {
    fetch('/api/logout.php', { method: 'POST', credentials: 'same-origin' }).finally(function () { location.replace('/'); });
  });
})();
