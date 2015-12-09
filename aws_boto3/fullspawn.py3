#!/usr/bin/env python3
"""
Creates a full AWS infrastructure (vpc, route table, security group, subnet,
internet gateway, instance with the relevant associations and attachments) for
easy testing of AWS without forgetting anything and without waiting for the GUI.

Each one of these resources is tagged with the `--tag` tag and `role` value for
easy matching and fetching.

The goal of this script is to easily set up a full infra for testing purposes, so
it is not very clever nor flexible. Once it ran once, you can use/update
everything created from the GUI or udate the script yourself.

A few variables (uppercase just below) can be updated or your usage, as they
provide defauls which might not be relevant for you.

The api doc can be found https://boto3.readthedocs.org/en/latest/

Caveats:
- Match one set of key/value in resource tag
- only one resource of each type allowed
- subnet has same cidr as vpc
- hardcoded ami, keypair, ingress rules

Advantages:
- idempotent
- resume from where it stopped last time
- works
- much faster than the GUI
- works for AWS beijing as well, where it is MUCH FASTER than the GUI
"""
import argparse
import boto3
import botocore
import logging
import sys
import time
# exception error messages
import traceback
import os

import pdb
#use with pdb.set_trace()

# Some defaults you might want to set for your own use cases
CENTOS_IE = 'ami-33734044'
CENTOS_CN = 'ami-0a8b1733'
AMI = CENTOS_CN if 'AWS_PROFILE' in os.environ and 'cn' in os.environ['AWS_PROFILE'] else CENTOS_IE
KEYPAIR = 'yourkey'  # Add your own here
# Will be added to the 'allow all inside security'
INGRESS = [{
    # You do not really want to open access to the whole world, this is only an example.
    'IpProtocol': '-1',
    'FromPort': 0,
    'ToPort': 0,
    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
}]

parser = argparse.ArgumentParser(
    description='Spawns a full AWS self-contained infrastructure.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter
)

parser.add_argument(
    'role',
    type=str,
    help='Tag value used for marking and fetching resources.'
)

parser.add_argument(
    '--tag', '-t',
    type=str,
    default='roles',
    help='Tag name used for marking and fetching resources.'
)

updown = parser.add_mutually_exclusive_group()
updown.add_argument(
    '--up', '-u',
    dest='action',
    action='store_const',
    const='up',
    help='Creates a full infra.'
)
updown.add_argument(
    '--down', '-d',
    dest='action',
    action='store_const',
    const='down',
    help='Destroys a full infra.'
)
parser.set_defaults(action='up')

wetdry = parser.add_mutually_exclusive_group()
wetdry.add_argument(
    '--wet', '-w',
    dest='dry',
    action='store_const',
    const='wet',
    help='Actually performs the action.'
)
wetdry.add_argument(
    '--dry',
    dest='dry',
    action='store_const',
    const='dry',
    help='Only shows what would be done, not doing anything.'
)
parser.set_defaults(dry='dry')


parser.add_argument(
    '--log',
    dest='loglevel',
    type=str.upper,
    choices='DEBUG INFO WARNING ERROR CRITICAL'.split(),
    default='WARNING',
    help='Verbosity level.'
)
parser.add_argument(
    '--cidr',
    dest='cidr',
    type=str,
    default='10.0.42.0/28',
    help='The network range for the VPC, in CIDR notation. For example, 10.0.0.0/16'
)

parser.add_argument(
    #http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/AMIs.html
    '--ami',
    dest='ami',
    type=str,
    default=AMI,
    help='The AMI id for your instance.'
)

parser.add_argument(
    # http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html
    '--keypair',
    dest='keypair',
    type=str,
    default=KEYPAIR,
    help='A keypair aws knows about.'
)

parser.add_argument(
    #  https://boto3.readthedocs.org/en/latest/guide/configuration.html
    '--profile',
    dest='profile',
    type=str,
    default=os.environ['AWS_PROFILE'] if 'AWS_PROFILE' in os.environ else 'default',
    help='Profile to use for credentials. Will use AWS_PROFILE environment variable if set.'
)

parser.add_argument(
    # https://aws.amazon.com/ec2/instance-types/
    '--instance',
    dest='instance',
    type=str,
    default='t2.micro',
    help='Instance type.'
)


args = parser.parse_args()
# used in many places, so make it its own var to limit keystrokes.
dry = args.dry == 'dry'


class AttrDict(dict):
    # Dark magic to use dict.key as well as dict[key]
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self

# Cached dict of existing resources
_existing = AttrDict({})

