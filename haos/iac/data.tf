data "external" "host" {
  program = [
    "bash",
    "-lc",
    "printf '{\"arch\":\"%s\"}' \"$(uname -m)\""
  ]
}

data "http" "haos_release" {
  url = var.haos_release_api

  request_headers = {
    Accept = "application/vnd.github+json"
  }
}
