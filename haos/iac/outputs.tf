output "vm_name" {
	description = "Created libvirt domain name"
	value       = libvirt_domain.haos.name
}

output "vm_ip" {
	description = "Management IP when NAT is enabled, otherwise LAN DHCP hint"
	value       = local.nat_network_enabled ? var.vm_ip : "DHCP on ${var.host_bridge_interface}"
}

output "ha_url" {
	description = "Preferred Home Assistant URL (management NAT when enabled)"
	value       = local.nat_network_enabled ? "http://${var.vm_ip}:8123" : "http://home-assistant.local:8123"
}

output "haos_image_url" {
	description = "Resolved Home Assistant OS image URL"
	value       = local.selected_image_url
}
