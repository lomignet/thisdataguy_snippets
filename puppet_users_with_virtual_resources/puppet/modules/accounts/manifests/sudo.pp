# Create super users. See Readme.
class accounts::sudo () {

    $users=hiera_hash(accounts::config::users, {})

    # Create a user with sudo access
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
              sudo   => true
          }
      }
    }

   create_resources('@accounts::sudo::virtual', $users)

    define roles($type) {
        if $title == 'all' {
            Accounts::Sudo::Virtual <| |>
        } else{
            Accounts::Sudo::Virtual <| roles == $title |>
        }
    }

    $sudo = hiera_array(accounts::config::sudo, []).reduce({}) |$accumulator, $x| {
        merge ($accumulator, {"$x" =>  {'type' => 'sudo'}})
    }

    create_resources('accounts::sudo::roles', $sudo)
}