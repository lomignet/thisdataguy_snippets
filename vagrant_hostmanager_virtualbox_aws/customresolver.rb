$cached_addresses = {}
# There is a bug when using virtualbox/dhcp which makes hostmanager not find
# the proper IP, only the loop one: https://github.com/smdahlen/vagrant-hostmanager/issues/86
# The following custom resolver (for linux guests) is a good workaround.
# Furthermore it handles aws private/public IP.

# A limitation (feature?) is that hostmanager only looks at the current provider.
# This means that if you `up` an aws vm, then a virtualbox vm, all aws ips
# will disappear from your host /etc/hosts.
# To prevent this, apply this patch to your hostmanager plugin (1.6.1), probably
# at $HOME/.vagramt.d/gems/gems or (hopefully) wait for newer versions.
# https://github.com/smdahlen/vagrant-hostmanager/pull/169
$ip_resolver = proc do |vm, resolving_vm|
  # For aws, we should use private IP on the guests, public IP on the host
  if vm.provider_name == :aws
    if resolving_vm.nil?
      used_name = vm.name.to_s + '--host'
    else
      used_name = vm.name.to_s + '--guest'
    end
  else
    used_name= vm.name.to_s
  end

  if $cached_addresses[used_name].nil?
    if hostname = (vm.ssh_info && vm.ssh_info[:host])

      # getting aws guest ip *for the host*, we want the public IP in that case.
      if vm.provider_name == :aws and resolving_vm.nil?
        vm.communicate.execute('curl http://169.254.169.254/latest/meta-data/public-ipv4') do |type, pubip|
          $cached_addresses[used_name] = pubip
        end
      else

        vm.communicate.execute('uname -o') do |type, uname|
          unless uname.downcase.include?('linux')
            warn("Guest for #{vm.name} (#{vm.provider_name}) is not Linux, hostmanager might not find an IP.")
          end
        end

        vm.communicate.execute('hostname --all-ip-addresses') do |type, hostname_i|
          # much easier (but less fun) to work in ruby than sed'ing or perl'ing from shell

          allips = hostname_i.strip().split(' ')
          if vm.provider_name == :virtualbox
            # 10.0.2.15 is the default virtualbox IP in NAT mode.
            allips = allips.select { |x| x != '10.0.2.15'}
          end

          if allips.size() == 0
            warn("Trying to find out ip for #{vm.name} (#{vm.provider_name}), found none useable: #{allips}.")
          else
            if allips.size() > 1
              warn("Trying to find out ip for #{vm.name} (#{vm.provider_name}), found too many: #{allips} and I cannot choose cleverly. Will select the first one.")
            end
            $cached_addresses[used_name] = allips[0]
          end
        end
      end
    end
  end
  $cached_addresses[used_name]
end
