#!/bin/bash

# Este script automatiza la instalación de Prometheus en el namespace monitoring.
# Se asegura de que el namespace exista y luego instala el kube-prometheus-stack.

echo "Verificando si el namespace 'monitoring' existe..."
if ! kubectl get namespace monitoring &> /dev/null; then
    echo "El namespace 'monitoring' no existe. Creándolo..."
    kubectl create namespace monitoring
else
    echo "El namespace 'monitoring' ya existe. Continuando..."
fi

echo "Añadiendo el repositorio de Helm de Prometheus..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts

echo "Actualizando los repositorios de Helm..."
helm repo update

echo "Instalando el kube-prometheus-stack en el namespace 'monitoring'..."
helm install prometheus prometheus-community/kube-prometheus-stack --namespace monitoring

echo "Instalación completada. Espera unos minutos para que los pods se inicien."
echo "Puedes verificar el estado con el siguiente comando: kubectl get pods -n monitoring"