variable "libvirt_uri" {
	description = "Libvirt URI"
	type        = string
	default     = "qemu:///system"
}

variable "vm_name" {
	description = "Libvirt domain name"
	type        = string
	default     = "home-assistant"
}

variable "vm_description" {
	description = "Virtual machine description"
	type        = string
	default     = "Home Assistant OS"
}

variable "vm_memory_mb" {
	description = "Memory in MB"
	type        = number
	default     = 8192
}

variable "vm_vcpus" {
	description = "Number of vCPUs"
	type        = number
	default     = 2
}

variable "vm_disk_size_bytes" {
	description = "Desired disk virtual size in bytes"
	type        = number
	default     = 34359738368
}

variable "vm_mac" {
	description = "Static MAC for the VM"
	type        = string
	default     = "52:54:00:ab:cd:10"
}

variable "vm_ip" {
	description = "Reserved DHCP IP for NAT management network"
	type        = string
	default     = "192.168.150.10"
}

variable "enable_management_nat_interface" {
	description = "Attach a second NAT management NIC when using host-bridge mode"
	type        = bool
	default     = true
}

variable "management_vm_mac" {
	description = "MAC address used by the NAT management NIC"
	type        = string
	default     = "52:54:00:ab:cd:11"
}

variable "network_mode" {
	description = "VM network mode: host-bridge (macvtap on host interface) or nat (libvirt network)"
	type        = string
	default     = "host-bridge"

	validation {
		condition     = contains(["host-bridge", "nat"], var.network_mode)
		error_message = "network_mode must be host-bridge or nat."
	}
}

variable "host_bridge_interface" {
	description = "Host interface used by macvtap in host-bridge mode"
	type        = string
	default     = "eth0"
}

variable "network_name" {
	description = "Libvirt network name"
	type        = string
	default     = "ha-net"
}

variable "network_bridge" {
	description = "Bridge name used by libvirt NAT network"
	type        = string
	default     = "virbr-ha"
}

variable "network_domain" {
	description = "Optional DNS domain for the NAT network"
	type        = string
	default     = "ha.local"
}

variable "network_cidr" {
	description = "NAT network CIDR"
	type        = string
	default     = "192.168.150.0/24"
}

variable "storage_pool_name" {
	description = "Libvirt storage pool name"
	type        = string
	default     = "home-assistant"
}

variable "storage_pool_path" {
	description = "Storage pool path on host"
	type        = string
	default     = "/var/lib/libvirt/images/home-assistant"
}

variable "haos_release_api" {
	description = "GitHub API URL for latest Home Assistant OS release"
	type        = string
	default     = "https://api.github.com/repos/home-assistant/operating-system/releases/latest"
}

variable "domain_arch_override" {
	description = "Optional arch override (x86_64 or aarch64). Empty means auto-detect."
	type        = string
	default     = ""
}

variable "host_usb_passthrough_enabled" {
	description = "Enable host USB passthrough into the VM"
	type        = bool
	default     = true
}

variable "host_usb_bus_number" {
	description = "Host USB bus number for passthrough"
	type        = number
	default     = 1
}

variable "host_usb_device_number" {
	description = "Host USB device number for passthrough"
	type        = number
	default     = 2
}

variable "host_usb_vendor_id" {
	description = "USB vendor ID (hex with 0x prefix). If set with product ID, passthrough uses vendor/product matching."
	type        = string
	default     = "0x10c4"
}

variable "host_usb_product_id" {
	description = "USB product ID (hex with 0x prefix). If set with vendor ID, passthrough uses vendor/product matching."
	type        = string
	default     = "0xea60"
}
