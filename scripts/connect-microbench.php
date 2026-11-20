<?php
// usage: php connect.php <dsn-host-port-db> N ; prints median ms: connect, session setup, first ci compare, second ci compare, first plain select, catalog-heavy first statement
[$host,$port,$db,$n,$mode]=[$argv[1],$argv[2],$argv[3],(int)$argv[4],$argv[5]??'new'];
$med=fn($a)=>round((function($a){sort($a);return $a[intdiv(count($a),2)];})($a)*1000,2);
$r=['connect'=>[],'setup'=>[],'ci1'=>[],'ci2'=>[],'plain1'=>[]];
for($i=0;$i<$n;$i++){
  $t=hrtime(true);
  $o=[PDO::ATTR_STRINGIFY_FETCHES=>true,PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION];
  if($mode==='persistent')$o[PDO::ATTR_PERSISTENT]=true;
  $p=new PDO("pgsql:host=$host;port=$port;dbname=$db",'shopware','shopware',$o);
  $r['connect'][]=(hrtime(true)-$t)/1e9; $t=hrtime(true);
  $p->exec("SET NAMES 'utf8'");$p->exec("SET TIME ZONE 'UTC'");
  $r['setup'][]=(hrtime(true)-$t)/1e9; $t=hrtime(true);
  $p->query("select 1")->fetchAll();
  $r['plain1'][]=(hrtime(true)-$t)/1e9; $t=hrtime(true);
  $p->query("select count(*) from language where name = 'English' collate ci")->fetchAll();
  $r['ci1'][]=(hrtime(true)-$t)/1e9; $t=hrtime(true);
  $p->query("select count(*) from language where name = 'Deutsch' collate ci")->fetchAll();
  $r['ci2'][]=(hrtime(true)-$t)/1e9;
  $p=null;
}
echo json_encode(array_map($med,$r)),"\n";
