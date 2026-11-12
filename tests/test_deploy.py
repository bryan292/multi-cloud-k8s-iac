import importlib.util
import unittest


from scripts import deploy as deploy



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
