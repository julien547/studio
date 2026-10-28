<?php
// Included after authentication and ownership helpers. Never directly callable.
if (!defined('OR_PRIVATE')) { http_response_code(404); exit; }

if ($action === 'generate-test-batch') {
    or_post_guard(); $input = or_levels_json_input();
    $id = (string)($input['job'] ?? ''); $meta = or_job_meta($id, $login, $isAdmin);
    $collection = $input['collection'] ?? 'doemo';
    if (!or_name_ok($collection)) studio_json(400, ['ok' => false, 'error' => 'Dossier client invalide.']);
    $useLevels = $input['use_levels'] ?? false;
    if (!is_bool($useLevels)) studio_json(400, ['ok' => false, 'error' => 'Option de niveaux invalide.']);
    $lock = fopen(OR_PRIVATE . "/$id/.generation.lock", 'c');
    if (!$lock || !flock($lock, LOCK_EX | LOCK_NB)) studio_json(409, ['ok' => false, 'error' => 'Une génération est déjà en cours pour ce BAT.']);
    $batchId = bin2hex(random_bytes(8)); $parent = OR_RESULTS . "/$id";
    if (!or_mkdir($parent)) studio_json(500, ['ok' => false, 'error' => 'Stockage du lot indisponible.']);
    $destination = "$parent/lot-$batchId";
    $args = ['generate-test-batch', OR_PRIVATE . "/$id/source.pdf", $destination, '--client', $collection, '--basename', pathinfo($meta['name'], PATHINFO_FILENAME)];
    $snapshot = null;
    try {
        if ($useLevels) {
            $saved = OR_PRIVATE . "/$id/levels.json";
            $raw = is_file($saved) ? file_get_contents($saved) : false;
            $doc = $raw !== false ? json_decode($raw, true) : null;
            if (!is_array($doc) || empty($doc['levels'])) studio_json(422, ['ok' => false, 'error' => 'Enregistrez vos niveaux ou désactivez la délimitation facultative.']);
            if (($doc['review_acknowledged'] ?? false) !== true) studio_json(422, ['ok' => false, 'error' => 'Contrôlez visuellement les limites des niveaux, cochez la confirmation puis enregistrez.']);
            $snapshot = tempnam(OR_PRIVATE . "/$id", '.generation-levels-');
            if ($snapshot === false || file_put_contents($snapshot, $raw) === false) studio_json(500, ['ok' => false, 'error' => 'Lecture des sélections impossible.']);
            $args[] = '--levels'; $args[] = $snapshot;
        }
        @set_time_limit(250);
        [$code, $out, $err] = or_run($args, 240);
    } finally {
        if (is_string($snapshot)) @unlink($snapshot);
        flock($lock, LOCK_UN); fclose($lock);
    }
    $report = json_decode($out, true);
    if ($code !== 0 || !is_array($report) || ($report['status'] ?? '') !== 'test_batch_complete' || !is_file("$destination/plans.zip")) {
        if (is_dir($destination)) or_rmtree($destination);
        studio_json(422, ['ok' => false, 'error' => or_msg($err, 'La génération n’a pas abouti ; aucun ZIP incomplet n’est proposé.')]);
    }
    foreach (scandir($destination) as $name) if (is_file("$destination/$name")) @chmod("$destination/$name", 0660);
    @chmod($destination, 02770);
    studio_json(200, ['ok' => true, 'job' => $id, 'batch' => $batchId, 'report' => $report]);
}

if ($action === 'batch-file') {
    $id = (string)($_GET['job'] ?? ''); or_job_meta($id, $login, $isAdmin);
    $batchId = (string)($_GET['batch'] ?? '');
    if (!or_job_ok($batchId)) studio_json(400, ['ok' => false, 'error' => 'Lot invalide.']);
    $directory = OR_RESULTS . "/$id/lot-$batchId";
    if (is_link($directory)) studio_json(404, ['ok' => false, 'error' => 'Lot introuvable.']);
    $report = is_file("$directory/rapport.json") ? json_decode(file_get_contents("$directory/rapport.json"), true) : null;
    if (!is_array($report) || ($report['status'] ?? '') !== 'test_batch_complete') studio_json(404, ['ok' => false, 'error' => 'Lot incomplet ou introuvable.']);
    $name = (string)($_GET['file'] ?? 'plans.zip');
    $allowed = array_merge(['plans.zip', 'rapport.json'], array_column($report['results'], 'file'));
    if ($name !== basename($name) || preg_match('/[\x00-\x1f\x7f]/', $name) || !in_array($name, $allowed, true)) studio_json(400, ['ok' => false, 'error' => 'Fichier invalide.']);
    $path = "$directory/$name";
    if (!is_file($path) || is_link($path)) studio_json(404, ['ok' => false, 'error' => 'Fichier introuvable.']);
    header('Content-Type: ' . ($name === 'plans.zip' ? 'application/zip' : ($name === 'rapport.json' ? 'application/json' : 'application/pdf')));
    header('Cache-Control: private, no-store'); header('X-Content-Type-Options: nosniff');
    header('Content-Length: ' . filesize($path));
    header("Content-Disposition: attachment; filename*=UTF-8''" . rawurlencode($name));
    readfile($path); exit;
}
