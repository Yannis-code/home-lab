# home-lab

Command shortcuts are available at the repository root via `just`.

Cockpit shortcuts:

- `just cockpit` to list all cockpit commands
- `just cockpit::init-config` to initialize the config file
- `just cockpit::install` to install cockpit-machines
- `just cockpit::revert` to revert cockpit-machines
- `just cockpit::status` to check the status of cockpit-machines
- `just cockpit::check` to check the configuration and environment
- `just cockpit::doctor` to run a diagnostic check
- `just cockpit::logs` to view the logs of cockpit-machines
- `just cockpit::url` to get the URL for accessing cockpit-machines

HAOS shortcuts:

- `just haos` to list all haos commands
- `just haos::init` to initialize the Terraform configuration
- `just haos::plan` to show the Terraform plan
- `just haos::apply` to apply the Terraform configuration
- `just haos::destroy` to destroy the Terraform-managed infrastructure
- `just haos::output` to show the Terraform outputs
