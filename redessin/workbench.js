'use strict';
(() => {
  const byId = id => document.getElementById(id);
  let project = null, loadedVersion = null, user = '', dirty = false, remoteConfigured = false, busy = false;
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
    byId('ai').disabled = !project || busy || !remoteConfigured;
    byId('saveServer').disabled = !project || busy;
    byId('serverSvg').disabled = !project || busy || dirty;
    byId('import').disabled = busy; byId('open').disabled = busy;
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
    byId('evidence').hidden = !records.length;
    byId('evidence').textContent = records.length ? JSON.stringify(records.at(-1), null, 2) : '';
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
  byId('ai').onclick = () => action(async () => {
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
    user = health.user; remoteConfigured = health.runpod_configured;
    byId('aiStatus').textContent = remoteConfigured
      ? 'Connexion RunPod configurée. Le test vérifiera les inférences réelles.'
      : 'RunPod non configuré pour ce module. Import, correction et sauvegarde restent disponibles.';
    await listing(); controls(); message('Prêt à importer une page.');
  }).catch(error => message(error.message));
})();
