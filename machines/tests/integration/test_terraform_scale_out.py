#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Terraform integration test: scale out while changing configuration."""

import logging
import shutil
from typing import Any, Dict

import jubilant
import pytest

from .helpers import (
    TF_BINARY,
    Scenario,
    _apps_match,
    _offers_match,
    _statuses_match,
    clean_terraform_state,
    get_common_vars,
    terraform_apply,
    terraform_init,
)

logger = logging.getLogger(__name__)

MYSQL_APP = "mysql"

INITIAL_UNITS = 1
SCALED_UNITS = 3

# Configuration changed in the same apply that scales the cluster out
SCALE_OUT_CONFIG = {
    "binlog-retention-days": "3",
    "max-connections": "200",
    "logs-audit-policy": "all",
}

# Router is disabled to keep the focus on the MySQL Server application
SCENARIO = Scenario(
    name="scale_out_config",
    vars={"router_enabled": "false"},
    active_apps=[MYSQL_APP, "s3-integrator"],
    absent_apps=["mysql-router"],
    offers={"mysql-database-offer": MYSQL_APP},
)


@pytest.fixture(scope="module", autouse=True)
def _terraform_setup() -> None:
    """Skip if the terraform binary is missing, then clean stale state."""
    if not shutil.which(TF_BINARY):
        pytest.skip(f"{TF_BINARY} not found on PATH")
    clean_terraform_state()


@pytest.fixture(scope="module", autouse=True)
def _terraform_init(_terraform_setup) -> None:
    """Run terraform init once before the first apply."""
    terraform_init()


def _build_vars(juju: jubilant.Juju, units: int, config: Dict[str, str]) -> Dict[str, Any]:
    """Build the terraform vars, merging the MySQL Server overrides into the common ones."""
    terraform_vars = {**get_common_vars(juju), **SCENARIO.vars}
    terraform_vars["mysql_server"] = {
        **terraform_vars.get("mysql_server", {}),
        "units": units,
        "config": config,
    }
    return terraform_vars


def _settled(status: jubilant.Status, units: int) -> bool:
    """Check that the model matches the scenario and the MySQL app has settled."""
    return (
        _apps_match(status, SCENARIO)
        and _statuses_match(status, SCENARIO)
        and _offers_match(status, SCENARIO)
        and len(status.apps[MYSQL_APP].units) == units
        and jubilant.all_active(status, MYSQL_APP)
        and jubilant.all_agents_idle(status, MYSQL_APP)
    )


def test_deploy_single_unit(juju: jubilant.Juju) -> None:
    """Deploy a single unit MySQL cluster and wait for it to settle."""
    logger.info(f"Deploying terraform module with {INITIAL_UNITS} MySQL unit")
    terraform_apply(_build_vars(juju, units=INITIAL_UNITS, config={}))

    juju.wait(
        lambda status: _settled(status, INITIAL_UNITS),
        error=jubilant.any_error,
        successes=5,
    )


def test_scale_out_with_config_change(juju: jubilant.Juju) -> None:
    """Scale out the MySQL cluster while changing its configuration."""
    logger.info(f"Scaling out to {SCALED_UNITS} units while changing config {SCALE_OUT_CONFIG}")
    terraform_apply(_build_vars(juju, units=SCALED_UNITS, config=SCALE_OUT_CONFIG))

    juju.wait(
        lambda status: _settled(status, SCALED_UNITS),
        error=jubilant.any_error,
        successes=5,
    )

    app_config = juju.config(MYSQL_APP)
    for key, value in SCALE_OUT_CONFIG.items():
        assert str(app_config[key]) == value, f"Config {key} not applied"
