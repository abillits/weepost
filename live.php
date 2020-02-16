<?php
//=======================================//
$key = "f38cxZ92m8EgX203Grnv-2";
//=======================================//
function save_cache($data, $name, $timeout) {
    // delete cache
    $id=shmop_open(get_cache_id($name), "a", 0, 0);
    shmop_delete($id);
    shmop_close($id);

    // get id for name of cache
    $id=shmop_open(get_cache_id($name), "c", 0644, strlen(serialize($data)));

    // return int for data size or boolean false for fail
    if ($id) {
        set_timeout($name, $timeout);
        return shmop_write($id, serialize($data), 0);
    }
    else return false;
}

function get_cache($name) {
    if (!check_timeout($name)) {
        $id=shmop_open(get_cache_id($name), "a", 0, 0);
        if (!$id) {
          return false;
        }

        if ($id) $data=unserialize(shmop_read($id, 0, shmop_size($id)));
        else return false;          // failed to load data

        if ($data) {                // array retrieved
            shmop_close($id);
            return $data;
        }
        else return false;          // failed to load data
    }
    else return false;              // data was expired
}

function get_cache_id($name) {
    // maintain list of caches here
    $id=array(  'live-data' => 1
                );

    return $id[$name];
}

function set_timeout($name, $int) {
    $timeout=new DateTime(date('Y-m-d H:i:s'));
    date_add($timeout, date_interval_create_from_date_string("$int seconds"));
    $timeout=date_format($timeout, 'YmdHis');

    $id=shmop_open(100, "a", 0, 0);
    if ($id) $tl=unserialize(shmop_read($id, 0, shmop_size($id)));
    else $tl=array();
    shmop_delete($id);
    shmop_close($id);

    $tl[$name]=$timeout;
    $id=shmop_open(100, "c", 0644, strlen(serialize($tl)));
    shmop_write($id, serialize($tl), 0);
}

function check_timeout($name) {
    $now=new DateTime(date('Y-m-d H:i:s'));
    $now=date_format($now, 'YmdHis');

    $id=shmop_open(100, "a", 0, 0);
    if ($id) $tl=unserialize(shmop_read($id, 0, shmop_size($id)));
    else return true;
    shmop_close($id);

    $timeout=$tl[$name];
    return (intval($now)>intval($timeout));
}
//=======================================//
if (isset($_SERVER['HTTP_KEY']) && $_SERVER['HTTP_KEY'] == base64_encode($key)) {
  //store data
  $live_data = serialize(file_get_contents('php://input'));
  if (strlen($live_data) < 2000) { //just in case something happens and a massive amount of data gets sent. Don't want to take up too much RAM.
    save_cache(serialize(file_get_contents('php://input')), "live-data", 30);
  }
} else {
  //retrieve data
  $live_data = get_cache('live-data');
  if (!$live_data === false) {
    echo unserialize($live_data);
  } else {
    echo '{
            "last-updated": 0
        }';
  }
}
?>
