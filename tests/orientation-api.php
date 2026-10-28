<?php
// Régression HTTP : un succès technique ne doit pas livrer un faux plan.
// PHP CLI >= 8 ; serveur et sessions temporaires, aucun accès à Dolibarr.
$root = dirname(__DIR__);
$tmp = sys_get_temp_dir() . '/doemo-api-test-' . bin2hex(random_bytes(8));
mkdir($tmp, 0700);
$server = null;
function check($condition, $message) {
    if (!$condition) throw new RuntimeException($message);
}
function call_api($port, $action, $method, $cookie = '', $origin = 'https://studio.doemo.fr') {
    $headers = "Content-Type: application/json\r\nOrigin: $origin\r\n";
    if ($cookie !== '') $headers .= "Cookie: studio_sid=$cookie\r\n";
    $context = stream_context_create(['http' => [
        'method' => $method, 'header' => $headers, 'ignore_errors' => true,
        'timeout' => 3, 'content' => $method === 'POST' ? '{"job":"0000000000000000"}' : '',
    ]]);
    $body = file_get_contents("http://127.0.0.1:$port/api/orientation.php?action=$action", false, $context);
    preg_match('/^HTTP\/\S+ (\d+)/', $http_response_header[0], $match);
    return [(int)$match[1], json_decode($body, true, 512, JSON_THROW_ON_ERROR)];
}
try {
    session_save_path($tmp);
    session_name('studio_sid');
    $sessions = [];
    foreach (['admin', 'dessinateur'] as $role) {
        $id = bin2hex(random_bytes(16));
        session_id($id);
        session_start();
        $_SESSION = ['login' => 'test', 'role' => $role, 't' => time()];
        session_write_close();
        $sessions[$role] = $id;
    }
    $socket = stream_socket_server('tcp://127.0.0.1:0', $errno, $error);
    check($socket !== false, 'Port de test indisponible.');
    $address = stream_socket_get_name($socket, false);
    $port = (int)substr(strrchr($address, ':'), 1);
    fclose($socket);
    $server = proc_open([PHP_BINARY, '-d', "session.save_path=$tmp", '-d',
        'session.gc_probability=0', '-S', "127.0.0.1:$port", '-t', $root],
        [0 => ['file', '/dev/null', 'r'], 1 => ['file', "$tmp/server.log", 'a'],
         2 => ['file', "$tmp/server.log", 'a']], $pipes);
    check(is_resource($server), 'Serveur PHP non démarré.');
    $ready = false;
    for ($i = 0; $i < 50; $i++) {
        $connection = @stream_socket_client("tcp://127.0.0.1:$port", $errno, $error, 0.1);
        if ($connection) { fclose($connection); $ready = true; break; }
        usleep(20000);
    }
    check($ready, 'Délai de démarrage dépassé.');
    [$status] = call_api($port, 'compose', 'POST');
    check($status === 401, 'Un anonyme doit rester refusé.');
    [$status] = call_api($port, 'compose', 'POST', $sessions['dessinateur']);
    check($status === 403, 'Les rôles non autorisés doivent rester refusés.');
    [$status] = call_api($port, 'compose', 'GET', $sessions['admin']);
    check($status === 405, 'La garde POST doit rester active.');
    [$status] = call_api($port, 'compose', 'POST', $sessions['admin'], 'https://example.org');
    check($status === 403, 'La garde origine doit rester active.');
    [$status, $result] = call_api($port, 'compose', 'POST', $sessions['admin']);
    check($status === 422 && $result['ok'] === false, 'La génération doit échouer explicitement.');
    check($result['code'] === 'GENERATION_NOT_IMPLEMENTED' && $result['production_ready'] === false,
        'Le refus doit indiquer le manque fonctionnel.');
    check(!isset($result['file']), 'Aucun fichier ne doit être proposé comme plan.');
    [$status, $result] = call_api($port, 'capabilities', 'GET', $sessions['admin']);
    check($status === 200 && $result['generation_available'] === false &&
        $result['diagnostic_available'] === true && $result['diagnostic_action'] === 'compose-diagnostic',
        'Le frontend doit pouvoir distinguer diagnostic et génération.');
    [$status] = call_api($port, 'compose-diagnostic', 'POST', $sessions['admin']);
    check($status === 404, 'Le diagnostic explicite doit contrôler le travail demandé.');
    echo "7 scénarios HTTP réussis : authentification, rôle, méthode, origine, refus de génération, capacités, diagnostic explicite.\n";
} finally {
    if (is_resource($server)) { proc_terminate($server); proc_close($server); }
    foreach (glob("$tmp/*") as $file) unlink($file);
    rmdir($tmp);
}
