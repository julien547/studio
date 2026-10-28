#!/usr/bin/env php
<?php
// Test double only. Does not read or generate PDFs.
if ($argv[1] === 'levels-init') echo json_encode(['document' => ['schema_version'=>1,'revision'=>0,'source'=>['sha256'=>'known'],'levels'=>[],'markers'=>[],'review_acknowledged'=>false]]);
elseif ($argv[1] === 'levels-validate') {
    $doc=json_decode(file_get_contents($argv[3]), true);
    if (($doc['source']['sha256'] ?? '') !== 'known') { fwrite(STDERR,json_encode(['error'=>'BAT incompatible.'])); exit(2); }
    echo json_encode(['document'=>$doc,'report'=>['levels'=>[],'production_ready'=>false]]);
} elseif ($argv[1] === 'inspect') echo json_encode(['page_count'=>1]);
else exit(2);
