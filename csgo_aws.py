#!/usr/bin/env python
#
# Troposphere script to create a CS:GO Server on AWS
# Components created by this script

from troposphere import Base64, FindInMap, GetAtt, Join, Output
from troposphere import Parameter, Ref, Tags, Template
from troposphere.autoscaling import Metadata
from troposphere.ec2 import Route, VPCGatewayAttachment, \
    SubnetRouteTableAssociation, Subnet, RouteTable, VPC, \
    NetworkInterfaceProperty, EIP, Instance, InternetGateway, \
    SecurityGroupRule, SecurityGroup
from troposphere.policies import CreationPolicy, ResourceSignal
from troposphere.cloudformation import Init, InitFile, InitFiles, \
    InitConfig, InitService, InitServices
import yaml
import argparse

# Parsing Arguments
parser = argparse.ArgumentParser(description='Create CS:GO CF Template.')
parser.add_argument('-c',
                    metavar='config_file',
                    nargs=1,
                    type=argparse.FileType('r'),
                    help='Config file',
                    required=True)
parser.add_argument('-o',
                    metavar='output_file',
                    nargs=1,
                    type=argparse.FileType('w'),
                    help='Output file',
                    default="csgo_cf.template")
args = parser.parse_args()

if not any([args.c, args.o]):
    args.print_usage()
    quit()

# Parsing config file
with args.c[0] as ymlfile:
    config_file = yaml.load(ymlfile)

# Open outputfile
output_file = args.o

# General parameters
t = Template()
t.add_version('2010-09-09')
t.add_description(config_file['cf']['descr'])

# EC2 Parameters
keyname_param = t.add_parameter(
    Parameter(
        'KeyName',
        Description='Instance KeyName',
        Type='String',
        Default=config_file['ec2']['key']
    ))

instanceType_param = t.add_parameter(Parameter(
    'InstanceType',
    Type='String',
    Description=config_file['ec2']['descr'],
    Default='t2.micro',
    AllowedValues=[
        't2.micro', 't2.small', 't2.medium',
        'm3.medium', 'm3.large', 'm3.xlarge',
        'm4.medium', 'm4.large', 'm4.xlarge',
    ],
    ConstraintDescription='must be a valid EC2 instance type.',
))

t.add_mapping('AWSInstanceType2Arch', {
    't2.micro': {'Arch': 'HVM64'},
    't2.small': {'Arch': 'HVM64'},
    't2.medium': {'Arch': 'HVM64'},
    'm3.medium': {'Arch': 'HVM64'},
    'm3.large': {'Arch': 'HVM64'},
    'm3.xlarge': {'Arch': 'HVM64'},
    'm4.medium': {'Arch': 'HVM64'},
    'm4.large': {'Arch': 'HVM64'},
    'm4.xlarge': {'Arch': 'HVM64'},
})

t.add_mapping('AWSRegionArch2AMI', {
    'eu-central-1': {'HVM64': config_file['ec2']['ami']},
})

ref_stack_id = Ref('AWS::StackId')
ref_region = Ref('AWS::Region')
ref_stack_name = Ref('AWS::StackName')

# VPC Parameters
VPC = t.add_resource(
    VPC(
        config_file['vpc']['name'],
        CidrBlock=config_file['vpc']['cidr'],
        Tags=Tags(
            Application=ref_stack_id)))

subnet = t.add_resource(
    Subnet(
        config_file['subnet']['name'],
        CidrBlock=config_file['subnet']['cidr'],
        VpcId=Ref(VPC),
        Tags=Tags(
            Application=ref_stack_id)))

internetGateway = t.add_resource(
    InternetGateway(
        config_file['igw']['name'],
        Tags=Tags(
            Application=ref_stack_id)))

gatewayAttachment = t.add_resource(
    VPCGatewayAttachment(
        'AttachGateway',
        VpcId=Ref(VPC),
        InternetGatewayId=Ref(internetGateway)))

routeTable = t.add_resource(
    RouteTable(
        config_file['rtable']['name'],
        VpcId=Ref(VPC),
        Tags=Tags(
            Application=ref_stack_id)))

route = t.add_resource(
    Route(
        config_file['route']['name'],
        DependsOn='AttachGateway',
        GatewayId=Ref(config_file['igw']['name']),
        DestinationCidrBlock='0.0.0.0/0',
        RouteTableId=Ref(routeTable),
    ))

subnetRouteTableAssociation = t.add_resource(
    SubnetRouteTableAssociation(
        'SubnetRouteTableAssociation',
        SubnetId=Ref(subnet),
        RouteTableId=Ref(routeTable),
    ))

# Security Parameters
sshlocation_param = t.add_parameter(
    Parameter(
        'SSHLocation',
        Description=' The IP address range that can be used to SSH to the EC2 \
instances',
        Type='String',
        MinLength='9',
        MaxLength='18',
        Default='0.0.0.0/0',
        AllowedPattern="(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})/(\d{1,2})",
        ConstraintDescription=(
            "must be a valid IP CIDR range of the form x.x.x.x/x."),
    ))

instanceSecurityGroup = t.add_resource(
    SecurityGroup(
        config_file['sg']['name'],
        GroupDescription='Enable SSH access via port 22',
        SecurityGroupIngress=[
            SecurityGroupRule(
                IpProtocol='tcp',
                FromPort='22',
                ToPort='22',
                CidrIp=Ref(sshlocation_param)),
            SecurityGroupRule(
                IpProtocol='tcp',
                FromPort='80',
                ToPort='80',
                CidrIp='0.0.0.0/0')],
        VpcId=Ref(VPC),
    ))

# Instance Parameters
customUserData = """#!/bin/bash
INSTANCEID=`/usr/bin/curl -s http://169.254.169.254/latest/meta-data/instance-id`
IPV4=`/usr/bin/curl -s http://169.254.169.254/latest/meta-data/local-ipv4`

cat<<EOF > /test
test
#EOF
"""

# customUserData = customUserData.replace("AZ1",az[0])
# customUserData = customUserData.replace("AZ2",az[1])
# customUserData = customUserData.replace("hostnamekey",natAG_hostname)
# customUserData = customUserData.replace("s3commonbucket",config['S3_COMMON'])

instance = t.add_resource(
    Instance(
        config_file['ec2']['name'],
        ImageId=FindInMap(
            'AWSRegionArch2AMI',
            config_file['vpc']['region'],
            FindInMap(
                'AWSInstanceType2Arch',
                config_file['ec2']['type'],
                'Arch')),
        InstanceType=config_file['ec2']['type'],
        KeyName=Ref(keyname_param),
        NetworkInterfaces=[
            NetworkInterfaceProperty(
                GroupSet=[
                    Ref(instanceSecurityGroup)],
                AssociatePublicIpAddress='true',
                DeviceIndex='0',
                DeleteOnTermination='true',
                SubnetId=Ref(subnet))],
        CreationPolicy=CreationPolicy(
            ResourceSignal=ResourceSignal(
                Timeout='PT15M')),
        Tags=Tags(
            Application=ref_stack_id),
    ))

ipAddress = t.add_resource(
    EIP('IPAddress',
        DependsOn='AttachGateway',
        Domain='vpc',
        InstanceId=Ref(instance)
        ))

# WRITE TEMPLATE
json = t.to_json()
output_file.write(json)
