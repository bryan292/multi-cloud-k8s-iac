import importlib.util
import unittest


spec = importlib.util.spec_from_file_location("deploy", "scripts/deploy.py")
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class DeploymentStageTests(unittest.TestCase):
    def test_aws_stages(self):
        self.assertEqual(
            deploy.stages("aws"),
            ["aws/network", "aws/eks", "kubernetes", "kube_resources"],
        )

    def test_azure_stages(self):
        self.assertEqual(
            deploy.stages("azure"),
            ["azure/aks", "kubernetes", "kube_resources"],
        )
