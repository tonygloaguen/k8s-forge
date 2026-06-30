# Module 12 - Ansible Readiness

Module 12 prepares local Ansible examples for learning automation around a Kubernetes application. `k8s-forge` generates files and explanations, but it does not execute Ansible, open remote sessions, modify servers, contact the cluster, run Helm, run Terraform, create secrets, or generate login keys.

## Configuration

```yaml
ansible:
  enabled: true
  projectName: weatherapi
  inventory:
    type: local
    hosts:
      - localhost
  playbook:
    name: site.yml
  roles:
    enabled: true
  collections:
    kubernetes:
      enabled: true
    community:
      enabled: false
  examples:
    enabled: true
```

`projectName` can stay empty; `k8s-forge` then uses `app.name`.

## Render Ansible Readiness Files

```bash
k8s-forge ansible render app.yaml --output generated-ansible/
```

Generated layout:

```text
generated-ansible/
  README.md
  ansible.cfg
  inventory.ini
  site.yml
  group_vars/
    all.yml
  roles/
    README.md
```

## Concepts

Ansible is an automation and configuration management tool. An inventory lists targets, a playbook groups tasks, roles organize repeated automation, `group_vars` stores shared variables, and collections package reusable modules.

Terraform and Ansible are complementary. Terraform models infrastructure resources and state. Ansible is usually used for operational workflows and configuration tasks. In v0.15.0, both modules stay educational and local.

## Safety Model

The generated inventory is local only and uses `localhost`. The generated playbook contains review-only tasks. It does not install packages, manage services, run Docker tasks, run Kubernetes tasks, deploy Helm releases, or invoke Terraform.

`k8s-forge doctor` checks only whether `ansible` and optional `ansible-lint` are available by running version commands. Missing tools are non-blocking for readiness file generation.

AWX and Tower are useful orchestration platforms for larger Ansible workflows, but they are outside v0.15.0.

## Weatherapi Validation

```bash
k8s-forge check k8s-forge-app-ansible.yaml
k8s-forge render k8s-forge-app-ansible.yaml --output generated-k8s-forge-ansible/
k8s-forge ansible render k8s-forge-app-ansible.yaml --output generated-ansible/ --force
find generated-ansible -maxdepth 4 -type f -print
cat generated-ansible/README.md
cat generated-ansible/ansible.cfg
cat generated-ansible/inventory.ini
cat generated-ansible/site.yml
cat generated-ansible/group_vars/all.yml
cat generated-ansible/roles/README.md
k8s-forge doctor
```

## Limits

- No Ansible execution.
- No remote host connection.
- No production inventory.
- No server modification.
- No system package task.
- No active Kubernetes or Helm task.
- No Terraform execution.
- No AWX/Tower integration.
- No secrets or generated login keys.
