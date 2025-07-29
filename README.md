# Sistema de Balanceo y Nodos Spot en Kubernetes

Este proyecto implementa un sistema para gestionar automáticamente la carga de trabajo entre nodos regulares y nodos spot en un cluster de Kubernetes, optimizando costos mediante el uso eficiente de recursos.

## 🏗️ Arquitectura

El sistema consta de los siguientes componentes principales:

1. **Monitor de Carga**: Un script Python que monitorea la carga de los nodos y balancea los despliegues.
2. **Balanceador de Carga**: Distribuye la carga entre los nodos regulares y spot.
3. **Kubernetes CronJob**: Ejecuta periódicamente el script de balanceo.
4. **Prometheus**: Recolecta métricas del cluster para la toma de decisiones.

## 📁 Estructura del Proyecto

```
.
├── automatization.py     # Script para mover servicios a nodos spot
├── load_balancer.py     # Balanceador de carga entre nodos
├── namespaces.yaml      # Configuración de namespaces y políticas de red
├── banking-deployments.yaml  # Ejemplos de despliegues para servicios bancarios
├── rbac.yaml            # Configuración de RBAC para el balanceador
├── cronjob.yaml         # Configuración del CronJob
├── Dockerfile           # Para construir la imagen del balanceador
├── requirements.txt     # Dependencias de Python
└── tests/               # Pruebas de integración
    └── test_integration.py
```

## 🚀 Despliegue

### Requisitos Previos

- Cluster de Kubernetes con nodos regulares y spot
- Prometheus desplegado en el namespace `monitoring`
- `kubectl` configurado para acceder al cluster

### 1. Configurar los namespaces

```bash
kubectl apply -f namespaces.yaml
```

### 2. Desplegar los componentes RBAC

```bash
kubectl apply -f rbac.yaml
```

### 3. Construir y desplegar el balanceador

1. Construir la imagen Docker:

```bash
docker build -t tu-registro/load-balancer:latest .
docker push tu-registro/load-balancer:latest
```

2. Actualizar la referencia a la imagen en `cronjob.yaml`
3. Desplegar el CronJob:

```bash
kubectl apply -f cronjob.yaml
```

### 4. Desplegar aplicaciones de ejemplo

```bash
kubectl apply -f banking-deployments.yaml
```

## 🔄 Flujo de Trabajo

1. El CronJob ejecuta periódicamente el script de balanceo.
2. El balanceador recopila métricas de Prometheus sobre el uso de recursos.
3. Basado en las métricas, decide si mover servicios entre nodos regulares y spot.
4. Los servicios con menor prioridad se mueven a nodos spot para reducir costos.
5. Se monitorea constantemente el estado del cluster para mantener el equilibrio.

## 🧪 Pruebas

Para ejecutar las pruebas de integración:

```bash
pip install -r requirements.txt
python -m pytest tests/
```

## 🔍 Monitoreo

El sistema expone métricas que pueden ser recopiladas por Prometheus. Las métricas incluyen:

- Uso de CPU y memoria por nodo
- Distribución de pods
- Eventos de balanceo

## 🔧 Solución de Problemas

### Verificar el estado del CronJob

```bash
kubectl get cronjobs -n monitoring
kubectl get pods -n monitoring
kubectl logs -n monitoring <nombre-del-pod>
```

### Verificar los logs del balanceador

```bash
kubectl logs -n monitoring -l app=spot-balancer
```

## 📝 Licencia

Este proyecto está bajo la Licencia MIT. Ver el archivo `LICENSE` para más detalles.

## 🤝 Contribuciones

Las contribuciones son bienvenidas. Por favor, lee las directrices de contribución antes de enviar pull requests.
