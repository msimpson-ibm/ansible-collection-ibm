#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = '''
---
name: classic_inventory
author:
    - IBM Cloud Ansible Team
version_added: "1.0.0"
requirements:
    - Python >= 3
short_description: Inventory source for IBM Cloud Classic Infrastructure servers
description:
    - This plugin builds a dynamic inventory of IBM Cloud Classic Infrastructure (formerly SoftLayer)
      virtual servers and bare metal servers using the SoftLayer Python API.
    - Inventory sources must be structured as *.classic.yml or *.classic.yaml.
    - Valid server properties that can be used for groups, keyed groups, filters, and composite variables
      include hostname, domain, datacenter, maxCpu, maxMemory, status, tags, and server_type.
    - Authentication requires IAAS_CLASSIC_USERNAME and IAAS_CLASSIC_API_KEY environment variables to be set.
extends_documentation_fragment:
    - inventory_cache
options:
    datacenters:
        description: List of IBM Cloud Classic datacenters to query (e.g., dal10, wdc07, lon02).
        type: list
        elements: str
        default: []
    filters:
        description:
            - A key value pair for filtering by various virtual server attributes.
              Only results matching the filter will be included in the inventory.
        type: dict
        default: {}
    groups:
        description: Add virtual server hosts to group based on Jinja2 conditionals.
        type: dict
        default: {}
    compose:
        description: Create variables based on virtual server attributes.
        type: dict
        default: {}
    exclude_ip:
        description: A list of virtual server IP addresses to exclude from the inventory.
        type: list
        elements: str
        default: []
    exclude_hostname:
        description: A list of virtual server hostnames to exclude from the inventory.
        type: list
        elements: str
        default: []
    exclude_id:
        description: A list of virtual server IDs to exclude from the inventory.
        type: list
        elements: str
        default: []
    exclude_tag:
        description: A list of virtual server tags to exclude from the inventory.
        type: list
        elements: str
        default: []
    keyed_groups:
        description: Add virtual server hosts to group based on the values of a variable.
        type: list
        elements: dict
        default: []
    use_public_ips:
        description:
            - Indicates whether to use public IP addresses instead of private IP addresses
              for virtual servers. If this value is True, all instances that do not have a
              public IP address will be filtered out when building the inventory.
        type: bool
        default: False
    fail_on_duplicate:
        description:
            - If True, the classic_inventory plugin will fail if it finds duplicate host names or IP addresses.
              This can occur when targeting different datacenters.
        type: bool
        default: True
    ansible_display_name:
        description: By default, the virtual server's hostname will be used as the name displayed by Ansible.
          Instead of the hostname, its IP address, FQDN, or ID may also be used.
        type: str
        choices: [hostname, ip, id, fqdn]
        default: "hostname"
    ansible_host_type:
        description: Determines if the IP Address or the virtual server hostname will be used as the "ansible_host"
          variable in playbooks.
        type: str
        choices: [hostname, ip]
        default: "ip"
'''

EXAMPLES = '''
# Minimal example targeting all datacenters
plugin: ibm.cloudcollection.classic_inventory

# Target specific datacenters
plugin: ibm.cloudcollection.classic_inventory
datacenters:
  - dal10
  - wdc07

# Filter for running instances only
plugin: ibm.cloudcollection.classic_inventory
datacenters:
  - dal10
  - wdc07
filters:
  status: RUNNING

# Generate inventory with public IPs and extra host variables
plugin: ibm.cloudcollection.classic_inventory
datacenters:
  - dal10
filters:
  status: RUNNING
compose:
  memory: maxMemory
  cores: maxCpu
  datacenter: datacenter.name
use_public_ips: True

# Generate inventory with grouping by datacenter
plugin: ibm.cloudcollection.classic_inventory
datacenters:
  - dal10
  - wdc07
keyed_groups:
  - prefix: datacenter
    key: datacenter.name
compose:
  datacenter: datacenter.name

# Exclude specific hosts by IP, hostname, or ID
plugin: ibm.cloudcollection.classic_inventory
datacenters:
  - dal10
exclude_ip:
  - 10.x.x.x
exclude_hostname:
  - test-server-1
exclude_id:
  - 12345678

# Create custom groups based on conditions
plugin: ibm.cloudcollection.classic_inventory
datacenters:
  - dal10
