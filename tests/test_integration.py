import unittest
import os
import time
import yaml
from kubernetes import client, config
from kubernetes.client.rest import ApiException

class TestKubernetesIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Configurar el cliente de Kubernetes
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
            
        cls.api = client.CoreV1Api()
        cls.apps_api = client.AppsV1Api()
        cls.namespace = "banco"
        cls.spot_namespace = "banco-spot"
        
    def test_namespaces_exist(self):
        """Verifica que los namespaces necesarios existen."""
        namespaces = [ns.metadata.name for ns in self.api.list_namespace().items]
        self.assertIn(self.namespace, namespaces, f"El namespace {self.namespace} no existe")
        self.assertIn(self.spot_namespace, namespaces, f"El namespace {self.spot_namespace} no existe")
        
    def test_deployments_running(self):
        """Verifica que los deployments están en ejecución."""
        # Verificar deployment en el namespace regular
        deployments = self.apps_api.list_namespaced_deployment(namespace=self.namespace)
        self.assertGreater(len(deployments.items), 0, f"No hay deployments en el namespace {self.namespace}")
        
        # Verificar que al menos un pod está en estado Running
        pods = self.api.list_namespaced_pod(namespace=self.namespace)
        self.assertGreater(len(pods.items), 0, f"No hay pods en el namespace {self.namespace}")
        
        for pod in pods.items:
            self.assertEqual(pod.status.phase, "Running", 
                           f"El pod {pod.metadata.name} no está en estado Running")
    
    def test_spot_node_affinity(self):
        """Verifica que los pods en el namespace spot tienen la afinidad correcta."""
        pods = self.api.list_namespaced_pod(namespace=self.spot_namespace)
        for pod in pods.items:
            self.assertIn('node.kubernetes.io/lifecycle', pod.spec.node_selector,
                        f"El pod {pod.metadata.name} no tiene el selector de nodo spot")
            self.assertEqual(pod.spec.node_selector['node.kubernetes.io/lifecycle'], 'spot',
                           f"El pod {pod.metadata.name} no está programado en un nodo spot")

class TestLoadBalancerIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Configuración similar a la clase anterior
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
            
        cls.api = client.CoreV1Api()
        
    def test_service_endpoints(self):
        """Verifica que los servicios tienen endpoints."""
        services = self.api.list_namespaced_service(namespace="banco")
        for svc in services.items:
            endpoints = self.api.list_namespaced_endpoints(
                namespace="banco",
                field_selector=f"metadata.name={svc.metadata.name}"
            )
            self.assertGreater(len(endpoints.items), 0, 
                             f"El servicio {svc.metadata.name} no tiene endpoints")

if __name__ == '__main__':
    unittest.main()
