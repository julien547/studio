<?php
require dirname(__DIR__) . '/api/_s.php';
studio_start();
if (empty($_SESSION['login']) || time() - (int)($_SESSION['t'] ?? 0) > 43200) {
    header('Location: /'); exit;
}
if (!in_array($_SESSION['role'] ?? '', ['admin', 'administration', 'dessinateur'], true)) {
    http_response_code(403); exit('Accès réservé aux dessinateurs et administrateurs.');
}
session_write_close();
header('Cache-Control: no-store');
?><!doctype html>
<html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DOEMO Studio · Essai du redessin</title><link rel="stylesheet" href="/redessin/workbench.css">
<header><a href="/app/">DOEMO Studio</a><h1>Essai du redessin architectural</h1><span>Validation humaine requise</span></header>
<main><section class="panel">
<p>Importez une page, contrôlez les axes proposés sur le plan original, puis corrigez et enregistrez les murs. Un mur est représenté par un seul trait noir plein.</p>
<p class="notice">La segmentation architecturale spécialisée reste à qualifier. Les propositions géométriques peuvent contenir des erreurs et des murs manquants.</p>
<form id="upload"><label>Plan PDF, PNG ou JPEG · 20 Mio maximum <input id="plan" name="plan" type="file" accept=".pdf,.png,.jpg,.jpeg" required></label>
<label>Page du PDF <input name="page" type="number" min="1" max="10000" value="1" required></label>
<button id="import">Importer et proposer les axes</button></form>
<div class="actions"><label>Mes projets <select id="projects"></select></label><button id="open">Ouvrir</button>
<button id="checkAi" disabled>Vérifier la connexion aux IA</button>
<button id="ai" disabled>Tester les trois IA sur cette page</button><button id="saveServer" disabled>Enregistrer sur OVH</button>
<button id="serverSvg" disabled>SVG validé du serveur</button></div>
<p id="status" role="status">Connexion au service…</p><p id="aiStatus"></p><pre id="evidence" hidden></pre>
</section><section id="editorHost" hidden></section></main>
<script src="/redessin/editor.js" defer></script><script src="/redessin/workbench.js" defer></script></html>