# Sets of method names and params per resource type to use generised methods.
# See setup() below to check how this hash is actually used.
# http://boto3.readthedocs.org/en/latest/reference/services/ec2.html#service-resource
definitions = {
    'disk': {'stem': 'volume'},
    'igw':  {'stem': 'internet_gateway'},
    'sg':   {'stem': 'security_group'},
    'sub':  {'stem': 'subnet'},
    'vm':   {'stem': 'instance', 'destroy': 'terminate', 'create': 'create_instances'},
    'vpc':  {'stem': 'vpc'},
}


# Trying to remove debug statements from boto, without success
#logging.getLogger('botocore.hooks').addHandler(logging.NullHandler())
logging.basicConfig(level=getattr(logging, args.loglevel.upper()))

# For some reason, using only AWS_PROFILE fails (AWS was not able to
# validate the provided access credentials), the profile needs to be explicitely
# given.
session = boto3.session.Session(profile_name=args.profile)
print('Connecting to AWS with profile ' + session.profile_name + '.')
ec2 = session.resource('ec2')

# low level interface, used for a few specific calls
ec2_client = ec2.meta.client
regions = ec2_client.describe_regions()
if 'Regions' in regions:
    print('Regions available: ' + ', '.join(sorted(map(lambda x: x['RegionName'], regions['Regions']))))
else:
    print('No region available for those credentials. Problems will ensue.')



def _dict2tags(tags):
    """
    AWS need tags in a form of an array of dict with 2 keys: key and value.
    eg: [{'Key': 'Name', 'Value': 'dataplatform'}, {'Key': 'roles', 'Value': 'DP'}, {'Key': 'DP', 'Value': ''}]
    will be created from {'Name': 'dataplatform', 'roles': 'DP', 'DP': ''}
    """
    awstags = []
    for k, v in tags.items():
        awstags.append({'Key': k, 'Value': v})
    return awstags


def _fetch(resource):
    """
    All resources have more or less the same syntax to fetch them.
    Based on the definitions dict, get them.
    Not that finding more than 1 raises an exception.

    :param resource: `str` telling which resource we want to get (key in definitions)
    :returns: matched resource or None.
    """
    found = []
    for x in getattr(ec2, definitions[resource].fetch).all():
        if x.tags:
            for t in x.tags:
                if t['Key'] == args.tag and t['Value'] == args.role:
                    found.append(x)

    if len(found) > 1:
        raise Exception('More than 1 {r} tagged {k}:{v} found, this is an issue.'.format(
            r=resource,
            k=args.tag,
            v=args.role
        ))
    elif len(found) == 1:
        return found[0]
    else:
        return None


def _create_resource(resource, **options):
    """
    Creates and tag a resource.

    Will update the _existing global var.

    :param resource: `str` telling which resource we want to create (key in definitions)
    :param options: `dict` to pas to the create call.
    :returns: `bool` indicating success or not.
    """
    global _existing

    if _existing[resource]:
        print('{r} {k}:{v} already exists with id {i}.'.format(
            r=resource,
            k=args.tag,
            v=args.role,
            i=_existing[resource].id
        ))
        return True

    print('{v} a {r} with parameters: {p}...'.format(
        v='Would create' if dry else 'Creating',
        r=resource,
        p=str(options)
    ))

    if dry:
        return True

    # All easy cases out of the way, we now need to actually create something.
    r = None
    try:
        r = getattr(ec2, definitions[resource].create)(** options)
        # In some cases (instance) a list is returned instead of one item. Quack!
        try:
            r = r[0]
        except:
            pass
        _tag_resource(r)
        print('... {r} id {i} created.'.format(
            r=resource,
            i=r.id
        ))
        _existing[resource] = r
        return True
    except Exception as e:
        if r is None:
            print('Could not create resource {r}.'.format(
                r=resource
            ))
            traceback.print_exc()
        else:
            print('Could not tag resource {r}, id {i}.'.format(
                r=resource,
                i=r.id
            ))
            traceback.print_exc()
            _destroy_resource(resource)
        return False


def _destroy_resource(resource):
    """
    Will update the _existing global var.
    """
    global _existing
    if _existing[resource]:
        print('{v} a {r} with id: {i}.'.format(
            v='Would destroy' if dry else 'Destroying',
            r=resource,
            i=_existing[resource].id
        ))

        if dry:
            return True
        else:
            try:
                # _existing[resource].delete()
                getattr(_existing[resource], definitions[resource].destroy)()

                if resource == 'vm':
                    # untag resource in case a UP follow very quickly: the instance,
                    # although terminating, still exists for a while
                    print('Postfixing tag of instance {} with -terminated'.format(_existing[resource].id))
                    _tag_resource(_existing[resource], tags={args.tag: args.role + '-terminated'})

                _existing[resource] = None

            except AttributeError as e:

                if resource == 'vm':
                    state = _existing[resource].state['Name']
                    if state in ['terminated', 'shutting-down']:
                        print('Trying to delete a vm {i} wich is {s}. not an issue.'.format(
                            i=_existing[resource].id,
                            s=state
                            ))
                        return True

                # all other cases are problems
                traceback.print_exc()
                return False

            except Exception as e:
                print('Could not destroy resource {r}, id {i}. Reason just below.'.format(
                    r=resource,
                    i=_existing[resource].id,
                ))
                traceback.print_exc()
                return False
            return True
    else:
        print('Trying to destroy a {r} tagged {k}:{v}, but none found'.format(
            r=resource,
            k=args.tag,
            v=args.role
        ))
        return False


