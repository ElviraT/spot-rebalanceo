import os
import time
import json
import requests
from kubernetes import client, config
from collections import defaultdict

class LoadBalancer:
    def __init__(self):
        self.api = client.CoreV1Api()
        self.apps_api = client.AppsV1Api()
        self.prometheus_url = os.getenv("PROMETHEUS_URL", "http://prometheus-kube-prometheus-prometheus.monitoring:9090")
        
    def get_node_metrics(self):
        """Obtiene el uso de CPU y memoria de los nodos desde Prometheus."""
        metrics = defaultdict(dict)
        try:
            # Consulta para obtener el uso de CPU promedio del último minuto
            cpu_query = '100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)'
            # Consulta para obtener el uso de memoria
            mem_query = '100 - ((node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes) * 100'

            for metric_name, query in [('cpu', cpu_query), ('memory', mem_query)]:
                response = requests.get(
                    f"{self.prometheus_url}/api/v1/query",
                    params={'query': query}
                )
                response.raise_for_status()
                for result in response.json()['data']['result']:
                    node = result['metric'].get('instance', '').split(':')[0]
                    metrics[node][metric_name] = float(result['value'][1])
            return metrics
        except Exception as e:
            print(f"Error al obtener métricas de nodos: {e}")
            return {}
            
    def get_pod_distribution(self):
        """Obtiene la distribución de pods por nodo y por deployment."""
        pod_distribution = defaultdict(lambda: defaultdict(list))
        try:
            pods = self.api.list_pod_for_all_namespaces(field_selector="status.phase=Running")
            for pod in pods.items:
                node_name = pod.spec.node_name
                if not node_name:
                    continue
                
                # Intentamos encontrar el deployment del pod a través del ReplicaSet
                owner_ref = pod.metadata.owner_references
                if owner_ref and owner_ref[0].kind == 'ReplicaSet':
                    rs = self.apps_api.read_namespaced_replica_set(
                        name=owner_ref[0].name,
                        namespace=pod.metadata.namespace
                    )
                    deployment_name = rs.metadata.owner_references[0].name
                    pod_distribution[node_name][deployment_name].append(pod)
        except Exception as e:
            print(f"Error al obtener distribución de pods: {e}")
            return {}
        return pod_distribution

    def move_pod(self, pod):
        """Elimina un pod para que sea reprogramado por el scheduler de Kubernetes."""
        try:
            print(f"    - Moviendo pod: {pod.metadata.name} del nodo {pod.spec.node_name}")
            self.api.delete_namespaced_pod(name=pod.metadata.name, namespace=pod.metadata.namespace)
        except client.ApiException as e:
            print(f"Error al eliminar el pod {pod.metadata.name}: {e}")

    def balance_deployments(self, namespace='default'):
        """Balancea las cargas de los deployments basándose en políticas."""
        # Configuración de los umbrales para las políticas
        low_utilization_threshold = 0.4  # 40%
        over_utilization_threshold = 0.8  # 80%

        print("Iniciando balanceo de cargas...")
        node_metrics = self.get_node_metrics()
        pod_distribution = self.get_pod_distribution()

        if not node_metrics or not pod_distribution:
            print("No se pudieron obtener métricas o distribución de pods. Cancelando balanceo.")
            return

        print("Métricas de Nodos:", {node: {k: f"{v:.2f}%" for k, v in metrics.items()} for node, metrics in node_metrics.items()})
        print("Distribución de Pods:", {node: {dep: len(pods) for dep, pods in deps.items()} for node, deps in pod_distribution.items()})

        pods_to_move = []
        
        # 1. Política RemoveDuplicates: Mueve pods duplicados
        print("\nAplicando política 'RemoveDuplicates'...")
        for node, deployments in pod_distribution.items():
            for deployment_name, pods in deployments.items():
                if len(pods) > 1:
                    print(f"  - Nodo '{node}' tiene {len(pods)} pods del deployment '{deployment_name}'.")
                    # Añade todos los pods excepto el último a la lista para mover
                    pods_to_move.extend(pods[:-1])
        
        # 2. Política LowNodeUtilization: Mueve pods de nodos subutilizados
        print("\nAplicando política 'LowNodeUtilization'...")
        underutilized_nodes = [
            node for node, metrics in node_metrics.items()
            if (metrics.get('cpu', 0) + metrics.get('memory', 0)) / 2 < low_utilization_threshold
        ]
        
        if underutilized_nodes:
            print(f"  - Nodos subutilizados identificados: {underutilized_nodes}")
            for node in underutilized_nodes:
                if node in pod_distribution:
                    # En este ejemplo, movemos todos los pods del nodo subutilizado
                    for deployment_name, pods in pod_distribution[node].items():
                        pods_to_move.extend(pods)
        
        # 3. Mover los pods identificados
        if pods_to_move:
            print(f"\nSe moverán {len(pods_to_move)} pods para rebalanceo.")
            # Usar un set para evitar mover el mismo pod varias veces
            unique_pods = {pod.metadata.uid: pod for pod in pods_to_move}.values()
            for pod in unique_pods:
                self.move_pod(pod)
        else:
            print("\nNo se encontraron pods para mover. El clúster está balanceado.")
            
        print("\nBalanceo de cargas completado.")

def main():
    try:
        config.load_incluster_config()
    except config.ConfigException:
        print("No se pudo cargar la configuración in-cluster. ¿El script está corriendo dentro de un pod de Kubernetes?")
        return
    
    lb = LoadBalancer()
    
    # El bucle principal para ejecutar el balanceador
    while True:
        print(f"\n--- Iniciando ciclo de balanceo a las {time.ctime()} ---")
        lb.balance_deployments()
        print(f"--- Ciclo de balanceo completado. Esperando 5 minutos... ---\n")
        time.sleep(300)

if __name__ == "__main__":
    main()