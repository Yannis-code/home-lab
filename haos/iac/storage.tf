resource "null_resource" "download_haos" {
  triggers = {
    image_url      = coalesce(local.selected_image_url, "")
    extracted_path = local.extracted_image
  }

  lifecycle {
    precondition {
      condition     = local.selected_image_url != null
      error_message = "Could not resolve Home Assistant OS image URL for host architecture."
    }
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -euo pipefail
      mkdir -p "${local.vm_storage_dir}"
      tmp="${local.extracted_image}.xz"
      curl -fL "${local.selected_image_url}" -o "$tmp"
      xz -dc "$tmp" > "${local.extracted_image}"
      rm -f "$tmp"
    EOT
  }
}

resource "libvirt_volume" "haos_disk" {
  depends_on = [null_resource.download_haos]

  name   = "${var.vm_name}.qcow2"
  pool   = var.storage_pool_name
  source = local.extracted_image
  format = "qcow2"
}

resource "null_resource" "resize_haos_disk" {
  depends_on = [libvirt_volume.haos_disk]

  triggers = {
    pool                 = var.storage_pool_name
    volume_name          = libvirt_volume.haos_disk.name
    requested_size_bytes = tostring(var.vm_disk_size_bytes)
    libvirt_uri          = var.libvirt_uri
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command = <<-EOT
      set -euo pipefail
      vol_path="$(virsh -c "${var.libvirt_uri}" vol-path --pool "${var.storage_pool_name}" "${libvirt_volume.haos_disk.name}")"
      current_size="$(qemu-img info --output=json "$vol_path" | sed -nE 's/^[[:space:]]*"virtual-size"[[:space:]]*:[[:space:]]*([0-9]+),?$/\1/p' | tail -n1)"
      requested_size="${var.vm_disk_size_bytes}"
      if [[ -z "$current_size" ]]; then
        echo "Unable to detect current volume size for $vol_path" >&2
        exit 1
      fi
      if (( requested_size > current_size )); then
        qemu-img resize "$vol_path" "$requested_size" >/dev/null
      fi
    EOT
  }
}
