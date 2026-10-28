<?php
// HTTP persistence/authorization regression with a stub of the Python CLI.
// Actual PDF/schema/clipping checks are in engine/tests/test_levels.py.
$root = dirname(__DIR__);
$tmp = sys_get_temp_dir() . '/doemo-levels-api-' . bin2hex(random_bytes(8));
mkdir($tmp, 0700); mkdir("$tmp/jobs"); mkdir("$tmp/results");
$server = null;
function check($ok, $why) { if (!$ok) throw new RuntimeException($why); }
function remove_tree($path) { foreach (scandir($path) as $x) if ($x !== '.' && $x !== '..') { $p = "$path/$x"; is_dir($p) ? remove_tree($p) : unlink($p); } rmdir($path); }
function call_api($port, $action, $cookie, $body = null) {
    $options = ['method' => $body === null ? 'GET' : 'POST', 'ignore_errors' => true, 'timeout' => 5,
        'header' => "Content-Type: application/json\r\nOrigin: https://studio.doemo.fr\r\nCookie: studio_sid=$cookie\r\n"];
    if ($body !== null) $options['content'] = json_encode($body);
    $text = file_get_contents("http://127.0.0.1:$port/api/orientation.php?action=$action", false, stream_context_create(['http' => $options]));
    preg_match('/^HTTP\/\S+ (\d+)/', $http_response_header[0], $m);
    return [(int)$m[1], json_decode($text, true)];
}
try {
    $job = '1111111111111111'; mkdir("$tmp/jobs/$job");
    file_put_contents("$tmp/jobs/$job/meta.json", json_encode(['login' => 'owner', 'name' => 'BAT.pdf', 'created' => 1]));
    file_put_contents("$tmp/jobs/$job/source.pdf", '%PDF-test-stub');
    session_save_path($tmp); session_name('studio_sid');
    $cookies = [];
    foreach (['owner', 'other', 'admin'] as $login) {
        $id=bin2hex(random_bytes(16)); session_id($id); session_start();
        $_SESSION=['login'=>$login,'role'=>$login==='admin'?'admin':'dessinateur','t'=>time()]; session_write_close(); $cookies[$login]=$id;
    }
    $socket=stream_socket_server('tcp://127.0.0.1:0', $errno, $error);
    $port=(int)substr(strrchr(stream_socket_get_name($socket,false),':'),1); fclose($socket);
    $env=getenv(); $env['DOEMO_PRIVATE_JOBS']="$tmp/jobs"; $env['DOEMO_RESULTS_ROOT']="$tmp/results"; $env['DOEMO_PDF_BIN']="$root/tests/fixtures/levels-engine-stub.php";
    $server=proc_open([PHP_BINARY,'-d',"session.save_path=$tmp",'-d','session.gc_probability=0','-S',"127.0.0.1:$port",'-t',$root],
        [0=>['file','/dev/null','r'],1=>['file',"$tmp/server.log",'a'],2=>['file',"$tmp/server.log",'a']],$pipes,null,$env);
    for($i=0;$i<50;$i++){ $connection=@stream_socket_client("tcp://127.0.0.1:$port",$errno,$error,0.1); if($connection){fclose($connection);break;} usleep(20000); }
    [$code,$data]=call_api($port,"levels&job=$job",$cookies['owner']);
    check($code===200 && $data['document']['revision']===0,'Le dessinateur doit pouvoir créer ses sélections.');
    $doc=$data['document']; $doc['levels']=[['id'=>'rdc','name'=>'RDC','page'=>1,'contours'=>[['id'=>'L','nodes'=>[['x'=>1.123456789,'y'=>2]]]]]];
    [$code,$data]=call_api($port,'levels',$cookies['owner'],['job'=>$job,'document'=>$doc]);
    check($code===200 && $data['document']['revision']===1,'Sauvegarde atomique avec révision.');
    $saved=$data['document'];
    [$code,$data]=call_api($port,"levels&job=$job",$cookies['owner']);
    check($code===200 && $data['document']===$saved,'Reprise exacte du JSON.');
    [$code]=call_api($port,'levels',$cookies['owner'],['job'=>$job,'document'=>$doc]);
    check($code===409,'Une ancienne révision ne doit pas écraser une nouvelle.');
    $bad=$saved; $bad['source']['sha256']='different';
    [$code]=call_api($port,'levels',$cookies['owner'],['job'=>$job,'document'=>$bad]);
    check($code===422,'Un autre BAT doit être refusé.');
    [$code]=call_api($port,"levels&job=$job",$cookies['other']); check($code===403,'Projet privé du dessinateur.');
    [$code,$data]=call_api($port,'projects',$cookies['other']); check($code===200 && $data['projects']===[],'Liste filtrée par propriétaire.');
    [$code,$data]=call_api($port,'projects',$cookies['admin']); check($code===200 && count($data['projects'])===1,'Reprise administrative.');
    check(json_decode(file_get_contents("$tmp/jobs/$job/levels.json"),true)===$saved,'Les refus ne doivent pas changer la sauvegarde.');
    check(glob("$tmp/jobs/$job/.levels-*")===[],'Aucun fichier temporaire abandonné.');
    echo "8 scénarios HTTP de niveaux réussis (CLI simulé) : sauvegarde, reprise, conflit, compatibilité, autorisations et projets.\n";
} finally {
    if(is_resource($server)){proc_terminate($server);proc_close($server);} remove_tree($tmp);
}
