resource "libvirt_network" "haos" {
  name      = var.network_name
  mode      = "nat"
  bridge    = var.network_bridge
  domain    = var.network_domain
  addresses = [var.network_cidr]
  autostart = true

  dhcp {
    enabled = true
  }
}

resource "null_resource" "reserve_dhcp_ip" {
  depends_on = [libvirt_network.haos]

  triggers = {
    network = var.network_name
    mac     = var.vm_mac
    ip      = var.vm_ip
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command = <<-EOT
      set -euo pipefail
      if ! virsh -c "${var.libvirt_uri}" net-dumpxml "${var.network_name}" | grep -Eq "<host[^>]*mac='${var.vm_mac}'[^>]*ip='${var.vm_ip}'|<host[^>]*ip='${var.vm_ip}'[^>]*mac='${var.vm_mac}'"; then
        virsh -c "${var.libvirt_uri}" net-update "${var.network_name}" add ip-dhcp-host "<host mac='${var.vm_mac}' ip='${var.vm_ip}'/>" --live --config >/dev/null
      fi
    EOT
  }
}