def _tag_resource(r, tags=None):
    """
    Add a default args.tag:args.role tag, as well as a Name:args.tag_args.role.
    Note that updating a tag is the same as creating, so this function works for
    update as well.

    :param tags:
        optional `dict` overriding default tags.
    """
    r.create_tags(Tags=_dict2tags(tags if tags else {args.tag: args.role, 'Name': args.tag + '_' + args.role}))


def _tag_volume():
    """
    Tag the newly created volume for an instance.
    """
    if dry:
        print('Would tag the new volume.')
        return True

    while True:
        # waiting for the volume to be up to tag it
        i = _fetch('vm')
        v = [x for x in i.volumes.all()]
        if len(v) == 0:
            # volumes should actually be already there once the IP is up
            time.sleep(1)
        else:
            for x in v:
                print('Tagging volume ' + x.id + '.')
                _tag_resource(x)
            break


def _attach_vpc_igw(vpc=None, igw=None):
    if (vpc and igw):
        attached = False
        for attached_igw in vpc.internet_gateways.all():
            if attached_igw.id == igw.id:
                attached = True
                print ('VPC {v} and igw {i} already attached.'.format(
                    v=vpc.id,
                    i=igw.id,
                ))
            else:
                print('VPC {v} unexpectedly attached to igw {i}'.format(
                    v=vpc.id,
                    i=attached_igw.id
                ))

        if attached:
            return True
        elif dry:
            print('Would attach the vpc and igw now.')
            return True
        else:
            try:
                print('Attaching igw {i} to vpc {v}.'.format(
                    v=vpc.id,
                    i=igw.id,
                ))
                vpc.attach_internet_gateway(InternetGatewayId=igw.id)
                return True
            except Exception as e:
                print('Could not attach igw {i} to vpc {v}. Reason just below.'.format(
                    v=vpc.id,
                    i=igw.id,
                ))
                traceback.print_exc()
                return False
    else:
        if dry:
            print('Would attach the vpc and igw now.')
            return True
        else:
            print('VPC or igw could not be created, can not bind them.')
            return False


def _detach_vpc_igw(vpc=None, igw=None):
    if (vpc and igw):
        # formating cut&paste
        f = {'v': vpc.id, 'i': igw.id}
        try:
            print('Detaching igw {i} from vpc {v}.'.format(**f))
            vpc.detach_internet_gateway(InternetGatewayId=igw.id)
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'Gateway.NotAttached':
                # does not really matter
                print('igw {i} was not attached to vpc {v}.'.format(**f))
                return True
            else:
                print('Could not detach igw {i} from vpc {v}. Reason just below.'.format(**f))
                traceback.print_exc()
                return False
        except Exception as e:
            print('Could not detach igw {i} from vpc {v}. Reason just below.'.format(**f))
            traceback.print_exc()
            return False

    else:
        print('VPC or igw not existing, cannot detach them.')
        return dry


def _add_ingress_rules():
    """
    Add ingress rules to the SG.
    """
    if dry:
        print("Would add security group ingress rules.")
        return True
    else:
        print("Adding security group ingress rules.")
        rules = INGRESS + [{
            'IpProtocol': '-1',
            'FromPort': 0,
            'ToPort': 0,
            'UserIdGroupPairs': [{'GroupId': _existing.sg.id}]
        }]

        for r in rules:
            success = True
            try:
                _existing.sg.authorize_ingress(IpPermissions=[r])
            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] != 'InvalidPermission.Duplicate':
                    success = False
                    print('Could add rule {r} to sg {s}. Reason just below.'.format({
                        'r': str(r),
                        's': _existing.sg.id
                    }))
                    traceback.print_exc()
            except Exception as e:
                success = False
                print('Could add rule {r} to sg {s}. Reason just below.'.format({
                    'r': str(r),
                    's': _existing.sg.id
                }))
                traceback.print_exc()
        return success


