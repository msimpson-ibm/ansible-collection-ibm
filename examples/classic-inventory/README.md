# IBM Cloud Classic Infrastructure Inventory Plugin

This directory contains examples for using the `classic_inventory` dynamic inventory plugin for IBM Cloud Classic Infrastructure (formerly SoftLayer).

## Overview

The `classic_inventory` plugin allows you to dynamically generate an Ansible inventory from your IBM Cloud Classic Infrastructure virtual server instances. This is useful for managing infrastructure at scale without maintaining static inventory files.

## Prerequisites

1. **IBM Cloud Account**: You need an active IBM Cloud account with Classic Infrastructure access
2. **API Credentials**: Set up authentication using one of these methods:
   - **Option 1 (Recommended)**: Set `IC_API_KEY` environment variable with your IBM Cloud API key
   - **Option 2**: Set both `IAAS_CLASSIC_USERNAME` and `IAAS_CLASSIC_API_KEY` environment variables

## Authentication Setup

### Using IBM Cloud API Key (Recommended)

```bash
export IC_API_KEY="your-ibm-cloud-api-key"
```

### Using Classic Infrastructure Credentials

```bash
export IAAS_CLASSIC_USERNAME="your-classic-username"
export IAAS_CLASSIC_API_KEY="your-classic-api-key"
```

## Basic Usage

### 1. Create an Inventory File

Create a file named `inventory.classic.yml`:

```yaml
plugin: ibm.cloudcollection.classic_inventory
```

### 2. Test the Inventory

```bash
ansible-inventory -i inventory.classic.yml --list
```

### 3. Use with Ansible Playbooks

```bash
ansible-playbook -i inventory.classic.yml your-playbook.yml
```

## Configuration Examples

### Example 1: Target Specific Datacenters

```yaml
plugin: ibm.cloudcollection.classic_inventory
datacenters:
  - dal10
  - wdc07
  - lon02
```

### Example 2: Filter Running Instances

```yaml
plugin: ibm.cloudcollection.classic_inventory
datacenters:
  - dal10
filters:
  status: RUNNING
```

### Example 3: Use Public IPs

```yaml
plugin: ibm.cloudcollection.classic_inventory
use_public_ips: True
```

### Example 4: Add Custom Host Variables

```yaml
plugin: ibm.cloudcollection.classic_inventory
compose:
  memory: maxMemory
  cores: maxCpu
  datacenter_name: datacenter.name
  os_description: operatingSystem.softwareLicense.softwareDescription.longDescription
```

### Example 5: Group by Datacenter

```yaml
plugin: ibm.cloudcollection.classic_inventory
keyed_groups:
  - prefix: datacenter
    key: datacenter.name
compose:
  datacenter_name: datacenter.name
```

### Example 6: Create Conditional Groups

```yaml
plugin: ibm.cloudcollection.classic_inventory
groups:
  production: "'prod' in hostname"
  development: "'dev' in hostname"
  database: "'db' in hostname"
  webserver: "'web' in hostname"
```

### Example 7: Exclude Specific Hosts

```yaml
plugin: ibm.cloudcollection.classic_inventory
exclude_ip:
  - 10.x.x.x
  - 11.x.x.x
exclude_hostname:
  - test-server-1
  - maintenance-server
exclude_id:
  - 12345678
```

### Example 8: Complete Configuration

```yaml
plugin: ibm.cloudcollection.classic_inventory

# Target specific datacenters
datacenters:
  - dal10
  - wdc07

# Filter for running instances
filters:
  status: RUNNING

# Use public IPs
use_public_ips: False

# Add custom variables
compose:
  memory: maxMemory
  cores: maxCpu
  datacenter_name: datacenter.name
  domain: domain
  fqdn: fullyQualifiedDomainName

# Group by datacenter and OS
keyed_groups:
  - prefix: datacenter
    key: datacenter.name
  - prefix: os
    key: operatingSystem.softwareLicense.softwareDescription.name

# Create conditional groups
groups:
  production: "'prod' in hostname"
  development: "'dev' in hostname"

# Exclude specific hosts
exclude_hostname:
  - test-server

# Display configuration
ansible_display_name: hostname
ansible_host_type: ip

# Enable caching
cache: True
cache_plugin: jsonfile
cache_timeout: 3600
cache_connection: /tmp/ansible_classic_inventory_cache
```

