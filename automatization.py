import os
import requests
from kubernetes import client, config
import datetime

# 1. Config  
PROM_URL = os.getenv("PROMETHEUS_URL", "http://prometheus-kube-prometheus-prometheus.monitoring:9090") 

QUERY    = 'increase(http_requests_total[7d]) == 0'

def get_idle_services():
    """Obtiene una lista de servicios inactivos de Prometheus."""
    try:
        resp = requests.get(f"{PROM_URL}/api/v1/query", params={"query": QUERY})
        resp.raise_for_status() 
        results = resp.json()["data"]["result"]
        idle = []
        for item in results:
            svc = item["metric"].get("service")
            ns  = item["metric"].get("namespace", "default")
            if svc:
                idle.append((ns, svc))
        return idle
    except requests.exceptions.RequestException as e:
        print(f"Error al conectar con Prometheus: {e}")
        return []
    except KeyError as e:
        print(f"Error al parsear la respuesta de Prometheus (KeyError: {e}). Respuesta: {resp.text}")
        return []

def move_to_spot(namespace, svc_name):
    """Parchea un deployment para moverlo a nodos spot y fuerza un rollout."""
    api = client.AppsV1Api()
    deployment_name = svc_name 
    try:
        # Parche 1: Añadir el nodeSelector para los nuevos pods
        patch_node_selector = {
            "spec": {
                "template": {
                    "spec": {
                        "nodeSelector": {
                            "node.kubernetes.io/lifecycle": "spot"
                        }
                    }
                }
            }
        }
        api.patch_namespaced_deployment(deployment_name, namespace, patch_node_selector)
        print(f"→ Deployment '{deployment_name}' en namespace '{namespace}' parcheado con nodeSelector 'spot'.")

        # Parche 2: Forzar un rollout actualizando una anotación con un timestamp
        # Esto reiniciará todos los pods existentes para que sean reprogramados en los nodos spot.
        now = datetime.datetime.utcnow().isoformat("T") + "Z"
        patch_rollout = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": now
                        }
                    }
                }
            }
        }
        api.patch_namespaced_deployment(deployment_name, namespace, patch_rollout)
        print(f"→ Rollout del Deployment '{deployment_name}' en namespace '{namespace}' iniciado.")

    except client.ApiException as e:
        print(f"Error de Kubernetes al parchear deployment '{deployment_name}' en '{namespace}': {e}")
    except Exception as e:
        print(f"Error inesperado al parchear deployment '{deployment_name}' en '{namespace}': {e}")

def main():
    """Función principal para obtener servicios inactivos y moverlos a spot."""
    try:
        config.load_incluster_config()
    except config.ConfigException:
        print("No se pudo cargar la configuración in-cluster. ¿El script está corriendo dentro de un pod de Kubernetes?")
        return

    print(f"Conectando a Prometheus en: {PROM_URL}")
    idle_services = get_idle_services()
    
    if not idle_services:
        print("🚀 Todos los servicios tienen tráfico. No hay nada que mover.")
    else:
        print(f"Servicios inactivos encontrados: {idle_services}")
        for ns, svc in idle_services:
            move_to_spot(ns, svc)
            
if __name__ == "__main__":
    main()