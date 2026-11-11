import copy
import importlib.util
import unittest
from pathlib import Path
import yaml
spec = importlib.util.spec_from_file_location("preflight", "scripts/preflight.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.config = yaml.safe_load(Path("config.yaml_example").read_text())
    def test_documented_example(self):
        m.validate(self.config)
    def test_world_open_endpoint_is_rejected(self):
        for cidr in ["0.0.0.0/0", "::/0"]:
            with self.subTest(cidr=cidr), self.assertRaises(ValueError):
                c = copy.deepcopy(self.config)
                c["eks"]["admin_cidrs"] = [cidr]
                m.validate(c)
    def test_invalid_scaling_is_rejected(self):
        self.config["eks"]["node_scaling"]["desired"] = 99
        with self.assertRaises(ValueError): m.validate(self.config)
    def test_autoscaler_upgrade_requires_compatible_pin(self):
        self.config["global"]["kubernetes_version"] = "1.36"
        with self.assertRaises(ValueError): m.validate(self.config)
    def test_missing_administrator_is_rejected(self):
        self.config["eks"]["admin_principal_arns"] = []
        with self.assertRaises(ValueError): m.validate(self.config)
