import os
import requests
from kubernetes import client, config

# 1. Config  
PROM_URL = os.getenv("PROMETHEUS_URL", "http://prometheus-kube-prometheus-prometheus.monitoring:9090") 

# --- INICIO CAMBIO PARA DEMO (COMENTAR/DESCOMENTAR SEGÚN NECESITES) ---
# CONSULTA ORIGINAL (producción - busca servicios inactivos por 7 días)
# QUERY    = 'increase(http_requests_total[7d]) == 0'

# CONSULTA PARA DEMO (hace que el script SIEMPRE intente parchear 'nginx-demo' si está corriendo)
QUERY    = 'kube_deployment_status_replicas_available{deployment="nginx-demo"} > 0'
# --- FIN CAMBIO PARA DEMO ---

def get_idle_services():
    """Obtiene una lista de servicios inactivos de Prometheus."""
    try:
        resp = requests.get(f"{PROM_URL}/api/v1/query", params={"query": QUERY})
        resp.raise_for_status() 
        results = resp.json()["data"]["result"]
        idle = []
        for item in results:
            # --- INICIO CAMBIO PARA DEMO (COMENTAR/DESCOMENTAR SEGÚN NECESITES) ---
            # Para la consulta original (http_requests_total), usa 'service'
            # svc = item["metric"].get("service")
            
            # Para la consulta de DEMO (kube_deployment_status_replicas_available), usa 'deployment'
            svc = item["metric"].get("deployment") 
            # --- FIN CAMBIO PARA DEMO ---

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
    # Usamos el nombre del deployment directamente ya que la consulta de DEMO lo devuelve como tal
    deployment_name = svc_name 
    try:
        # No necesitamos listar por selector si ya tenemos el nombre directo
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
        print("🚀 Todos los servicios tienen tráfico. No hay nada que mover (o no se encontró el deployment de demo).")
    else:
        print(f"Servicios inactivos encontrados (para demo): {idle_services}")
        for ns, svc in idle_services:
            move_to_spot(ns, svc)
            
if __name__ == "__main__":
    main()