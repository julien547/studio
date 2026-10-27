(function () {
  var f = document.getElementById('f'), err = document.getElementById('err'), go = document.getElementById('go');
  var pw = document.getElementById('pw'), eye = document.getElementById('eye');
  eye.addEventListener('click', function () {
    var show = pw.type === 'password'; pw.type = show ? 'text' : 'password'; eye.textContent = show ? 'Masquer' : 'Afficher';
  });
  function fail(m) { err.textContent = m; err.className = 'err on'; }
  fetch('/api/me.php', { credentials: 'same-origin' }).then(function (r) { if (r.ok) location.replace('/app/'); }).catch(function () {});
  f.addEventListener('submit', function (e) {
    e.preventDefault(); err.className = 'err';
    var login = f.login.value.trim(), pass = pw.value;
    if (!login || !pass) { fail('Renseignez votre identifiant et votre mot de passe.'); return; }
    go.disabled = true; go.textContent = 'Connexion…';
    fetch('/api/login.php', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ login: login, password: pass }) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return { s: r.status, j: j }; }); })
      .then(function (x) {
        if (x.j && x.j.ok) { location.replace('/app/'); return; }
        fail((x.j && x.j.error) || 'Connexion impossible. Réessayez dans un instant.');
        go.disabled = false; go.textContent = 'Se connecter'; pw.value = ''; pw.focus();
      })
      .catch(function () { fail('Connexion impossible. Vérifiez votre réseau.'); go.disabled = false; go.textContent = 'Se connecter'; });
  });
})();
