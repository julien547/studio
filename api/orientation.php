<?php
// Inspection et diagnostic explicite. L'action compose refuse la génération
// métier tant que le moteur ne sait pas isoler les VEI et redresser les objets.
// compose-diagnostic reste un essai technique : production_ready est toujours false.
// Accès : admin / administration / dessinateur. Fichiers privés (hors web).
require __DIR__ . '/_s.php';
const OR_TEMPLATES = '/var/lib/doemo-studio/templates';
define('OR_PRIVATE', getenv('DOEMO_PRIVATE_JOBS') ?: '/var/lib/doemo-studio/private/jobs');
define('OR_RESULTS', getenv('DOEMO_RESULTS_ROOT') ?: '/var/lib/doemo-studio/results');
define('OR_BIN', getenv('DOEMO_PDF_BIN') ?: '/opt/doemo-studio/venv-pdf/bin/doemo-pdf');
const OR_ROLES = ['admin', 'administration', 'dessinateur'];
const OR_MAX_BYTES = 52428800;   // 50 Mo
const OR_KEEP_DAYS = 14;

studio_start();
if (empty($_SESSION['login']) || !in_array($_SESSION['role'] ?? '', STUDIO_ROLES_INTERNES, true) || (time() - (int)($_SESSION['t'] ?? 0)) > 43200) {
    studio_json(401, ['ok' => false, 'error' => 'Session expirée.']);
}
if (!in_array($_SESSION['role'], OR_ROLES, true)) studio_json(403, ['ok' => false, 'error' => 'Cet outil est réservé aux administrateurs et dessinateurs.']);
$login = $_SESSION['login']; $isAdmin = in_array($_SESSION['role'], ['admin', 'administration'], true);
session_write_close();

