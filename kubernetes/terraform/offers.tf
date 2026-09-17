# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

resource "juju_offer" "mysql_database_offer" {
  # create cross model offer of server endpoint, only if router is not deployed as part of this model
  count = var.router_enabled ? 0 : 1

  model_uuid = var.model
  name       = "mysql-database-offer"

  application_name = module.mysql_server.app_name
  endpoints = [
    module.mysql_server.provides.database,
  ]
}
