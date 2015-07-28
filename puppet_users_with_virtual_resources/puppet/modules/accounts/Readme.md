# Accounts

This module manages user accounts, including sudoer and keys.

## Assumptions

There are only 10 types of users. Those who understand binary and the others.

More to the point, a user can be:

- normal: they have their own homedir, user, group.
- sudo: same as normal, plus passwordless sudo rights to everything

This is handled per server. A user might be sudo on a web server, normal on a database server, and absent on all the other servers.

## User definition
Its usage is fairly simple. All users have to be defined in common.yaml. Definition there does not mean that the user will be automatically added anywhere. There is one extra step, explained later.

To add a user named example, just add an *example* entry under *accounts::config::users* hash:

```yaml
accounts::config::users:
  example:
    # List of roles the user belongs to. Not necessarily matched to linux groups
    # They will be used in user::config::{normal,super} in node yaml files to
    # decide which users are present on a server, and which ones have sudo allowed.
    # Note that all users are part of the implicit 'all' group
    roles: ['warrior', 'priest', 'orc']
    # default: bash
    shell: /bin/zsh
    # Already hashed password.
    # http://thisdataguy.com/2014/06/10/understand-and-generate-unix-passwords
    # python -c 'import crypt; print crypt.crypt("passwerd", "$6$some_random_salt")'
    # empty/absent means no login via password allowed (other means possible)
    pass: '$6$pepper$P9Wt3.3Uqh9UZbvz5/6UPtHqa4KE/2aeyeXbKm0mpv36Z5aCBv0OQEZ1e.aKcPR6RBYvQIa/ToAfdUX6HjEOL1'
    # A PUBLIC rsa key.
    # Empty/absent means not key login allowed (other means possible)
    sshkey: 'a valid public ssh key string'
```

## User deletion

To fully remove a user, add them to the array *accounts::config::killedwithfire* in common.yaml:

```yaml
accounts::config::killedwithfire:
  - kenny
```

Note that deletion is done after creation, so if a user appears in *accounts::config::users* and *accounts::config::killedwithfire*, it will be briefly created before being promptly killed with fire.

## A word about roles

Roles here have no direct Linux counterpart, they have nothing to do with linux groups.
They are only an easy way to manage users inside hiera. You can for instance say
that all sysops belong to the role sysops, and grant sudo to sysops everywhere in one go.

Roles can be added at will, and are just a string tag. Role names will be used later to actually select and create users.

## Usage

To be present on a server, a user must have one of its role added to the *accounts::config::normal* array. To be present **and** have sudo right, a user role must be present in the *accounts::config::sudo* array. Note that being in the sudo array implies being in the normal array.

All values added to these arrays are merged along the hierarchy.
This means that you can add users to specific servers in the node definition.

For instance, if in common.yaml we have:
```yaml
accounts::config::sudo: ['sysadmin']
accounts::config::normal: ['data']
```

in prod-nl-mongodb1.dmdelivery.local.yaml (configuration of the mongo server), we have:
```yaml
accounts::config::sudo: ['data']
accounts::config::normal: ['deployer']
```
Then:

- all sysadmin users will be everywhere, with sudo
- all data users will be everywhere, without sudo
- all data users will have the extra sudo rights on the mongo server
- all deployer users will be on the mongo server only, without sudo

## Technical explanation of the module

The module is divided in 3 classes, ordered:

- sudo
- normal
- killedwithfire

The point is that once a user has been added as a sudo user, then it will not be added again as a normal user (thanks to the [defined] funtion). Ordering is thus important.

As an extra there is a last manifest file, virtual.pp, which defines a resource to actually add a user.

The sudo and normal classes work with virtual resources, in the following way:

- A *roles* resource is defined, direclty called with the list of roles to be created, effectively creating a pure puppet loop over the roles. These resources will then realise the *virtual* user resource define on teh next bullet point, effectively creating a second pure puppet loop, this time over the relevant users filtered via the [spaceship] operator.

- A virtual *virtual* resource is defined, realised by the *roles* resource. This one just realises the generic *accounts::virtual* resource, which will then finally create the user. The point in having the 2 different virtual resources first (sudo and normal), is that then the sudo parameter can be injected before realising the final user. Additionally, these resources will filter out users which will be deleted, not creating them first.

The last class, killedwithfire, just get the list of users to be deleted and trivially delete them.

[defined]:https://docs.puppetlabs.com/references/latest/function.html#defined
[spaceship]:https://docs.puppetlabs.com/puppet/latest/reference/lang_collectors.html