function or_post_guard() {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') studio_json(405, ['ok' => false, 'error' => 'Méthode non autorisée.']);
    studio_same_origin();
    if (($_SERVER['HTTP_ORIGIN'] ?? '') === '' && ($_SERVER['HTTP_SEC_FETCH_SITE'] ?? '') !== 'same-origin') studio_json(403, ['ok' => false, 'error' => 'Origine refusée.']);
}
function or_name_ok($s) { return is_string($s) && strpos($s, '..') === false && preg_match('/^[\p{L}\p{N}][\p{L}\p{N}._ -]{0,100}$/u', $s) === 1; }
function or_job_ok($id) { return is_string($id) && preg_match('/^[a-f0-9]{16}$/', $id) === 1; }
function or_job_meta($id, $login, $isAdmin) {
    if (!or_job_ok($id)) studio_json(400, ['ok' => false, 'error' => 'Travail invalide.']);
    $f = OR_PRIVATE . "/$id/meta.json";
    $m = is_file($f) ? json_decode(file_get_contents($f), true) : null;
    if (!is_array($m)) studio_json(404, ['ok' => false, 'error' => 'Travail introuvable.']);
    if (!$isAdmin && ($m['login'] ?? '') !== $login) studio_json(403, ['ok' => false, 'error' => 'Projet non autorisé.']);
    return $m;
}
// Exécute le moteur sans shell, avec délai et plafonds mémoire / CPU / taille de fichier.
function or_run(array $args, $timeout = 100) {
    $cmd = array_merge(['/usr/bin/timeout', '--kill-after=5', (string)$timeout, '/usr/bin/prlimit', '--as=3221225472', '--cpu=' . $timeout, '--fsize=268435456', OR_BIN], $args);
    $p = proc_open($cmd, [1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes, '/tmp', ['PATH' => '/usr/local/bin:/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE' => '1', 'DOEMO_TEMPLATES_ROOT' => OR_TEMPLATES, 'LANG' => 'C.UTF-8']);
    if (!is_resource($p)) return [127, '', 'lancement impossible'];
    $out = stream_get_contents($pipes[1], 4194304); $err = stream_get_contents($pipes[2], 65536);
    foreach ($pipes as $x) fclose($x);
    return [proc_close($p), (string)$out, (string)$err];
}
function or_rmtree($d) {
    if (!is_dir($d)) return;
    foreach (scandir($d) as $n) { if ($n === '.' || $n === '..') continue; $p = "$d/$n"; (is_dir($p) && !is_link($p)) ? or_rmtree($p) : @unlink($p); }
    @rmdir($d);
}
function or_cleanup() {
    foreach ([OR_PRIVATE, OR_RESULTS] as $base) {
        if (!is_dir($base)) continue;
        foreach (scandir($base) as $n) if (or_job_ok($n) && !is_file(OR_PRIVATE . "/$n/levels.json") && filemtime("$base/$n") < time() - OR_KEEP_DAYS * 86400) or_rmtree("$base/$n");
    }
}
function or_mkdir($d) { if (!is_dir($d)) { @mkdir($d, 02770, true); @chmod($d, 02770); } return is_dir($d); }
function or_template($ref) {
    $parts = explode('/', (string)$ref);
    if (count($parts) !== 2 || !or_name_ok($parts[0]) || !or_name_ok($parts[1]) || strtolower(pathinfo($parts[1], PATHINFO_EXTENSION)) !== 'pdf') return null;
    $root = realpath(OR_TEMPLATES); $p = realpath(OR_TEMPLATES . '/' . $parts[0] . '/' . $parts[1]);
    if ($root === false || $p === false || strpos($p, $root . '/') !== 0 || !is_file($p)) return null;
    return $p;
}
// Les messages du moteur ne doivent pas révéler de chemin du serveur.
function or_msg($raw, $fallback) {
    $m = json_decode((string)$raw, true); $e = is_array($m) && isset($m['error']) ? (string)$m['error'] : '';
    $e = preg_replace('#(/[A-Za-z0-9._@%+-]+){2,}#', 'le fichier', $e);
    return $e !== '' ? mb_substr($e, 0, 300) : $fallback;
}
function or_num($v, $min = -1e7, $max = 1e7) { if (!is_numeric($v)) return null; $f = (float)$v; return (is_finite($f) && $f >= $min && $f <= $max) ? $f : null; }

$action = (string)($_GET['action'] ?? '');
require __DIR__ . '/_orientation_levels.php';

if ($action === 'capabilities') {
    studio_json(200, ['ok' => true, 'production_ready' => false,
        'generation_available' => false, 'diagnostic_available' => true,
        'diagnostic_action' => 'compose-diagnostic', 'planning_action' => 'plan',
        'generation_scope' => 'all_vei', 'template_selection' => 'automatic_by_client_type_paper_orientation']);
}

if ($action === 'compose') {
    or_post_guard();
    // Refuser avant tout lancement ou création de PDF. Une sortie de diagnostic
    // ne peut pas satisfaire une demande de déclinaison, même si le CLI réussit.
    studio_json(422, ['ok' => false, 'status' => 'generation_unavailable',
        'production_ready' => false, 'code' => 'GENERATION_NOT_IMPLEMENTED',
        'error' => 'La génération de plans n’est pas encore opérationnelle : le moteur ne sait pas conserver un seul « Vous êtes ici » et redresser les textes et pictogrammes. Aucun plan n’a été généré.']);
}

if ($action === 'plan') {
    or_post_guard();
    $in = json_decode(file_get_contents('php://input'), true);
    if (!is_array($in)) studio_json(400, ['ok' => false, 'error' => 'Demande invalide.']);
    $collection = $in['collection'] ?? 'doemo';
    if (!or_name_ok($collection)) {
        studio_json(400, ['ok' => false, 'error' => 'Collection de trames invalide.']);
    }
    $id = (string)($in['job'] ?? '');
    or_job_meta($id, $login, $isAdmin);
    [$code, $out, $err] = or_run(['plan-batch', OR_PRIVATE . "/$id/source.pdf", '--client', $collection], 100);
    $batch = json_decode($out, true);
    if ($code !== 0 || !is_array($batch) || ($batch['status'] ?? '') !== 'planning_only') {
        studio_json(422, ['ok' => false, 'error' => 'Analyse du BAT impossible : ' . or_msg($err, 'préparation du lot impossible.')]);
    }
    studio_json(200, ['ok' => true, 'status' => 'planning_only', 'production_ready' => false,
        'job' => $id, 'batch' => $batch]);
}

if ($action === 'templates') {
    $out = [];
    if (is_dir(OR_TEMPLATES)) foreach (scandir(OR_TEMPLATES) as $c) {
        if (!or_name_ok($c) || !is_dir(OR_TEMPLATES . "/$c") || is_link(OR_TEMPLATES . "/$c")) continue;
        $files = [];
        foreach (scandir(OR_TEMPLATES . "/$c") as $f) if ($f[0] !== '.' && is_file(OR_TEMPLATES . "/$c/$f") && strtolower(pathinfo($f, PATHINFO_EXTENSION)) === 'pdf') $files[] = $f;
        sort($files, SORT_NATURAL | SORT_FLAG_CASE);
        $out[] = ['collection' => $c, 'files' => $files];
    }
    studio_json(200, ['ok' => true, 'collections' => $out]);
}

if ($action === 'upload') {
    or_post_guard();
    if (!or_mkdir(OR_PRIVATE) || !or_mkdir(OR_RESULTS)) studio_json(500, ['ok' => false, 'error' => 'Stockage indisponible.']);
    or_cleanup();
    $f = $_FILES['file'] ?? null;
    if (!$f || !is_string($f['name'] ?? null) || $f['error'] !== UPLOAD_ERR_OK) studio_json(400, ['ok' => false, 'error' => 'Aucun fichier reçu (50 Mo maximum).']);
    $orig = trim(basename($f['name']));
    if (!or_name_ok($orig) || !in_array(strtolower(pathinfo($orig, PATHINFO_EXTENSION)), ['pdf', 'ai'], true)) studio_json(400, ['ok' => false, 'error' => 'Déposez un BAT au format PDF (ou AI compatible PDF).']);
    if ($f['size'] > OR_MAX_BYTES) studio_json(400, ['ok' => false, 'error' => 'Fichier trop volumineux (50 Mo maximum).']);
    $fh = @fopen($f['tmp_name'], 'rb'); $magic = $fh ? fread($fh, 5) : ''; if ($fh) fclose($fh);
    if ($magic !== '%PDF-') studio_json(400, ['ok' => false, 'error' => "Ce fichier n'est pas un PDF."]);
    $id = bin2hex(random_bytes(8));
    $dir = OR_PRIVATE . "/$id";
    if (!or_mkdir($dir)) studio_json(500, ['ok' => false, 'error' => 'Stockage indisponible.']);
    $src = "$dir/source.pdf";
    if (!move_uploaded_file($f['tmp_name'], $src)) { or_rmtree($dir); studio_json(500, ['ok' => false, 'error' => 'Écriture impossible.']); }
    @chmod($src, 0660);
    file_put_contents("$dir/meta.json", json_encode(['login' => $login, 'name' => $orig, 'created' => time()]));
    @chmod("$dir/meta.json", 0660);
    [$code, $out, $err] = or_run(['inspect', $src], 60);
    $info = json_decode($out, true);
    if ($code !== 0 || !is_array($info)) {
        or_rmtree($dir);
        studio_json(422, ['ok' => false, 'error' => 'Fichier refusé par le moteur : ' . or_msg($err, 'analyse impossible.')]);
    }
    $pages = [];
    foreach (($info['pages'] ?? []) as $p) {
        $pages[] = ['page' => $p['page'] ?? 0, 'media_box' => $p['media_box'] ?? null, 'rotation' => $p['rotation'] ?? 0,
                    'paths' => $p['vector_evidence']['path_paint_operators'] ?? 0, 'images' => $p['vector_evidence']['image_resources'] ?? 0,
                    'labels' => array_slice($p['label_candidates'] ?? [], 0, 60)];
    }
    studio_json(200, ['ok' => true, 'job' => $id, 'name' => $orig, 'pageCount' => $info['page_count'] ?? count($pages), 'pages' => $pages,
                      'layers' => array_values(array_map(function ($l) { return $l['name'] ?? ''; }, $info['layers'] ?? []))]);
}

if ($action === 'compose-diagnostic') {
    or_post_guard();
    $in = json_decode(file_get_contents('php://input'), true) ?: [];
    $id = (string)($in['job'] ?? ''); $meta = or_job_meta($id, $login, $isAdmin);
    $tpl = or_template($in['template'] ?? '');
    if ($tpl === null) studio_json(400, ['ok' => false, 'error' => 'Trame invalide.']);
    $z = $in['zone'] ?? []; $d = $in['direction'] ?? [];
    if (!is_array($z) || count($z) !== 4 || !is_array($d) || count($d) !== 2) studio_json(400, ['ok' => false, 'error' => 'Zone ou direction incomplète.']);
    $zone = array_map('or_num', array_values($z)); $dir = array_map('or_num', array_values($d));
    if (in_array(null, $zone, true) || in_array(null, $dir, true)) studio_json(400, ['ok' => false, 'error' => 'Valeurs numériques invalides.']);
    if ($zone[0] >= $zone[2] || $zone[1] >= $zone[3]) studio_json(400, ['ok' => false, 'error' => 'Zone invalide : X0 < X1 et Y0 < Y1.']);
    if ($dir[0] == 0 && $dir[1] == 0) studio_json(400, ['ok' => false, 'error' => 'Direction nulle.']);
    $page = (int)($in['page'] ?? 1); if ($page < 1 || $page > 500) studio_json(400, ['ok' => false, 'error' => 'Page invalide.']);
    $margin = or_num($in['margin'] ?? 12, 0, 200); if ($margin === null) studio_json(400, ['ok' => false, 'error' => 'Marge invalide.']);
    $resDir = OR_RESULTS . "/$id"; if (!or_mkdir($resDir)) studio_json(500, ['ok' => false, 'error' => 'Stockage indisponible.']);
    $outName = 'diagnostic-' . date('Ymd-His') . '.pdf'; $out = "$resDir/$outName";
    $args = ['compose-diagnostic', OR_PRIVATE . "/$id/source.pdf", $tpl, $out, '--zone', $zone[0], $zone[1], $zone[2], $zone[3],
             '--direction', $dir[0], $dir[1], '--page', (string)$page, '--margin', (string)$margin];
    if (!empty($in['reduceOnly'])) $args[] = '--reduce-only';
    [$code, $so, $se] = or_run(array_map('strval', $args), 100);
    $report = json_decode($so, true);
    if ($code !== 0 || !is_array($report)) {
        studio_json(422, ['ok' => false, 'error' => 'Composition refusée : ' . or_msg($se, 'le moteur a échoué.')]);
    }
    if (($report['status'] ?? null) !== 'diagnostic_nonconforming' ||
        ($report['production_ready'] ?? null) !== false ||
        !is_array($report['blockers'] ?? null) || count($report['blockers']) === 0) {
        studio_json(502, ['ok' => false, 'production_ready' => false,
            'error' => 'Le moteur a renvoyé un rapport de diagnostic incomplet.']);
    }
    @chmod($out, 0660);
    @file_put_contents(OR_RESULTS . "/$id/.journal", date('c') . "\t$login\t$outName\n", FILE_APPEND);
    studio_json(200, ['ok' => true, 'status' => 'diagnostic_nonconforming',
        'production_ready' => false, 'job' => $id, 'file' => $outName,
        'warning' => 'Essai technique non conforme : plusieurs VEI, ancien habillage et éléments non redressés peuvent être présents.',
        'report' => $report]);
}

if ($action === 'result') {
    $id = (string)($_GET['job'] ?? ''); or_job_meta($id, $login, $isAdmin);
    $name = (string)($_GET['file'] ?? '');
    if (!preg_match('/^(?:diagnostic-[0-9-]{15}|selection-[a-f0-9]{16})\.pdf$/', $name)) studio_json(400, ['ok' => false, 'error' => 'Fichier invalide.']);
    $p = OR_RESULTS . "/$id/$name";
    if (!is_file($p) || is_link($p)) studio_json(404, ['ok' => false, 'error' => 'Introuvable.']);
    header('Content-Type: application/pdf'); header('X-Content-Type-Options: nosniff'); header('Cache-Control: private, no-store');
    header('Content-Length: ' . filesize($p));
    header('Content-Disposition: ' . (isset($_GET['dl']) ? 'attachment' : 'inline') . '; filename="' . $name . '"');
    readfile($p); exit;
}

studio_json(400, ['ok' => false, 'error' => 'Action inconnue.']);
