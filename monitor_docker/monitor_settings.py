from dataclasses import dataclass, field
from pyexpat import features

from dataclass_wizard import YAMLWizard
import logging
import sys


@dataclass
class MonitorSettings(YAMLWizard):
    at_ports: list[str] = field(default_factory=lambda: ["/dev/ttyUSB3", "/dev/ttyUSB6"])
    modem_names: list[str] = field(default_factory=lambda: ["modem1", "modem2"])

    zmq_port: int = field(default=2345)

    def __post_init__(self):
        if len(self.at_ports) != len(self.modem_names):
            logging.error("Number of At-Ports to use does not match number of modem names!")
            sys.exit(1)