def _link_route_table():
    """
    A route table is created at the same time as the VPC.
    It needs to be tagged and associated to a subnet.
    """
    if dry:
        print("Would link the VPC and subnet in the route table.")
        return True

    vpc = _existing.vpc
    sub = _existing.sub
    igw = _existing.igw
    rt = [x for x in vpc.route_tables.all()]
    if len(rt) == 0:
        print('No route table have been created alongside the VPC. Not sure what to do here.')
    for r in rt:
        print('Linking sub {s} in route table {r}.'.format(
            s=sub.id,
            r=r.id
        ))
        r.associate_with_subnet(SubnetId=sub.id)
        _tag_resource(r)

        r.create_route(
            DestinationCidrBlock='0.0.0.0/0',
            GatewayId=igw.id,
            #InstanceId='string',
            #NetworkInterfaceId='string',
            #VpcPeeringConnectionId='string'
        )


def setup():
    """
    Load in (global) _existing existing resources.
    Setup definition call in (global) definitions.
    """
    global definitions

    # fully replace dict with AttrDict
    complete = AttrDict({})
    for k, v in definitions.items():
        data = AttrDict({})
        data.create  = v['create']  if 'create'  in v else 'create_' + v['stem']
        data.fetch   = v['fetch']   if 'fetch'   in v else v['stem'] + 's'
        data.destroy = v['destroy'] if 'destroy' in v else 'delete'
        complete[k] = data
    definitions = complete

    global _existing
    for r in definitions.keys():
        _existing[r] = _fetch(r)


def create():
    """
    Creation must be done in a certain order
    """

    # remember what is created or not
    vpc = False
    igw = False
    sg = False
    sub = False
    vm = False

    vpc = _create_resource('vpc', CidrBlock=args.cidr, InstanceTenancy='default')
    igw = _create_resource('igw')

    if vpc and igw:
        _attach_vpc_igw(vpc=_existing.vpc, igw=_existing.igw)
    else:
        print('Cannot attach an igw to a vpc as at least one of them could not be created.')

    if vpc:
        sg = _create_resource(
            'sg',
            GroupName=args.role,
            Description='SG for ' + args.role,
            VpcId=getattr(_existing.vpc, 'id', None)
        )
    else:
        print('Cannot create a sg as the vpc to attach it to could not be created.')

    if sg:
        _add_ingress_rules()
    else:
        print('Cannot create ingress rule as the sg could not be created.')

    if vpc:
        sub = _create_resource(
            'sub',
            VpcId=getattr(_existing.vpc, 'id', None),
            CidrBlock=args.cidr
        )
    else:
        print('Cannot create a subnet as the vpc to attach it to could not be created.')

    if vpc and sub:
        _link_route_table()
    else:
        print('Cannot link subnet and VPC in the route table as vpc or sub not created.')

    if sub and sg:
        vm = _create_resource(
            'vm',
            ImageId=args.ami,
            MinCount=1,
            MaxCount=1,
            KeyName=args.keypair,
            InstanceType=args.instance,
            # Note that there will be no internal name.
            # To get one, create first a DHCP options set and associate it with the VPC.
            NetworkInterfaces=[{
                'AssociatePublicIpAddress': True,
                'DeviceIndex': 0,  # needs to be 0 to get a public IP
                'SubnetId': getattr(_existing.sub, 'id', None),
                'Groups': [getattr(_existing.sg, 'id', None)],
            }],
        )
    else:
        print('Cannot create an instance as the sub or sg to use could not be created.')

    if vm:
        if not dry:
            print('Waiting for the instance to be up and running, usually done in less than 45 seconds...')
            _existing.vm.wait_until_running()
            _tag_volume()
            print('you can reach your VM at ' + _existing.vm.public_ip_address)

    else:
        print('VM not created for some reason.')


def destroy():
    """
    Destruction must be done in a specific order as well.
    """
    # instance first
    old_vm = _existing.vm
    _destroy_resource('vm')
    if not dry and old_vm is not None:
        # Wait for instance to be fully terminated before carrying on or we will have
        # dependency issues.
        print('Waiting for instance to be terminated before deleting other resources...')
        old_vm.wait_until_terminated()
        time.sleep(1)  # One would think that wait for terminated should be enough...

    _destroy_resource('disk')

    # detach before destroy
    _detach_vpc_igw(vpc=_existing.vpc, igw=_existing.igw)
    _destroy_resource('igw')

    # sg and sub before vpc
    _destroy_resource('sg')
    _destroy_resource('sub')

    _destroy_resource('vpc')


setup()

if args.action == 'up':
    create()
elif args.action == 'down':
    destroy()
else:
    print("""Oh, The grand old Duke of York,
He had ten thousand men;
He marched them up to the top of the hill,
And he marched them down again.

And when they were up, they were up,
And when they were down, they were down,
And when they were only half-way up,
They were neither up nor down.""")
