# HAOS KVM migration vers OpenTofu/Terraform

Ce dossier contient une migration progressive vers une infra declarative pour libvirt/KVM.

## Prerequis

- OpenTofu (`tofu`) ou Terraform (`terraform`)
- libvirt + KVM operationnels
- Outils systeme: `curl`, `xz`, `virsh`
- Droits pour `qemu:///system` (groupe libvirt ou sudo)

## Structure

- `versions.tf`: version OpenTofu/Terraform et providers
- `backend.tf`: backend local (state dans `../state/`)
- `provider.tf`: provider libvirt
- `data.tf`: data sources (arch hote et release HAOS)
- `locals.tf`: calculs locaux (image, xslt, arch)
- `network.tf`: reseau libvirt et reservation DHCP
- `storage.tf`: download image, volume, resize disque
- `vm.tf`: definition de la VM
- `variables.tf`: variables de configuration
- `outputs.tf`: sorties utiles (IP, URL)
- `import-existing.sh`: import de ressources deja existantes
- `../config/terraform.tfvars.example`: exemple de variables
- `../config/templates/`: templates XSL/TPL
- `../state/`: fichiers de state local

## Demarrage rapide

1. Copier les variables:

```bash
cd haos/iac
cp ../config/terraform.tfvars.example ../config/terraform.tfvars
```

2. Initialiser:

```bash
tofu init
# ou: terraform init
```

3. Si une VM existe deja (cree par le script shell), importer l'existant:

```bash
./import-existing.sh
```

4. Verifier les changements:

```bash
tofu plan
# ou: terraform plan
```

5. Appliquer:

```bash
tofu apply
# ou: terraform apply
```

## Justfile

Depuis `haos/`:

- `just tf-init`
- `just tf-import`
- `just tf-plan`
- `just tf-apply`
- `just tf-output`
- `just tf-destroy`

## Notes

- L'image HAOS est resolue automatiquement depuis la release GitHub la plus recente selon l'architecture hote.
- La reservation DHCP est appliquee via `virsh net-update` pour garantir MAC/IP.
- Taille disque: utilise `vm_disk_size_bytes`.
- En aarch64, un override XSLT force AAVMF no-secboot pour eviter un boot UEFI bloque sans bail DHCP.
- Le passthrough USB hote est configurable via `host_usb_passthrough_enabled`, `host_usb_bus_number`, `host_usb_device_number`.
