import os
import time
from kubernetes import client, config
import requests
from collections import defaultdict

class LoadBalancer:
    def __init__(self):
        self.api = client.CoreV1Api()
        self.apps_api = client.AppsV1Api()
        self.prometheus_url = os.getenv("PROMETHEUS_URL", "http://prometheus-kube-prometheus-prometheus.monitoring:9090")
        
    def get_node_metrics(self):
        """Obtiene métricas de uso de CPU y memoria de los nodos desde Prometheus."""
        try:
            # Consulta para obtener el uso de CPU (1m de promedio)
            cpu_query = '100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100'
            # Consulta para obtener el uso de memoria
            mem_query = '100 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100'
            
            metrics = {}
            
            for metric_name, query in [('cpu', cpu_query), ('memory', mem_query)]:
                response = requests.get(
                    f"{self.prometheus_url}/api/v1/query",
                    params={'query': query}
                )
                response.raise_for_status()
                
                for result in response.json()['data']['result']:
                    node = result['metric'].get('instance', '').split(':')[0]
                    if node not in metrics:
                        metrics[node] = {}
                    try:
                        metrics[node][metric_name] = float(result['value'][1])
                    except (IndexError, ValueError):
                        metrics[node][metric_name] = 0.0
                        
            return metrics
            
        except Exception as e:
            print(f"Error al obtener métricas: {e}")
            return {}
    
    def get_pod_distribution(self):
        """Obtiene la distribución actual de pods por nodo."""
        nodes = self.api.list_node()
        node_pods = defaultdict(list)
        
        for node in nodes.items:
            node_name = node.metadata.name
            pods = self.api.list_pod_for_all_namespaces(
                field_selector=f"spec.nodeName={node_name},status.phase=Running"
            )
            node_pods[node_name] = len(pods.items)
            
        return node_pods
    
    def balance_deployments(self, namespace='default'):
        """Balancea las cargas de los deployments entre los nodos."""
        try:
            # Obtener métricas de los nodos
            node_metrics = self.get_node_metrics()
            if not node_metrics:
                print("No se pudieron obtener métricas de los nodos")
                return
                
            print("Métricas de los nodos:", node_metrics)
            
            # Obtener distribución actual de pods
            pod_distribution = self.get_pod_distribution()
            print("Distribución actual de pods:", pod_distribution)
            
            # Obtener todos los deployments en el namespace
            deployments = self.apps_api.list_namespaced_deployment(namespace=namespace)
            
            # Aquí iría la lógica para decidir cómo mover los deployments
            # basado en las métricas recopiladas
            
            print("Balanceo completado")
            
        except Exception as e:
            print(f"Error en el balanceo: {e}")

def main():
    try:
        config.load_incluster_config()
    except config.ConfigException:
        print("No se pudo cargar la configuración in-cluster. ¿El script está corriendo dentro de un pod de Kubernetes?")
        return
    
    lb = LoadBalancer()
    
    # Ejecutar el balanceador cada 5 minutos
    while True:
        print(f"\n--- Iniciando ciclo de balanceo a las {time.ctime()} ---")
        lb.balance_deployments()
        print(f"--- Ciclo de balanceo completado. Esperando 5 minutos... ---\n")
        time.sleep(300)  # 5 minutos

if __name__ == "__main__":
    main()
