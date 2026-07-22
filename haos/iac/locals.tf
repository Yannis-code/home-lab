locals {
  normalized_host_arch = (
    var.domain_arch_override != ""
    ? var.domain_arch_override
    : (
      contains(["aarch64", "arm64"], data.external.host.result.arch)
      ? "aarch64"
      : "x86_64"
    )
  )

  release = jsondecode(data.http.haos_release.response_body)

  image_name_pattern = (
    local.normalized_host_arch == "aarch64"
    ? "haos_generic-aarch64-[0-9.]+\\.qcow2\\.xz$"
    : "haos_ova-[0-9.]+\\.qcow2\\.xz$"
  )

  image_urls = [
    for asset in local.release.assets : asset.browser_download_url
    if length(regexall(local.image_name_pattern, asset.name)) > 0
  ]

  selected_image_url = try(local.image_urls[0], null)
  vm_storage_dir     = "${var.storage_pool_path}/${var.vm_name}"
  extracted_image    = "${local.vm_storage_dir}/haos-${local.normalized_host_arch}.qcow2"
  domain_xslt = templatefile("${path.module}/../config/templates/domain-transform.xsl.tftpl", {
    use_no_secboot               = local.normalized_host_arch == "aarch64"
    host_usb_passthrough_enabled = var.host_usb_passthrough_enabled
    host_usb_use_vendor_product  = var.host_usb_vendor_id != "" && var.host_usb_product_id != ""
    host_usb_bus_number          = var.host_usb_bus_number
    host_usb_device_number       = var.host_usb_device_number
    host_usb_vendor_id           = var.host_usb_vendor_id
    host_usb_product_id          = var.host_usb_product_id
  })
}
