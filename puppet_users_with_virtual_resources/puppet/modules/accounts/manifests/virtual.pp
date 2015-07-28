  # virtual resource to create a local user + their group, key and sudo
define accounts::virtual(
  $pass='!', # Means cannot login with password
  $shell='/bin/bash',
  $sshkey=undef,
  $sudo = false,
  ) {

  # Might be that the $pass field is present in hiera but empty.
  # This would allow passwordless login. Fix this.
  if $pass == '' {
    $pass='!'
  }

  user { $title:
    ensure     =>  present,
    gid        =>  $title,
    shell      =>  $shell,
    home       =>  "/home/${title}",
    password   =>  $pass,
    managehome =>  true,
    require    =>  Group[$title],
  }

  group { $title:
    ensure => present,
    name   => $title,
  }

  # Note that empty strings are false in boolean context, so we filter out
  # absence and emptiness in one go here.
  if ($sshkey) {
    ssh_authorized_key { $title:
      ensure  => 'present',
      type    => 'ssh-rsa',
      key     => '$sshkey',
      user    => $title,
      require => User[$title],
    }
  }

  # filename as per the manual or aliases as per the sudoer spec must not
  # contain dots.
  # As having dots in a username is legit, let's fudge
  $sane_name = regsubst($name, '\.', '_', 'G')
  $sudoers_path = "/etc/sudoers.d/${sane_name}"

  if $sane_name !~ /^[A-Za-z][A-Za-z0-9_]*$/ {
    fail "Will not create sudoers file '${sudoers_path}' (for user \"${name}\").
     Should consist of letters numbers or underscores."
  }

    if ($sudo) {
    file { $sudoers_path:
      ensure  => present,
      content => template("${module_name}/etc/sudoers.d/sudoers.erb"),
      mode    => '0440'
    }
  } else {
    file { $sudoers_path:
      ensure => absent
    }
  }

}
