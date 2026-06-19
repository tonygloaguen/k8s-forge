# Debian and Ubuntu Installation

This guide documents a clean local installation of `k8s-forge` on a Debian or
Ubuntu virtual machine. `k8s-forge` does not install Docker, kind, or kubectl
automatically; install those tools separately before using cluster commands.

## System Prerequisites

Install Python virtual environment support and pip:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
```

On distributions where the default Python package is version-specific, install
the matching venv package instead, for example:

```bash
sudo apt install -y python3.13-venv python3-pip
```

You also need Git for cloning the repository:

```bash
sudo apt install -y git
```

For local Kubernetes workflows, install Docker, kind, and kubectl with your
normal system process. `k8s-forge doctor` can check whether they are available,
but it does not install them.

## Create the Project Directory

Some Debian VMs start without a `~/projets` directory. Create it before cloning:

```bash
mkdir -p ~/projets
cd ~/projets
```

If you see this error:

```text
bash: cd: /home/gloaguen/projets: No such file or directory
```

create the directory with `mkdir -p ~/projets` and retry.

## Clone the Repository

Clone `k8s-forge` into the project directory:

```bash
cd ~/projets
git clone <repository-url> k8s-forge
cd k8s-forge
```

If the repository was accidentally cloned in `~` because `~/projets` did not
exist, either move it:

```bash
mkdir -p ~/projets
mv ~/k8s-forge ~/projets/
cd ~/projets/k8s-forge
```

or remove the misplaced clone and clone again into `~/projets`.

## Create the Virtual Environment

Create a local virtual environment:

```bash
python3 -m venv .venv
```

If this fails with:

```text
ensurepip is not available
```

install the Debian/Ubuntu venv package, then recreate the virtual environment:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
rm -rf .venv
python3 -m venv .venv
```

For a version-specific Python install, use the matching package, for example
`python3.13-venv`.

## Activate the Virtual Environment

Activate the virtual environment:

```bash
source .venv/bin/activate
```

If activation fails with:

```text
.venv/bin/activate: No such file or directory
```

the virtual environment was not created. Recreate it:

```bash
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
```

On Debian, the `python` command may be absent outside a virtual environment:

```text
bash: python: command not found
```

Use `python3` outside the virtual environment. After activation, `python` should
point to `.venv/bin/python`.

## Install k8s-forge

Install the package in editable mode with development dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

If `k8s-forge` is not found:

```text
k8s-forge: command not found
```

make sure the virtual environment is active and the editable installation was
completed.

## Verify the CLI

Check that the command is available:

```bash
k8s-forge --help
```

Check the local Kubernetes tooling:

```bash
k8s-forge doctor
```

`doctor` reports Docker, kind, kubectl, the current kubectl context, and visible
nodes when available. Missing tools should be installed manually by the user.
