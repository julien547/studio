'use strict';
(() => {
  const byId = id => document.getElementById(id);
  let project = null, loadedVersion = null, user = '', dirty = false, remoteReadyUntil = 0, busy = false;
  let readinessTimer = null;
  const message = text => { byId('status').textContent = text; };
  async function api(route, body, multipart = false) {
    const response = await fetch('/api/redessin.php?route=' + encodeURIComponent(route), {
      credentials: 'same-origin', method: body === undefined ? 'GET' : 'POST',
      headers: body === undefined || multipart ? {} : {'Content-Type': 'application/json'},
      body: body === undefined ? undefined : multipart ? body : JSON.stringify(body),
    });
    const result = await response.json();
    if (response.status === 401) { location.assign('/'); throw Error('Session expirée'); }
    if (!response.ok) throw Error(typeof result.detail === 'string' ? result.detail : result.error || 'Demande refusée');
    return result;
  }
  function controls() {
    byId('ai').disabled = !project || busy || Date.now() >= remoteReadyUntil;
    byId('checkAi').disabled = busy;
    byId('saveServer').disabled = !project || busy;
    byId('serverSvg').disabled = !project || busy || dirty;
    byId('import').disabled = busy; byId('open').disabled = busy;
  }
  async function checkConnection() {
    clearTimeout(readinessTimer);
    remoteReadyUntil = 0; controls();
    byId('aiStatus').textContent = 'Vérification du service RunPod…';
    byId('engineStatus').replaceChildren();
    try {
      const status = await api('/runpod/status');
      const labels = {
        not_configured: 'IA non raccordées : configuration OVH–RunPod à terminer.',
        unavailable: 'Service RunPod injoignable. Faire vérifier le transport privé.',
        authentication_failed: 'Authentification RunPod refusée. Faire vérifier les clés de service et les horloges.',
        key_unavailable: 'La clé de signature OVH est inaccessible au service.',
        invalid_configuration_or_contract: 'La configuration ou la réponse RunPod ne correspond pas au service attendu.',
        starting: 'RunPod répond ; les tests de démarrage des trois moteurs ne sont pas tous confirmés.',
        not_ready: 'RunPod répond mais demande une intervention avant toute analyse.',
        busy: 'RunPod répond mais ne peut pas accepter une nouvelle analyse pour le moment.',
        ready: 'Connexion aux trois IA disponible. Vous pouvez analyser cette page ; les résultats resteront à contrôler.',
      };
      byId('aiStatus').textContent = labels[status.state] || 'État RunPod non reconnu.';
      const names = {qwen: 'Qwen — lecture des zones', paddleocr: 'PaddleOCR — textes', rtmdet: 'RTMDet — diagnostic d’objets'};
      for (const engine of status.engines || []) {
        const item = document.createElement('li');
        item.textContent = (names[engine.id] || engine.id) + ' : ' + (engine.startup_inference_verified ? 'test de démarrage réussi' : 'test de démarrage non confirmé');
        byId('engineStatus').append(item);
      }
      if (status.state === 'ready' && status.can_analyze === true) {
        remoteReadyUntil = Date.now() + 60000;
        readinessTimer = setTimeout(() => {
          if (Date.now() >= remoteReadyUntil) {
            controls();
            byId('aiStatus').textContent = 'Vérifiez de nouveau la disponibilité RunPod avant une nouvelle analyse.';
          }
        }, 60100);
      }
      return status.state === 'ready' && status.can_analyze === true;
    } catch (error) {
      byId('aiStatus').textContent = 'Vérification RunPod impossible. Réessayez ou faites contrôler le service.';
      throw error;
    } finally { controls(); }
  }
  function edited() { dirty = true; controls(); }
  async function listing(selected) {
    const projects = await api('/projects'); byId('projects').replaceChildren();
    for (const item of projects) {
      const option = document.createElement('option'); option.value = item.id;
      option.textContent = item.name + ' · page ' + item.page + (item.available ? '' : ' · en attente');
      byId('projects').append(option);
    }
    if (selected) byId('projects').value = selected;
  }
  async function open(id) {
    const data = await api('/projects/' + id);
    if (!data.document) throw Error('Extraction non terminée. Réessayez après le traitement.');
    project = id; loadedVersion = data.version;
    const option = [...byId('projects').options].find(item => item.value === id);
    if (option) option.textContent = data.name + ' · page ' + data.page;
    await window.doemoEditor.mount(byId('editorHost'), data.document, user, edited);
    byId('editorHost').hidden = false; dirty = false; controls();
    const records = Object.values(data.document.levels[0].ai_evidence || {});
    byId('evidenceDetails').hidden = !records.length;
    byId('evidenceSummary').hidden = !records.length;
    byId('evidence').textContent = records.length ? JSON.stringify(records.at(-1), null, 2) : '';
    if (records.length) {
      const evidence = records.at(-1);
      byId('evidenceSummary').textContent = `Dernière analyse : ${evidence.texts.length} texte(s) OCR, ${evidence.zones.length} zone(s) commentée(s), ${evidence.rtmdet_diagnostic_count ?? 0} objet(s) RTMDet de diagnostic. Ces résultats ne valident aucun mur.`;
    }
    message('Projet chargé. Enregistrez sur OVH après vos corrections.');
  }
  async function poll(id) {
    for (;;) {
      const task = await api('/tasks/' + id);
      if (task.status === 'completed') return task;
      if (['failed','interrupted'].includes(task.status)) throw Error(task.error || 'Traitement interrompu.');
      message(task.status === 'queued' ? 'Traitement en attente…' : 'Traitement en cours…');
      await new Promise(resolve => setTimeout(resolve, 1500));
    }
  }
  async function action(callback) {
    busy = true; controls(); window.doemoEditor.lock(true);
    try { await callback(); } catch (error) { message(error.message); }
    finally { busy = false; controls(); window.doemoEditor.lock(false); }
  }
  async function save() {
    const result = await api('/projects/' + project + '/save', {
      expected_version: loadedVersion, document: window.doemoEditor.document(),
    });
    loadedVersion = result.version;
    window.doemoEditor.replace(result.document); dirty = false; controls();
    message('Corrections enregistrées sur OVH.');
  }
  byId('upload').addEventListener('submit', event => {
    event.preventDefault();
    if (dirty && !confirm('Les corrections non enregistrées seront perdues. Continuer ?')) return;
    action(async () => {
      if (byId('plan').files[0].size > 20 * 1024 * 1024) throw Error('Fichier supérieur à 20 Mio.');
      const job = await api('/projects', new FormData(byId('upload')), true);
      await listing(job.id); await poll(job.task_id); await open(job.id);
    });
  });
  byId('open').onclick = () => {
    if (!byId('projects').value || (dirty && !confirm('Abandonner les corrections non enregistrées ?'))) return;
    action(() => open(byId('projects').value));
  };
  byId('saveServer').onclick = () => action(save);
  byId('checkAi').onclick = () => action(checkConnection);
  byId('ai').onclick = () => action(async () => {
    if (!await checkConnection()) throw Error('Les trois moteurs RunPod doivent être disponibles avant le test.');
    await save();
    window.doemoEditor.lock(true);
    try {
      const task = await api('/projects/' + project + '/analyze', {});
      await poll(task.task_id); await open(project);
      message('Réponses IA reçues. Les observations restent à contrôler ; aucun mur n’a été validé automatiquement.');
    } finally { window.doemoEditor.lock(false); }
  });
  byId('serverSvg').onclick = () => action(async () => {
    const result = await api('/projects/' + project + '/export/svg');
    const url = URL.createObjectURL(new Blob([result.content], {type: 'image/svg+xml'}));
    const a = document.createElement('a'); a.href = url; a.download = 'murs-valides.svg'; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
  api('/health').then(async health => {
    user = health.user;
    byId('aiStatus').textContent = 'IA non raccordées : configuration OVH–RunPod à terminer. Import et correction locale disponibles.';
    await listing(); controls(); message('Prêt à importer une page.');
    if (health.runpod_configured) await action(checkConnection);
  }).catch(error => message(error.message));
})();
