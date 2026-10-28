<?php
// Loopback development router; public root is built by scripts/dev.sh.
$path=rawurldecode(parse_url($_SERVER['REQUEST_URI'],PHP_URL_PATH) ?? '/');
if (preg_match('#(?:^|/)[._]#',$path) || str_contains($path,'..')) { http_response_code(403); exit('Accès refusé.'); }
if ($path==='/releves' || $path==='/releves/') { require __DIR__.'/index.php'; return true; }
if ($path==='/entrainement' || $path==='/entrainement/') { require dirname(__DIR__).'/entrainement/index.php'; return true; }
if ($path!=='/' && !is_file($_SERVER['DOCUMENT_ROOT'].$path)) { http_response_code(404); exit('Introuvable.'); }
return false;
