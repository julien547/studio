<?php
// Session-authenticated bridge to the PRIVATE Unix-socket recognition API.
require __DIR__ . '/_s.php';
studio_start();
$role = (string)($_SESSION['role'] ?? '');
$login = (string)($_SESSION['login'] ?? '');
if ($login === '' || (time() - (int)($_SESSION['t'] ?? 0)) > 43200) studio_json(401, ['ok'=>false,'error'=>'Session expirée.']);
if (!in_array($role, ['admin','administration','dessinateur'], true)) studio_json(403, ['ok'=>false,'error'=>'Rôle non autorisé.']);
session_write_close();
$method = $_SERVER['REQUEST_METHOD'];
if (!in_array($method, ['GET','POST','PUT'], true)) studio_json(405, ['ok'=>false,'error'=>'Méthode refusée.']);
if ($method !== 'GET') {
    studio_same_origin();
    if (($_SERVER['HTTP_ORIGIN'] ?? '') === '' && ($_SERVER['HTTP_SEC_FETCH_SITE'] ?? '') !== 'same-origin') studio_json(403, ['ok'=>false,'error'=>'Origine requise.']);
}
$route = (string)($_GET['route'] ?? '');
if (strlen($route)>2000 || preg_match('/[\x00-\x20\\\\]/', $route) || strpos($route, '..')!==false ||
    !preg_match('#^/(?:projects|libraries|health)(?:[/?]|$)#D', $route)) studio_json(400, ['ok'=>false,'error'=>'Route invalide.']);
$socket = getenv('DOEMO_RELEVES_SOCKET') ?: '/var/run/doemo-releves/backend.sock';
if (@filetype($socket) !== 'socket') studio_json(503, ['ok'=>false,'error'=>'Service de reconnaissance indisponible.']);
if ((int)($_SERVER['CONTENT_LENGTH'] ?? 0) > 540*1024*1024) studio_json(413, ['ok'=>false,'error'=>'Envoi trop volumineux.']);
$headers = ['X-Doemo-User: '.rawurlencode($login), 'X-Doemo-Role: '.$role, 'Accept: */*'];
$ch = curl_init('http://localhost'.$route);
curl_setopt_array($ch,[CURLOPT_UNIX_SOCKET_PATH=>$socket,CURLOPT_PROXY=>'',CURLOPT_RETURNTRANSFER=>true,
    CURLOPT_CONNECTTIMEOUT=>3,CURLOPT_TIMEOUT=>210,CURLOPT_CUSTOMREQUEST=>$method,CURLOPT_FOLLOWLOCATION=>false]);
if ($method !== 'GET') {
    if (stripos($_SERVER['CONTENT_TYPE'] ?? '', 'multipart/form-data') === 0) {
        $body=[];
        foreach (['file','inventory','archive'] as $name) if (isset($_FILES[$name])) {
            $f=$_FILES[$name];
            if (!is_array($f) || $f['error'] !== UPLOAD_ERR_OK || !is_uploaded_file($f['tmp_name'])) studio_json(400,['ok'=>false,'error'=>'Import incomplet ou trop volumineux.']);
            $body[$name]=new CURLFile($f['tmp_name'],'application/octet-stream',basename($f['name']));
        }
        if (isset($_POST['role']) && is_string($_POST['role'])) $body['role']=$_POST['role'];
        curl_setopt($ch,CURLOPT_POSTFIELDS,$body);
    } else {
        $raw=file_get_contents('php://input',false,null,0,16*1024*1024+1);
        if (strlen($raw)>16*1024*1024) studio_json(413,['ok'=>false,'error'=>'Dossier de revue trop volumineux.']);
        $headers[]='Content-Type: application/json';
        curl_setopt($ch,CURLOPT_POSTFIELDS,$raw);
    }
}
curl_setopt($ch,CURLOPT_HTTPHEADER,$headers);
$body=curl_exec($ch);
$status=(int)curl_getinfo($ch,CURLINFO_RESPONSE_CODE);
$contentType=(string)curl_getinfo($ch,CURLINFO_CONTENT_TYPE);
curl_close($ch);
if ($body === false || $status<100) studio_json(503,['ok'=>false,'error'=>'Traitement indisponible ou délai dépassé.']);
http_response_code($status);
header('Cache-Control: private, no-store');
header('X-Content-Type-Options: nosniff');
header('Content-Type: '.(in_array(explode(';',$contentType)[0],['application/json','image/png','application/zip'],true)?$contentType:'application/json'));
if (str_ends_with(parse_url($route,PHP_URL_PATH) ?? '', '/bundle') && $status===200) header('Content-Disposition: attachment; filename="DOEMO-placements.zip"');
echo $body;
