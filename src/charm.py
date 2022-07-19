#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""A Charm to functionally test the Prometheus Operator"""

import logging
import shutil
import stat
import subprocess
import textwrap

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus
from charms.operator_libs_linux.v0 import apt
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.operator_libs_linux.v1.systemd import (
    daemon_reload,
    service_restart,
    service_running,
    service_stop,
)
from pathlib import Path

logger = logging.getLogger(__name__)
TESTER_FILE="src/tester.py"
TESTER_PATH="/usr/local/bin/prometheus_tester"
SERVICE_NAME="prometheus-tester"
SERVICE_PATH=f"/etc/systemd/system/{SERVICE_NAME}.service"


class PrometheusTesterCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)
        self._name = "prometheus-tester"
        jobs = [
            {
                "scrape_interval": "1s",
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
        self.prometheus = MetricsEndpointProvider(self, jobs=jobs)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.stop, self._on_stop)

    def _on_install(self, _):
        packages = ["python3", "python3-pip"]
        self._install_packages(packages)

        pip_cmd = [
            "pip3",
            "install",
            "prometheus-client",
        ]
        result = subprocess.run(pip_cmd)
        try:
            result.check_returncode()
        except subprocess.CalledProcessError:
            logger.error("Could not install Prometheus client %s", result.stderr)

        shutil.copyfile(TESTER_FILE, TESTER_PATH)
        tester = Path(TESTER_PATH)
        tester.chmod(tester.stat().st_mode | stat.S_IEXEC)

    def _on_start(self, _):
        systemd_template = textwrap.dedent(
        f"""
                [Unit]
                Description=Prometheus Tester

                [Service]
                ExecStart={TESTER_PATH}

                [Install]
                WantedBy=multi-user.target
                """
        )

        with open(SERVICE_PATH, "w") as f:
            f.write(systemd_template)

        daemon_reload()
        service_restart(f"{SERVICE_NAME}.service")

        self.unit.status = ActiveStatus()

    def _on_stop(self, _):
        if service_running(SERVICE_NAME):
            service_stop(SERVICE_NAME)

    def _install_packages(self, packages):
        try:
            logger.debug("updating apt")
            apt.update()
        except subprocess.CalledProcessError as e:
            logger.exception("failed to update apt : %s", str(e))
            self.unit.status = BlockedStatus("could not updated apt")
            return

        try:
            logger.debug("installing packages: %s", ", ".join(packages))
            apt.add_package(packages)
        except apt.PackageNotFoundError:
            logger.error("an apt package was not found")
            self.unit.status = BlockedStatus("could not find package")
        except TypeError as e:
            logger.error("could not add packages: %s", str(e))
            self.unit.status = BlockedStatus("could not install packages")


if __name__ == "__main__":
    main(PrometheusTesterCharm)
