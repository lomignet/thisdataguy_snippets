# Remove users. See Readme.
class accounts::killedwithfire () {

  $deleted=hiera_array(accounts::config::killedwithfire, [])

  user { $deleted:
      ensure => absent,
      managehome => true,
  }

  # build list of sudoer files based on username
  $sudoers=$deleted.map |$x| {sprintf("/etc/sudoers.d/%s", regsubst($x, '\.', '_', 'G'))}
  file {$sudoers:
    ensure => absent,
  }
}