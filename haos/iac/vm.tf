resource "libvirt_domain" "haos" {
  depends_on = [null_resource.reserve_dhcp_ip, null_resource.resize_haos_disk]

  name        = var.vm_name
  description = var.vm_description
  arch        = local.normalized_host_arch
  firmware    = "efi"
  memory      = var.vm_memory_mb
  vcpu        = var.vm_vcpus
  autostart   = true

#   lifecycle {
#     ignore_changes = [
#       cmdline,
#       emulator,
#       machine,
#       firmware,
#       nvram,
#       graphics[0].websocket,
#       network_interface[0].addresses,
#       network_interface[0].hostname,
#       network_interface[0].mac,
#       network_interface[0].network_name,
#     ]
#   }

  dynamic "xml" {
    for_each = (local.normalized_host_arch == "aarch64" || var.host_usb_passthrough_enabled) ? [1] : []
    content {
      xslt = local.domain_xslt
    }
  }

  cpu {
    mode = "host-passthrough"
  }

  disk {
    volume_id = libvirt_volume.haos_disk.id
  }

  network_interface {
    network_id     = libvirt_network.haos.id
    mac            = var.vm_mac
    wait_for_lease = false
  }

  console {
    type        = "pty"
    target_type = "serial"
    target_port = "0"
  }

  graphics {
    type        = "spice"
    listen_type = "none"
    autoport    = true
  }
}