groups:
  production: "'prod' in hostname"
  development: "'dev' in hostname"
compose:
  environment: "'prod' if 'prod' in hostname else 'dev'"
'''

from ansible.plugins.inventory import BaseInventoryPlugin, Constructable, Cacheable
from ansible.module_utils.six import string_types, viewitems
from ansible.errors import AnsibleParserError
from ansible_collections.ibm.cloudcollection.plugins.module_utils.ibmcloud import ibmcloud_terraform
from ansible.config.manager import ensure_type
from ansible.template import Templar

from ansible.utils.display import Display
display = Display()

# Generic setting for log initializing and log rotation
import logging
LOG_FILENAME = "/tmp/ansible_classic.log"
logger = logging.getLogger(__name__)

TL_REQUIRED_PARAMETERS = [
]

# All top level parameter keys supported by Terraform module
TL_ALL_PARAMETERS = [
    'hostname',
    'domain',
    'most_recent',
]


def init_logger():
    logging.basicConfig(
        filename=LOG_FILENAME,
        format='[%(asctime)s] %(levelname)s: [%(funcName)s] %(message)s',
        level=logging.DEBUG)


class InventoryModule(BaseInventoryPlugin, Constructable, Cacheable):

    NAME = 'ibm.cloudcollection.classic_inventory'
    _cache = None

    def __init__(self):
        super().__init__()

        self.group_prefix = 'classic_'
        self.template_handle = None
        init_logger()

    def verify_file(self, path):
        """
        Verify inventory source is valid
        """
        if super().verify_file(path):
            logger.debug("Path: %s", path)
            if path.endswith(('.classic.yml', '.classic.yaml')):
                return True
            raise AnsibleParserError("Path is not valid. All IBM Cloud Classic inventory sources must have a suffix of .classic.yml or .classic.yaml.")

    def parse(self, inventory, loader, path, cache=True):
        """
        Parse inventory source
        """
        super(InventoryModule, self).parse(inventory, loader, path)

        self.load_cache_plugin()

        # Read the inventory YAML file
        self._configure(path)
        cache_key = self.get_cache_key(path)

        # cache may be True or False at this point to indicate if the inventory is being refreshed
        # get the user's cache option too to see if we should save the cache if it is changing
        user_cache_setting = self.get_option('cache')

        # read if the user has caching enabled and the cache isn't being refreshed
        attempt_to_read_cache = user_cache_setting and cache

        # update if the user has caching enabled and the cache is being refreshed;
        # update this value to True if the cache has expired below
        cache_needs_update = user_cache_setting and not cache

        # attempt to read the cache if inventory isn't being refreshed and the user has caching enabled
        if attempt_to_read_cache:
            try:
                vms = self._cache[cache_key]
            except KeyError:
                # This occurs if the cache_key is not in the cache or if the cache_key expired,
                # so the cache needs to be updated
                logger.debug("Cache needs to be updated: %s", cache_key)
                cache_needs_update = True

        if not attempt_to_read_cache or cache_needs_update:
            # parse the provided inventory source
            # submit the parsed data to the inventory object (add_host, set_variable, etc)
            self.template_handle = Templar(loader=loader)
            vms = self.get_virtual_servers()

        if cache_needs_update:
            self._cache[cache_key] = vms

        self._populate_from_vms(vms)

    def _populate_from_vms(self, vms):
        # Ensure that at least one VM was discovered
        if not vms:
            raise Exception("There are no Classic virtual servers found or no valid connections were established.")
        
        # Check to see if the list of VMs contains duplicates of the ansible display name or IP address.
        if self.fail_on_duplicate and len(vms) != len(set([v.get(self.ansible_display_name) for v in vms])):
            raise Exception(f"The fail_on_duplicate option is set and multiple hosts with the same {self.ansible_display_name} were found.")
        elif self.fail_on_duplicate and len(vms) != len(set([self.get_vm_ip(v) for v in vms])):
            raise Exception("The fail_on_duplicate option is set and multiple hosts with the same IP address were found.")

        for vm in vms:
            if self.vm_should_be_included(vm):
                # Lookup the IP address for the VM
                vm_ip = self.get_vm_ip(vm)
                vm_hostname = self.get_vm_hostname(vm)
                vm_id = self.get_vm_id(vm)
                vm_fqdn = self.get_vm_fqdn(vm)

                if self.ansible_host_type == "hostname":
                    hostname = vm_hostname
                else:
                    hostname = vm_ip

                if self.ansible_display_name == "hostname":
                    entry_name = vm_hostname
                elif self.ansible_display_name == "ip":
                    entry_name = vm_ip
                elif self.ansible_display_name == "fqdn":
                    entry_name = vm_fqdn
                else:
                    entry_name = vm_id

                self.inventory.add_host(entry_name)

                # Only add an ansible_host variable if it differs from the displayname in the inventory
                if hostname != entry_name:
                    self.inventory.set_variable(entry_name, "ansible_host", hostname)
                try:
                    self._set_composite_vars(self.compose, vm, entry_name, strict=True)
                    self._add_host_to_composed_groups(self.groups, vm, entry_name, strict=True)
                    self._add_host_to_keyed_groups(self.keyed_groups, vm, entry_name, strict=True)
                except Exception:
                    logger.debug("Attribute not found in the VM")
                    continue

    def get_virtual_servers(self):
        """
        Get all Classic virtual servers using SoftLayer Python API
        
        Note: The IBM Cloud Terraform provider's ibm_compute_vm_instance data source
        requires specific hostname and domain, so it cannot list all VMs.
        Instead, we use the SoftLayer Python API to get the list of all virtual servers.
        """
        import os
        
        vms = []
        
        try:
            # Import SoftLayer module
            try:
                import SoftLayer
            except ImportError:
                raise Exception(
                    "SoftLayer Python module is required for the classic_inventory plugin. "
                    "Please install it with: pip install softlayer"
                )
            
            # Get credentials from environment variables
            username = os.getenv('IAAS_CLASSIC_USERNAME')
            api_key = os.getenv('IAAS_CLASSIC_API_KEY')
            
            if not username or not api_key:
                raise Exception(
                    "Unable to authenticate with IBM Cloud Classic Infrastructure. "
                    "Please set IAAS_CLASSIC_USERNAME and IAAS_CLASSIC_API_KEY environment variables."
                )
            
            # Create SoftLayer client with explicit credentials
            # Note: SoftLayer.create_client_from_env() doesn't work reliably with env vars
            # so we create the client directly
            client = SoftLayer.Client(username=username, api_key=api_key)
            vs_manager = SoftLayer.VSManager(client)
            hardware_manager = SoftLayer.HardwareManager(client)
            
            # Define the object mask to get all needed properties for virtual servers
            vs_mask = "id,hostname,domain,fullyQualifiedDomainName,maxCpu,maxMemory," \
                      "primaryIpAddress,primaryBackendIpAddress,datacenter,powerState," \
                      "status,tagReferences"
            
            # Define the object mask for bare metal servers
            # Note: Use processorCount and memory for bare metal, not processorPhysicalCoreCount
            bm_mask = "id,hostname,domain,fullyQualifiedDomainName,processorCount," \
                      "memory,primaryIpAddress,primaryBackendIpAddress,datacenter," \
                      "hardwareStatus,tagReferences"
            
            logger.debug("Fetching virtual servers and bare metal servers from SoftLayer API")
            
            # Get all virtual servers
            vm_list = vs_manager.list_instances(mask=vs_mask)
            logger.debug(f"Retrieved {len(vm_list)} virtual servers from API")
            
            # Get all bare metal servers
            bm_list = hardware_manager.list_hardware(mask=bm_mask)
            logger.debug(f"Retrieved {len(bm_list)} bare metal servers from API")
            
            # Combine both lists
            vm_list.extend(bm_list)
            logger.debug(f"Total servers: {len(vm_list)}")
            
            # Filter by datacenter if specified
            if self.datacenters:
                filtered_vms = []
                for vm in vm_list:
                    datacenter_name = vm.get('datacenter', {}).get('name', '')
                    if datacenter_name in self.datacenters:
                        filtered_vms.append(vm)
                logger.debug(f"Filtered from {len(vm_list)} to {len(filtered_vms)} servers in specified datacenters: {self.datacenters}")
                vm_list = filtered_vms
            
            # Transform SoftLayer API output to match expected format
            transformed_vms = []
            for vm in vm_list:
                # Get datacenter name
                datacenter_name = vm.get('datacenter', {}).get('name', '')
                
                # Get tags
                tags = []
                if 'tagReferences' in vm and vm['tagReferences']:
                    tags = [tag.get('tag', {}).get('name', '') for tag in vm['tagReferences']]
                
                # Determine if this is a bare metal server or virtual server
                # Bare metal servers have 'processorCount' and 'memory' (as integer)
                # Virtual servers have 'maxCpu' and 'maxMemory'
                is_bare_metal = 'processorCount' in vm or ('memory' in vm and isinstance(vm.get('memory'), int))
                
                if is_bare_metal:
                    # Bare metal server
                    cpu_count = vm.get('processorCount', 0)
                    memory = vm.get('memory', 0)
                    # Determine status from hardwareStatus
                    hw_status = vm.get('hardwareStatus', {}).get('status', 'UNKNOWN')
                    status = 'RUNNING' if hw_status == 'ACTIVE' else hw_status
                    server_type = 'bare_metal'
                else:
                    # Virtual server
                    cpu_count = vm.get('maxCpu', 0)
                    memory = vm.get('maxMemory', 0)
                    # Determine status from powerState
                    power_state = vm.get('powerState', {}).get('keyName', 'UNKNOWN')
                    status = 'RUNNING' if power_state == 'RUNNING' else power_state
                    server_type = 'virtual'
                
                transformed_vm = {
                    'id': str(vm.get('id', '')),
                    'hostname': vm.get('hostname', ''),
                    'domain': vm.get('domain', ''),
                    'fullyQualifiedDomainName': vm.get('fullyQualifiedDomainName', ''),
                    'maxCpu': cpu_count,
                    'maxMemory': memory,
                    'ipv4_address': vm.get('primaryIpAddress', ''),
                    'ipv4_address_private': vm.get('primaryBackendIpAddress', ''),
                    'datacenter': {
                        'name': datacenter_name
                    },
                    'status': status,
                    'tags': tags,
                    'server_type': server_type  # Add server type for filtering/grouping
                }
                transformed_vms.append(transformed_vm)
            
            logger.debug(f"Transformed {len(transformed_vms)} virtual servers")
            return transformed_vms
            
        except Exception as e:
            logger.error(f"Error getting virtual servers: {e}")
            raise

    def _configure(self, path):
        config = self._read_config_data(path)

        args = dict(
            datacenters=dict(type="list", value=config.get("datacenters", [])),
            filters=dict(type="dict", value=config.get("filters", {})),
            groups=dict(type="dict", value=config.get("groups", {})),
            keyed_groups=dict(type="list", value=config.get("keyed_groups", [])),
            compose=dict(type="dict", value=config.get("compose", {})),
            exclude_ip=dict(type="list", value=config.get("exclude_ip", [])),
            exclude_hostname=dict(type="list", value=config.get("exclude_hostname", [])),
            exclude_id=dict(type="list", value=config.get("exclude_id", [])),
            exclude_tag=dict(type="list", value=config.get("exclude_tag", [])),
            use_public_ips=dict(type="bool", value=config.get("use_public_ips", False)),
            fail_on_duplicate=dict(type="bool", value=config.get("fail_on_duplicate", True)),
            ansible_display_name=dict(type="str", choices=["hostname", "ip", "id", "fqdn"], value=config.get("ansible_display_name", "hostname")),
            ansible_host_type=dict(type="str", choices=["hostname", "ip"], value=config.get("ansible_host_type", "ip")),
        )

        self.validate_and_set_args(args)

    def validate_and_set_args(self, args):
        for arg in args:
            if args[arg].get("required") and args[arg].get("value") is None:
                raise AnsibleParserError("%s is required value." % (arg))
            
            # Check type
            if args[arg]["type"] == 'str':
                type_checked_arg = ensure_type(
                    args[arg].get("value"), 'string')
                if type_checked_arg is not None and not isinstance(type_checked_arg, string_types):
                    raise AnsibleParserError("%s is expected to be a string, but got %s instead" % (
                        arg, type(type_checked_arg)))
                # Check for choices
                if "choices" in args[arg]:
                    if type_checked_arg not in args[arg]["choices"]:
                        raise AnsibleParserError("%s is not a valid option for %s. The following are valid options: %s" % (
                            type_checked_arg, arg, str(args[arg]["choices"])))
                setattr(self, arg, type_checked_arg)
            elif args[arg]["type"] == 'bool':
                if isinstance(args[arg].get("value"), bool):
                    setattr(self, arg, args[arg].get("value"))
                else:
                    raise AnsibleParserError("%s must be a boolean value. Current value is: %s" % (arg, args[arg].get("value")))
            elif args[arg]["type"] == 'list':
                if not isinstance(args[arg].get("value"), list):
                    raise AnsibleParserError("%s is currently %s and needs to be defined as a %s." % (arg, args[arg].get("value"), 'list'))
                setattr(self, arg, args[arg].get("value"))
            elif args[arg]["type"] == 'dict':
                if not isinstance(args[arg].get("value"), dict):
                    raise AnsibleParserError("%s is currently %s and needs to be defined as a %s." % (arg, args[arg].get("value"), 'dict'))
                setattr(self, arg, args[arg].get("value"))
            else:
                raise AnsibleParserError("%s is an unhandled type! This shouldn't happen." % (args[arg]["type"]))

            # Do not allow inventory generation to continue if an argument is set to None,
            # but also do not override a more type specific message that may have been raised.
            if args[arg].get("value") is None:
                raise AnsibleParserError("%s is an optional value, but cannot be None. Please specify a value or remove it from your inventory source." % (arg))

    def get_vm_ip(self, vm):
        """Get the IP address for a virtual server"""
        if self.use_public_ips:
            if "ipv4_address" in vm and vm.get("ipv4_address") is not None:
                return vm.get("ipv4_address")
            raise Exception("VM has no value for 'ipv4_address' (public IP)")
        else:
            if "ipv4_address_private" in vm and vm.get("ipv4_address_private") is not None:
                return vm.get("ipv4_address_private")
            raise Exception("VM has no value for 'ipv4_address_private' (private IP)")

    def get_vm_hostname(self, vm):
        """Get the hostname for a virtual server"""
        if "hostname" in vm and vm.get("hostname") is not None:
            return vm.get("hostname")
        raise Exception("VM has no value for 'hostname'")

    def get_vm_id(self, vm):
        """Get the ID for a virtual server"""
        if "id" in vm and vm.get("id") is not None:
            return str(vm.get("id"))
        raise Exception("VM has no value for 'id'")
    
    def get_vm_fqdn(self, vm):
        """Get the FQDN for a virtual server"""
        if "fullyQualifiedDomainName" in vm and vm.get("fullyQualifiedDomainName") is not None:
            return vm.get("fullyQualifiedDomainName")
        raise Exception("VM has no value for 'fullyQualifiedDomainName'")
    
    def get_vm_tags(self, vm):
        """Get the tags for a virtual server"""
        if "tags" in vm and vm.get("tags") is not None:
            return vm.get("tags")
        raise Exception("VM has no value for 'tags'")

    def is_vm_excluded(self, vm):
        """Check if a virtual server should be excluded"""
        # VM excluded due to IP address
        try:
            vm_ip = self.get_vm_ip(vm)
            if vm_ip in self.exclude_ip:
                return True
        except Exception:
            pass

        # VM excluded due to hostname
        try:
            vm_hostname = self.get_vm_hostname(vm)
            if vm_hostname in self.exclude_hostname:
                return True
        except Exception:
            pass

        # VM excluded due to ID
        try:
            vm_id = self.get_vm_id(vm)
            if vm_id in self.exclude_id:
                return True
        except Exception:
            pass

        # VM excluded due to a tag
        try:
            vm_tags = self.get_vm_tags(vm)
            if any(t in vm_tags for t in self.exclude_tag):
                return True
        except Exception:
            pass
        
        return False

    def matches_filters(self, vm):
        """Check if a virtual server matches the specified filters"""
        # Our filter should be a subset of our VM if the VM matches the filter items
        non_list_filters = {k: v for k, v in self.filters.items() if not isinstance(v, list)}
        list_filters = {k: v for k, v in self.filters.items() if isinstance(v, list)}

        if viewitems(non_list_filters) <= viewitems(vm):
            # For filters that are lists, check to see if each item in the filter
            # is present in the VM's properties.
            for k, v in list_filters.items():
                if not set(v).issubset(vm.get(k, [])):
                    return False
            return True

        return False

    def vm_should_be_included(self, vm):
        """Determine if a virtual server should be included in the inventory"""
        if self.matches_filters(vm) and not self.is_vm_excluded(vm):
            return True
        return False

# Made with Bob