## Available Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `datacenters` | list | [] | List of datacenters to query (e.g., dal10, wdc07) |
| `filters` | dict | {} | Key-value pairs for filtering virtual servers |
| `groups` | dict | {} | Jinja2 conditionals for creating groups |
| `compose` | dict | {} | Create custom host variables |
| `keyed_groups` | list | [] | Group hosts by variable values |
| `exclude_ip` | list | [] | IP addresses to exclude |
| `exclude_hostname` | list | [] | Hostnames to exclude |
| `exclude_id` | list | [] | Instance IDs to exclude |
| `exclude_tag` | list | [] | Tags to exclude |
| `use_public_ips` | bool | False | Use public IPs instead of private |
| `fail_on_duplicate` | bool | True | Fail if duplicate names/IPs found |
| `ansible_display_name` | str | hostname | Display name format (hostname/ip/id) |
| `ansible_host_type` | str | ip | ansible_host value (hostname/ip) |

## Common Virtual Server Properties

You can use these properties in filters, groups, compose, and keyed_groups:

- `hostname` - Virtual server hostname
- `domain` - Domain name
- `fullyQualifiedDomainName` - Complete FQDN
- `id` - Instance ID
- `ipv4_address` - Public IPv4 address
- `ipv4_address_private` - Private IPv4 address
- `maxMemory` - Memory in MB
- `maxCpu` - Number of CPU cores
- `datacenter.name` - Datacenter name (e.g., dal10)
- `status` - Instance status (e.g., RUNNING)
- `operatingSystem.softwareLicense.softwareDescription.name` - OS name
- `tags` - List of tags

## Caching

Enable caching to improve performance:

```yaml
plugin: ibm.cloudcollection.classic_inventory
cache: True
cache_plugin: jsonfile
cache_timeout: 3600
cache_connection: /tmp/ansible_classic_inventory_cache
```

To refresh the cache:

```bash
ansible-inventory -i inventory.classic.yml --list --refresh
```

## Troubleshooting

### No hosts found

1. Verify your API credentials are set correctly
2. Check that you have Classic Infrastructure virtual servers
3. Verify datacenter names if specified
4. Check filter criteria

### Authentication errors

1. Ensure `IC_API_KEY` or both `IAAS_CLASSIC_USERNAME` and `IAAS_CLASSIC_API_KEY` are set
2. Verify credentials have proper permissions
3. Check that credentials haven't expired

### Duplicate host errors

If you get duplicate host errors:

1. Set `fail_on_duplicate: False` to allow duplicates
2. Use `ansible_display_name: id` to ensure unique names
3. Use exclude options to filter out duplicates

## Example Playbook

```yaml
---
- name: Manage Classic Infrastructure Servers
  hosts: all
  gather_facts: yes
  tasks:
    - name: Display server information
      debug:
        msg: |
          Hostname: {{ inventory_hostname }}
          IP: {{ ansible_host }}
          Memory: {{ memory | default('N/A') }}
          Cores: {{ cores | default('N/A') }}
          Datacenter: {{ datacenter_name | default('N/A') }}

    - name: Ping all servers
      ping:

    - name: Update packages (Ubuntu/Debian)
      apt:
        update_cache: yes
        upgrade: dist
      when: ansible_os_family == "Debian"
      become: yes
```

Run with:

```bash
ansible-playbook -i inventory.classic.yml playbook.yml
```

## Additional Resources

- [IBM Cloud Classic Infrastructure Documentation](https://cloud.ibm.com/docs/cloud-infrastructure)
- [Ansible Dynamic Inventory](https://docs.ansible.com/ansible/latest/user_guide/intro_dynamic_inventory.html)
- [IBM Cloud Ansible Collection](https://github.com/IBM-Cloud/ansible-collection-ibm)