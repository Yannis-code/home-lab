resource "libvirt_network" "haos" {
	count = local.nat_network_enabled ? 1 : 0

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
	count      = local.nat_network_enabled ? 1 : 0
	depends_on = [libvirt_network.haos]

	triggers = {
		network = var.network_name
		mac     = local.nat_interface_mac
		ip      = var.vm_ip
	}

	provisioner "local-exec" {
		interpreter = ["/bin/bash", "-c"]
		command = <<-EOT
			set -euo pipefail
			if ! virsh -c "${var.libvirt_uri}" net-dumpxml "${var.network_name}" | grep -Eq "<host[^>]*mac='${local.nat_interface_mac}'[^>]*ip='${var.vm_ip}'|<host[^>]*ip='${var.vm_ip}'[^>]*mac='${local.nat_interface_mac}'"; then
				virsh -c "${var.libvirt_uri}" net-update "${var.network_name}" add ip-dhcp-host "<host mac='${local.nat_interface_mac}' ip='${var.vm_ip}'/>" --live --config >/dev/null
			fi
		EOT
	}
}
