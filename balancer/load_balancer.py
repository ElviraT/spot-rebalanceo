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
        self.underutilized_threshold = 0.4  # Umbral de uso por debajo del cual un nodo se considera subutilizado
        self.low_utilization_threshold = 0.2 # Umbral para la remoción del nodo (por ejemplo, 20% de uso)
        
    def get_node_metrics(self):
        """Obtiene métricas de uso de CPU y memoria de los nodos desde Prometheus."""
        metrics = defaultdict(dict)
        try:
            cpu_query = '100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)'
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
            print(f"    - Drenando y moviendo pod: {pod.metadata.name} del nodo {pod.spec.node_name}")
            self.api.delete_namespaced_pod(name=pod.metadata.name, namespace=pod.metadata.namespace)
        except client.ApiException as e:
            print(f"Error al eliminar el pod {pod.metadata.name}: {e}")

    def drain_and_delete_node(self, node_name):
        """Drena y elimina un nodo del clúster."""
        try:
            print(f"  - Drenando nodo '{node_name}' para su eliminación.")
            # Marcar el nodo como no programable
            self.api.patch_node(
                name=node_name,
                body={'spec': {'unschedulable': True}}
            )
            
            # Obtener y mover pods del nodo (excepto los de sistema)
            pods_on_node = self.api.list_pod_for_all_namespaces(
                field_selector=f"spec.nodeName={node_name},status.phase=Running"
            )
            for pod in pods_on_node.items:
                if pod.metadata.namespace != 'kube-system':
                    self.move_pod(pod)

            # Esperar a que los pods se muevan (lógica simplificada)
            time.sleep(30)
            
            # Eliminar el nodo
            print(f"  - Eliminando nodo '{node_name}'.")
            self.api.delete_node(name=node_name)
            print(f"  - Nodo '{node_name}' eliminado exitosamente.")

        except client.ApiException as e:
            print(f"Error al drenar o eliminar el nodo {node_name}: {e}")

    def balance_deployments(self, namespace='default'):
        """Balancea las cargas de los deployments y gestiona el desescalado de nodos."""
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
                    pods_to_move.extend(pods[:-1])
        
        # 2. Política LowNodeUtilization: Mueve pods de nodos subutilizados
        print("\nAplicando política 'LowNodeUtilization'...")
        underutilized_nodes = [
            node for node, metrics in node_metrics.items()
            if (metrics.get('cpu', 0) + metrics.get('memory', 0)) / 2 < self.underutilized_threshold
        ]
        
        if underutilized_nodes:
            print(f"  - Nodos subutilizados identificados: {underutilized_nodes}")
            for node in underutilized_nodes:
                if node in pod_distribution:
                    for deployment_name, pods in pod_distribution[node].items():
                        pods_to_move.extend(pods)
        
        # Mover los pods identificados
        if pods_to_move:
            print(f"\nSe moverán {len(pods_to_move)} pods para rebalanceo.")
            unique_pods = {pod.metadata.uid: pod for pod in pods_to_move}.values()
            for pod in unique_pods:
                self.move_pod(pod)
        else:
            print("\nNo se encontraron pods para mover. El clúster está balanceado o no hay nodos para rebalancear.")
        
        # 3. Lógica de Desescalado (adicional para resolver el problema del coordinador)
        print("\nAplicando política de desescalado...")
        for node, metrics in node_metrics.items():
            if (metrics.get('cpu', 0) + metrics.get('memory', 0)) / 2 < self.low_utilization_threshold:
                # Si el nodo está subutilizado, intenta drenarlo y eliminarlo
                self.drain_and_delete_node(node)
            else:
                print(f"  - Nodo '{node}' no es candidato para ser eliminado (uso > {self.low_utilization_threshold*100:.0f}%).")
            
        print("\nBalanceo de cargas completado.")

def main():
    try:
        config.load_incluster_config()
    except config.ConfigException:
        print("No se pudo cargar la configuración in-cluster. ¿El script está corriendo dentro de un pod de Kubernetes?")
        return
    
    lb = LoadBalancer()
    
    while True:
        print(f"\n--- Iniciando ciclo de balanceo a las {time.ctime()} ---")
        lb.balance_deployments()
        print(f"--- Ciclo de balanceo completado. Esperando 5 minutos... ---\n")
        time.sleep(300)

if __name__ == "__main__":
    main()