#!/bin/bash

# Este script automatiza el despliegue del proyecto en una sesión de Killercode.

echo "--- Iniciando configuración de Killercode ---"

# 1. Etiquetar el nodo de Killercode como "spot"
echo "1. Etiquetando el nodo 'controlplane' como spot..."
kubectl label node controlplane node.kubernetes.io/lifecycle=spot --overwrite
echo "   Nodo etiquetado."

# 2. Crear los namespaces
echo "2. Creando los namespaces 'monitoring' y 'banco'..."
kubectl apply -f namespaces.yaml
echo "   Namespaces creados."

# 3. Crear y aplicar el RBAC de DEPURACIÓN (para superar el problema de permisos)
# Este es un RBAC de depuración que otorga amplios permisos, solo para la demo en Killercode.
echo "3. Creando y aplicando RBAC de DEPURACIÓN (¡ADVERTENCIA: SOLO PARA DEMO!)..."
cat <<EOF > rbac-debug.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: spot-mover-debug-admin
rules:
- apiGroups: ["*"]
  resources: ["*"]
  verbs: ["*"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: spot-mover-debug-admin-binding
subjects:
- kind: ServiceAccount
  name: spot-mover
  namespace: monitoring
roleRef:
  kind: ClusterRole
  name: spot-mover-debug-admin
  apiGroup: rbac.authorization.k8s.io
EOF
kubectl apply -f rbac-debug.yaml
echo "   RBAC de depuración aplicado."

# 4. Añadir repositorio de Helm e instalar kube-prometheus-stack
echo "4. Añadiendo repositorio de Helm e instalando 'kube-prometheus-stack'..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install prometheus prometheus-community/kube-prometheus-stack -n monitoring --wait --timeout 5m
echo "   'kube-prometheus-stack' instalado."

# 5. Crear y aplicar el CronJob (configurado para cada minuto para la demo)
echo "5. Creando y aplicando el CronJob 'spot-mover-cron' (cada minuto para demo)..."
kubectl apply -f cronjob.yaml
echo "   CronJob 'spot-mover-cron' aplicado."

# 6. Crear y aplicar los Deployments de prueba (servicios bancarios)
echo "6. Creando y aplicando los Deployments de prueba 'banco'..."
kubectl apply -f banking-deployments.yaml
echo "   Deployments aplicados."

echo "--- Configuración completa. Esperando 60 segundos para que el CronJob se ejecute por primera vez... ---"
sleep 60

# 7. Verificación final
echo "7. Verificando el parcheo del Deployment 'servicio-bancario'..."
kubectl get deployment servicio-bancario -n banco -o yaml | grep -A 5 "nodeSelector"

echo "--- Fin de la ejecución del script ---"