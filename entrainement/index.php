<?php
require dirname(__DIR__) . '/api/_s.php';
studio_start();
if (empty($_SESSION['login']) || (time()-(int)($_SESSION['t'] ?? 0))>43200) { header('Location: /'); exit; }
if (!in_array($_SESSION['role'] ?? '', ['admin','administration'], true)) { http_response_code(403); exit('Accès réservé aux administrateurs.'); }
session_write_close();
header('Cache-Control: private, no-store');
header('Content-Type: text/html; charset=utf-8');
header("Content-Security-Policy: default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'");
$dist=getenv('DOEMO_RELEVES_DIST') ?: dirname(__DIR__).'/releves/dist';
if (!is_file($dist.'/index.html')) { http_response_code(503); exit('Compiler le frontend DOEMO Studio avant activation.'); }
readfile($dist.'/index.html');
