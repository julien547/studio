#!/usr/bin/env php
<?php
// HTTP contract test double only; PDF/vector/ZIP contents are tested in Python.
if ($argv[1] !== 'generate-test-batch') exit(2);
$directory = $argv[3]; mkdir($directory, 0700, true);
$levelAt = array_search('--levels', $argv, true);
file_put_contents(dirname($argv[2]) . '/invocation.json', json_encode(['arguments'=>$argv,'levels'=>$levelAt===false?null:json_decode(file_get_contents($argv[$levelAt+1]),true)]));
if (in_array('broken', $argv, true)) { file_put_contents("$directory/partial.pdf", '%PDF-partial'); fwrite(STDERR,json_encode(['error'=>'Génération interrompue.'])); exit(2); }
$results=[];
for($i=1;$i<=3;$i++){ $name="BAT-VEI-$i.pdf";file_put_contents("$directory/$name",'%PDF-fixture');$results[]=['id'=>"vei-$i",'vei'=>$i,'type'=>$i===3?'PI':'PE','file'=>$name]; }
$report=['status'=>'test_batch_complete','production_ready'=>false,'count'=>3,'results'=>$results];
file_put_contents("$directory/rapport.json",json_encode($report));file_put_contents("$directory/plans.zip",'PK-HTTP-test-double');echo json_encode($report);
