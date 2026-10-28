<?php
// Gestion des trames (PDF) : /var/lib/doemo-studio/templates/<dossier>/...
// Lecture : tout utilisateur interne. Écriture (import, nouveau dossier, suppression) : admin / administration.
require __DIR__ . '/_s.php';
const TPL_BASE = '/var/lib/doemo-studio/templates';
const TPL_MAX_BYTES = 52428800;           // 50 Mo par fichier
const TPL_MAX_DEPTH = 4;
const TPL_WRITE_ROLES = ['admin', 'administration'];
const TPL_PROTEGES = ['doemo'];           // dossiers racine non supprimables

studio_start();
if (empty($_SESSION['login']) || !in_array($_SESSION['role'] ?? '', STUDIO_ROLES_INTERNES, true) || (time() - (int)($_SESSION['t'] ?? 0)) > 43200) {
    studio_json(401, ['ok' => false, 'error' => 'Session expirée.']);
}
$canWrite = in_array($_SESSION['role'], TPL_WRITE_ROLES, true);

function tpl_name_ok($s) {
    return is_string($s) && strpos($s, '..') === false && preg_match('/^[\p{L}\p{N}][\p{L}\p{N}._ -]{0,100}$/u', $s) === 1;
}
function tpl_segments($rel) {
    $rel = trim((string)$rel, '/');
    if ($rel === '') return [];
    $seg = explode('/', $rel);
    if (count($seg) > TPL_MAX_DEPTH) return null;
    foreach ($seg as $s) if (!tpl_name_ok($s)) return null;
    return $seg;
}
function tpl_abs(array $seg) { return TPL_BASE . ($seg ? '/' . implode('/', $seg) : ''); }
// Chemin existant, résolu et strictement contenu dans la base (anti-traversée, anti-lien symbolique).
function tpl_existing(array $seg) {
    $base = realpath(TPL_BASE); $p = realpath(tpl_abs($seg));
    if ($base === false || $p === false) return null;
    return ($p === $base || strpos($p, $base . '/') === 0) ? $p : null;
}
function tpl_log($action, $path) {
    @file_put_contents(TPL_BASE . '/.journal.log', date('c') . "\t" . $_SESSION['login'] . "\t" . $action . "\t" . $path . "\n", FILE_APPEND | LOCK_EX);
}
function tpl_trash($abs, $rel) {
    $d = TPL_BASE . '/.corbeille';
    if (!is_dir($d)) { @mkdir($d, 02770); }
    return @rename($abs, $d . '/' . date('Ymd-His') . '_' . str_replace('/', '__', $rel));
}
function tpl_need_write($canWrite) {
    if (!$canWrite) studio_json(403, ['ok' => false, 'error' => 'Modification réservée aux administrateurs.']);
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') studio_json(405, ['ok' => false, 'error' => 'Méthode non autorisée.']);
    studio_same_origin();
    if (($_SERVER['HTTP_ORIGIN'] ?? '') === '' && ($_SERVER['HTTP_SEC_FETCH_SITE'] ?? '') !== 'same-origin') studio_json(403, ['ok' => false, 'error' => 'Origine refusée.']);
}

$action = (string)($_GET['action'] ?? $_POST['action'] ?? '');
$in = [];
if (($_SERVER['CONTENT_TYPE'] ?? '') !== '' && stripos($_SERVER['CONTENT_TYPE'], 'application/json') === 0) {
    $in = json_decode(file_get_contents('php://input'), true) ?: [];
    if (isset($in['action'])) $action = (string)$in['action'];
}
$relIn = (string)($_GET['path'] ?? $_POST['path'] ?? ($in['path'] ?? ''));
$seg = tpl_segments($relIn);
if ($seg === null) studio_json(400, ['ok' => false, 'error' => 'Chemin invalide.']);

if ($action === 'list') {
    $abs = tpl_existing($seg);
    if ($abs === null || !is_dir($abs)) studio_json(404, ['ok' => false, 'error' => 'Dossier introuvable.']);
    $out = [];
    foreach (scandir($abs) as $n) {
        if ($n[0] === '.') continue;
        $p = $abs . '/' . $n;
        if (is_link($p)) continue;
        if (is_dir($p)) {
            $c = 0; foreach (scandir($p) as $m) if ($m[0] !== '.') $c++;
            $out[] = ['name' => $n, 'type' => 'dir', 'items' => $c, 'mtime' => filemtime($p), 'protected' => !$seg && in_array($n, TPL_PROTEGES, true)];
        } elseif (is_file($p) && strtolower(pathinfo($n, PATHINFO_EXTENSION)) === 'pdf') {
            $out[] = ['name' => $n, 'type' => 'file', 'size' => filesize($p), 'mtime' => filemtime($p)];
        }
    }
    usort($out, function ($a, $b) { return ($a['type'] !== $b['type']) ? ($a['type'] === 'dir' ? -1 : 1) : strcasecmp($a['name'], $b['name']); });
    studio_json(200, ['ok' => true, 'path' => implode('/', $seg), 'canWrite' => $canWrite, 'entries' => $out]);
}

