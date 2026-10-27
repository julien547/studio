<?php
// Session studio : cookie HttpOnly, Secure, SameSite=Strict ; 12 h.
const STUDIO_ORIGIN = 'https://studio.doemo.fr';
const STUDIO_ROLES_INTERNES = ['admin', 'administration', 'dessinateur', 'technicien', 'expedition'];
function studio_start() {
    session_name('studio_sid');
    session_set_cookie_params(['lifetime' => 0, 'path' => '/', 'secure' => true, 'httponly' => true, 'samesite' => 'Strict']);
    ini_set('session.gc_maxlifetime', '43200');
    session_start();
}
function studio_json($code, $data) {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    echo json_encode($data, JSON_UNESCAPED_UNICODE);
    exit;
}
function studio_same_origin() {
    $o = $_SERVER['HTTP_ORIGIN'] ?? '';
    if ($o !== '' && $o !== STUDIO_ORIGIN) studio_json(403, ['ok' => false, 'error' => 'Origine refusée.']);
}
function studio_api($action, array $headers, $body = null) {
    $ch = curl_init('https://gestion.doemo.fr/api_doemo.php?action=' . $action);
    curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 20, CURLOPT_CONNECTTIMEOUT => 5, CURLOPT_SSL_VERIFYPEER => true,
        CURLOPT_POST => true, CURLOPT_POSTFIELDS => $body === null ? '' : json_encode($body), CURLOPT_HTTPHEADER => array_merge(['Content-Type: application/json', 'Accept: application/json'], $headers)]);
    $r = curl_exec($ch); curl_close($ch);
    return $r === false ? null : json_decode($r, true);
}
