import os
import requests
from kubernetes import client, config

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
    """Parchea un deployment para moverlo a nodos spot."""
    api = client.AppsV1Api()
    # Asume que el nombre del Deployment es el mismo que el nombre del servicio
    deployment_name = svc_name 
    try:
        # Encontrar el Deployment asociado al servicio. 
        # Esto puede requerir una lógica más compleja si el nombre del servicio no coincide directamente con el del deployment.
        # Por ahora, asumimos que coinciden para simplificar.
        d = api.read_namespaced_deployment(deployment_name, namespace)
        
        patch = {
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
        api.patch_namespaced_deployment(d.metadata.name, namespace, patch)
        print(f"→ Deployment '{d.metadata.name}' en namespace '{namespace}' parcheado para nodos spot.")
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