if ($action === 'download') {
    $abs = tpl_existing($seg);
    if ($abs === null || !is_file($abs) || strtolower(pathinfo($abs, PATHINFO_EXTENSION)) !== 'pdf') studio_json(404, ['ok' => false, 'error' => 'Fichier introuvable.']);
    header('Content-Type: application/pdf');
    header('X-Content-Type-Options: nosniff');
    header('Cache-Control: private, no-store');
    header('Content-Length: ' . filesize($abs));
    header('Content-Disposition: ' . (isset($_GET['dl']) ? 'attachment' : 'inline') . '; filename="' . rawurlencode(basename($abs)) . '"');
    readfile($abs);
    exit;
}

if ($action === 'mkdir') {
    tpl_need_write($canWrite);
    $name = (string)($in['name'] ?? '');
    if (!tpl_name_ok($name)) studio_json(400, ['ok' => false, 'error' => 'Nom de dossier invalide (lettres, chiffres, espace, tiret, point, souligné).']);
    $parent = tpl_existing($seg);
    if ($parent === null || !is_dir($parent)) studio_json(404, ['ok' => false, 'error' => 'Dossier parent introuvable.']);
    if (count($seg) + 1 > TPL_MAX_DEPTH) studio_json(400, ['ok' => false, 'error' => 'Profondeur maximale atteinte.']);
    $new = $parent . '/' . $name;
    if (file_exists($new)) studio_json(409, ['ok' => false, 'error' => 'Ce dossier existe déjà.']);
    if (!@mkdir($new, 02770)) studio_json(500, ['ok' => false, 'error' => 'Création impossible.']);
    @chmod($new, 02770);
    tpl_log('mkdir', implode('/', array_merge($seg, [$name])));
    studio_json(200, ['ok' => true]);
}

if ($action === 'upload') {
    tpl_need_write($canWrite);
    $dir = tpl_existing($seg);
    if (!$seg) studio_json(400, ['ok' => false, 'error' => 'Ouvrez un dossier (par exemple doemo) pour importer une trame.']);
    if ($dir === null || !is_dir($dir)) studio_json(404, ['ok' => false, 'error' => 'Dossier introuvable.']);
    $files = $_FILES['files'] ?? null;
    if (!$files || !is_array($files['name'])) studio_json(400, ['ok' => false, 'error' => 'Aucun fichier reçu (50 Mo maximum par fichier).']);
    $done = []; $errors = [];
    foreach ($files['name'] as $i => $orig) {
        $label = (string)$orig;
        if ($files['error'][$i] !== UPLOAD_ERR_OK) { $errors[] = "$label : réception impossible (50 Mo maximum)."; continue; }
        $name = preg_replace('/\s+/u', ' ', trim(basename($label)));
        if (!tpl_name_ok($name) || strtolower(pathinfo($name, PATHINFO_EXTENSION)) !== 'pdf') { $errors[] = "$label : nom invalide ou fichier non PDF."; continue; }
        if ($files['size'][$i] > TPL_MAX_BYTES) { $errors[] = "$label : dépasse 50 Mo."; continue; }
        $fh = @fopen($files['tmp_name'][$i], 'rb'); $magic = $fh ? fread($fh, 5) : ''; if ($fh) fclose($fh);
        if ($magic !== '%PDF-') { $errors[] = "$label : ce n'est pas un PDF."; continue; }
        $dest = $dir . '/' . $name; $rel = implode('/', array_merge($seg, [$name]));
        $replaced = false;
        if (file_exists($dest)) { if (!tpl_trash($dest, $rel)) { $errors[] = "$label : remplacement impossible."; continue; } $replaced = true; }
        if (!move_uploaded_file($files['tmp_name'][$i], $dest)) { $errors[] = "$label : écriture impossible."; continue; }
        @chmod($dest, 0660);
        tpl_log($replaced ? 'replace' : 'upload', $rel);
        $done[] = $name;
    }
    studio_json($done ? 200 : 400, ['ok' => (bool)$done, 'done' => $done, 'errors' => $errors, 'error' => $done ? null : implode(' ', $errors)]);
}

if ($action === 'delete') {
    tpl_need_write($canWrite);
    if (!$seg) studio_json(400, ['ok' => false, 'error' => 'Chemin requis.']);
    $abs = tpl_existing($seg);
    if ($abs === null) studio_json(404, ['ok' => false, 'error' => 'Introuvable.']);
    $rel = implode('/', $seg);
    if (is_dir($abs)) {
        if (count($seg) === 1 && in_array($seg[0], TPL_PROTEGES, true)) studio_json(403, ['ok' => false, 'error' => 'Ce dossier ne peut pas être supprimé.']);
        foreach (scandir($abs) as $m) if ($m[0] !== '.') studio_json(409, ['ok' => false, 'error' => 'Le dossier n\'est pas vide : supprimez d\'abord son contenu.']);
        if (!@rmdir($abs)) studio_json(500, ['ok' => false, 'error' => 'Suppression impossible.']);
        tpl_log('rmdir', $rel); studio_json(200, ['ok' => true]);
    }
    if (!is_file($abs) || strtolower(pathinfo($abs, PATHINFO_EXTENSION)) !== 'pdf') studio_json(400, ['ok' => false, 'error' => 'Type non supporté.']);
    if (!tpl_trash($abs, $rel)) studio_json(500, ['ok' => false, 'error' => 'Suppression impossible.']);
    tpl_log('delete', $rel);
    studio_json(200, ['ok' => true]);
}

studio_json(400, ['ok' => false, 'error' => 'Action inconnue.']);
