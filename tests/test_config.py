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
    def test_documented_azure_example(self):
        self.config["global"]["provider"] = "azure"
        m.validate(self.config)
    def test_platform_requires_immutable_commit(self):
        self.config["platform"]["commit"] = "main"
        with self.assertRaises(ValueError): m.validate(self.config)
    def test_world_open_aks_endpoint_is_rejected(self):
        self.config["global"]["provider"] = "azure"
        self.config["azure"]["network"]["api_server_authorized_ip_ranges"] = ["0.0.0.0/0"]
        with self.assertRaises(ValueError): m.validate(self.config)
    def test_azure_subnet_must_be_inside_vnet(self):
        self.config["global"]["provider"] = "azure"
        self.config["azure"]["network"]["subnet_cidr"] = "10.99.0.0/24"
        with self.assertRaises(ValueError): m.validate(self.config)
