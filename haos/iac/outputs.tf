output "vm_name" {
  description = "Created libvirt domain name"
  value       = libvirt_domain.haos.name
}

output "vm_ip" {
  description = "Reserved Home Assistant IP"
  value       = var.vm_ip
}

output "ha_url" {
  description = "Home Assistant URL"
  value       = "http://${var.vm_ip}:8123"
}

output "haos_image_url" {
  description = "Resolved Home Assistant OS image URL"
  value       = local.selected_image_url
}
