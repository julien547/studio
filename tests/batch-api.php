<?php
$root=dirname(__DIR__);$tmp=sys_get_temp_dir().'/doemo-batch-api-'.bin2hex(random_bytes(8));mkdir($tmp,0700);mkdir("$tmp/jobs");mkdir("$tmp/results");$server=null;
function check($ok,$why){if(!$ok)throw new RuntimeException($why);}
function remove_tree($path){foreach(scandir($path) as $x)if($x!=='.'&&$x!=='..'){$p="$path/$x";is_dir($p)?remove_tree($p):unlink($p);}rmdir($path);}
function call_api($port,$action,$cookie,$body=null,$origin=true){
 $options=['method'=>$body===null?'GET':'POST','ignore_errors'=>true,'timeout'=>5,'header'=>"Content-Type: application/json\r\nCookie: studio_sid=$cookie\r\n".($origin?"Origin: https://studio.doemo.fr\r\n":'')];
 if($body!==null)$options['content']=json_encode($body);
 $raw=file_get_contents("http://127.0.0.1:$port/api/orientation.php?action=$action",false,stream_context_create(['http'=>$options]));preg_match('/^HTTP\/\S+ (\d+)/',$http_response_header[0],$m);
 return [(int)$m[1],json_decode($raw,true),$raw,implode("\n",$http_response_header)];
}
try{
 $job='1111111111111111';mkdir("$tmp/jobs/$job");file_put_contents("$tmp/jobs/$job/meta.json",json_encode(['login'=>'owner','name'=>'BAT.ai','created'=>time()]));file_put_contents("$tmp/jobs/$job/source.pdf",'%PDF-stub');
 // Existing selections must be ignored when the option is disabled.
 $levels=['review_acknowledged'=>true,'levels'=>[['id'=>'rdc']]];file_put_contents("$tmp/jobs/$job/levels.json",json_encode($levels));
 session_save_path($tmp);session_name('studio_sid');$cookies=[];
 foreach(['owner','other'] as $login){$id=bin2hex(random_bytes(16));session_id($id);session_start();$_SESSION=['login'=>$login,'role'=>'dessinateur','t'=>time()];session_write_close();$cookies[$login]=$id;}
 $socket=stream_socket_server('tcp://127.0.0.1:0',$errno,$error);$port=(int)substr(strrchr(stream_socket_get_name($socket,false),':'),1);fclose($socket);
 $env=getenv();$env['DOEMO_PRIVATE_JOBS']="$tmp/jobs";$env['DOEMO_RESULTS_ROOT']="$tmp/results";$env['DOEMO_PDF_BIN']="$root/tests/fixtures/batch-engine-stub.php";
 $server=proc_open([PHP_BINARY,'-d',"session.save_path=$tmp",'-d','session.gc_probability=0','-S',"127.0.0.1:$port",'-t',$root],[0=>['file','/dev/null','r'],1=>['file',"$tmp/server.log",'a'],2=>['file',"$tmp/server.log",'a']],$pipes,null,$env);
 for($i=0;$i<50;$i++){$c=@stream_socket_client("tcp://127.0.0.1:$port",$errno,$error,.1);if($c){fclose($c);break;}usleep(20000);}
 $input=['job'=>$job,'collection'=>'doemo','use_levels'=>false];
 [$code,$data]=call_api($port,'generate-test-batch',$cookies['owner'],$input);check($code===200&&$data['report']['count']===3,'Lot complet.');$batch=$data['batch'];
 $invocation=json_decode(file_get_contents("$tmp/jobs/$job/invocation.json"),true);check($invocation['levels']===null&&!in_array('--levels',$invocation['arguments'],true),'Les niveaux restent facultatifs, même si un fichier existe.');
 [$code,,$raw,$headers]=call_api($port,"batch-file&job=$job&batch=$batch",$cookies['owner']);check($code===200&&$raw==='PK-HTTP-test-double'&&str_contains($headers,'application/zip'),'Téléchargement ZIP autorisé.');
 [$code,,$raw,$headers]=call_api($port,"batch-file&job=$job&batch=$batch&file=BAT-VEI-1.pdf",$cookies['owner']);check($code===200&&$raw==='%PDF-fixture'&&str_contains($headers,'application/pdf'),'Téléchargement individuel.');
 [$code]=call_api($port,"batch-file&job=$job&batch=$batch",$cookies['other']);check($code===403,'Lot privé.');
 [$code]=call_api($port,"batch-file&job=$job&batch=$batch&file=..%2Fmeta.json",$cookies['owner']);check($code===400,'Traversée de dossier refusée.');
 [$code]=call_api($port,'generate-test-batch',$cookies['owner'],$input,false);check($code===403,'Origine requise.');
 [$code]=call_api($port,'generate-test-batch',$cookies['owner']);check($code===405,'POST requis.');
 $lock=fopen("$tmp/jobs/$job/.generation.lock",'c');flock($lock,LOCK_EX);
 [$code]=call_api($port,'generate-test-batch',$cookies['owner'],$input);check($code===409,'Deux générations simultanées refusées.');flock($lock,LOCK_UN);fclose($lock);
 $input['use_levels']=true;[$code]=call_api($port,'generate-test-batch',$cookies['owner'],$input);check($code===200,'Option de niveaux activable.');
 $invocation=json_decode(file_get_contents("$tmp/jobs/$job/invocation.json"),true);check($invocation['levels']===$levels,'Instantané exact des sélections.');check(glob("$tmp/jobs/$job/.generation-levels-*")===[],'Instantané temporaire supprimé.');
 $before=glob("$tmp/results/$job/lot-*");$input['use_levels']=false;$input['collection']='broken';[$code]=call_api($port,'generate-test-batch',$cookies['owner'],$input);check($code===422&&glob("$tmp/results/$job/lot-*")===$before,'Aucun lot partiel téléchargeable après échec.');
 echo "11 scénarios HTTP de lot réussis (CLI simulé).\n";
}finally{if(is_resource($server)){proc_terminate($server);proc_close($server);}remove_tree($tmp);}
