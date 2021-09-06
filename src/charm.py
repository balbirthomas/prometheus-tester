#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""A Charm to functionally test the Prometheus Operator"""

import logging

from ops.charm import CharmBase
from ops.main import main
from ops.framework import StoredState
from ops.model import ActiveStatus, ModelError
from ops.pebble import ConnectionError
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider

logger = logging.getLogger(__name__)


class PrometheusTesterCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self._stored.set_default(monitoring_enabled=False)
        jobs = [
            {
                "static_configs": [
                    {
                        "targets": ["*:8000"],
                        "labels": {
                            "status": "testing"
                        }
                    }
                ]
            }
        ]
        self.prometheus = MetricsEndpointProvider(self, "metrics-endpoint",
                                          self.on.prometheus_tester_pebble_ready,
                                          jobs=jobs)
        self.framework.observe(self.on.prometheus_tester_pebble_ready,
                               self._on_prometheus_tester_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on.show_config_action, self._on_show_config_action)

    def _on_prometheus_tester_pebble_ready(self, event):
        container = event.workload
        layer = self._tester_pebble_layer()
        container.add_layer("tester", layer, combine=True)
        container.autostart()
        self.unit.status = ActiveStatus()

    def _on_config_changed(self, event):
        container = self.unit.get_container("prometheus-tester")
        try:
            service = container.get_service("tester")
        except ConnectionError:
            logger.info("Pebble API is not yet ready")
            return
        except ModelError:
            logger.info("tester service is not yet ready")
            return

        plan = container.get_plan()
        layer = self._tester_pebble_layer()
        if plan.service["tester"] != layer["services"]["tester"]:
            container.add_layer("tester", layer, combine=True)
            logger.debug("Added tester layer to container")

        if service.is_running():
            container.stop("tester")

        container.start("tester")
        logger.info("Restarted tester service")

        self.unit.status = ActiveStatus()

    def _on_update_status(self, event):
        rel = self.framework.model.get_relation("metrics-endpoint")
        if rel and not self._stored.monitoring_enabled:
            binding = self.model.get_binding(rel)
            bind_address = str(binding.network.bind_address)
            self._stored.monitoring_enabled = True
            logger.debug("NETWORK : %s", bind_address)

    def _on_show_config_action(self, event):
        event.set_results({"config": self.model.config})

    def _tester_pebble_layer(self):
        layer = {
            "summary": "prometheus tester",
            "description": "a test data generator for Prometheus",
            "services": {
                "tester": {
                    "override": "replace",
                    "summary": "tester service",
                    "command": "python /tester/tester.py",
                    "startup": "enabled"
                }
            }
        }
        return layer


if __name__ == "__main__":
    main(PrometheusTesterCharm)
