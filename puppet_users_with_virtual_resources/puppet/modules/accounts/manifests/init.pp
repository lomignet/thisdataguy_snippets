# Manage users, groups and ssh keys
class accounts (
) {

  # See Readme.md for explanation of the {dirti,awesome}ness of this module.

  anchor { 'accounts::begin': } ->
  class  { 'accounts::sudo': } ->
  class  { 'accounts::normal': } ->
  class  { 'accounts::killedwithfire': } ->
  anchor { 'accounts::end': }

}


