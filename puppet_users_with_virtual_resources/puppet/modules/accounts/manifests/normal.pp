# Create normal users. See Readme.
class accounts::normal () {

  $users=hiera_hash(accounts::config::users, {})
  # Create a user without sudo access
  define virtual(
    $pass='!', # Means cannot login with password
    $roles=[], # In hiera so needs to be present but useless
    $shell='/bin/bash',
    $sshkey=undef,
  ) {
    # Thanks to defined, a user will be created only once,
    # preventing double resource creation which is verboten by puppet.
    unless defined (Accounts::Virtual[$title]) {
        accounts::virtual{$title:
            pass   => $pass,
            shell  => $shell,
            sshkey => $sshkey,
            sudo   => false
        }
    }
  }

  create_resources('@accounts::normal::virtual', $users)

  define roles($type) {
    if $title == 'all' {
      Accounts::Normal::Virtual <| |>
    } else{
      Accounts::Normal::Virtual <| roles == $title |>
    }
  }

  $normal = hiera_array(accounts::config::normal, []).reduce({}) |$accumulator, $x| {
    merge ($accumulator, {"$x" =>  {'type' => 'normal'}})
  }

  create_resources('accounts::normal::roles', $normal)
}