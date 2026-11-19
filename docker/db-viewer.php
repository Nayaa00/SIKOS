<?php
// Local Docker SIKOS browser; authentication is provided through private environment variables.
$cfg['Servers'][1]['verbose'] = 'SIKOS Docker (data aplikasi port 8002)';
$cfg['Servers'][1]['only_db'] = ['sikos'];
$cfg['Servers'][1]['hide_db'] = '^(information_schema|performance_schema|mysql|sys|sikos_test)$';
$cfg['Servers'][1]['AllowNoPassword'] = false;
$cfg['TitleDefault'] = 'SIKOS Docker - Database';
$cfg['TitleDatabase'] = 'SIKOS Docker - @DATABASE@';
$cfg['TitleTable'] = 'SIKOS Docker - @TABLE@';
$cfg['ShowPhpInfo'] = false;
$cfg['ShowChgPassword'] = false;
$cfg['SuhosinDisableWarning'] = true;
