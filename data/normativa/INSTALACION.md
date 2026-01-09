# 🚀 Guía K8s Local: Colima + K3s + Cilium (Optimizado para futuro OpenShift)

Este entorno está diseñado para ser ligero en un MacBook 2017 (16GB RAM) pero manteniendo estándares de nivel empresarial para facilitar una migración futura a Red Hat OpenShift.

## 🛠 1. Requisitos Previos

Instala las herramientas base desde la terminal usando Homebrew:

```bash
brew install colima kubectl cilium-cli helm
```

## 🏗 2. Despliegue del Clúster
Arrancamos Colima configurando el motor de K3s sin los componentes "ligeros" por defecto para usar estándares de industria (Cilium y HAProxy).

```bash
colima start --cpu 3 --memory 6 --disk 30 --kubernetes \
  --k3s-arg "--flannel-backend=none" \
  --k3s-arg "--disable=traefik" \
  --k3s-arg "--disable-network-policy" \
  --k3s-arg "--disable=servicelb"
```

> [!NOTE]ota: Reservamos 6GB de RAM. Esto permite que el sistema macOS y el navegador sigan funcionando fluidamente.


## 🔌 3. Red Avanzada con Cilium (eBPF)
En lugar de la red básica, instalamos Cilium. Esto te permitirá usar Hubble para observar el tráfico, algo muy similar a lo que verás en la consola de OpenShift.

```bash
# Instalación de Cilium
cilium install

# Habilitar Hubble (Observabilidad)
cilium hubble enable --ui
```

## 🚪 4. Ingress Controller (HAProxy)
OpenShift utiliza internamente una versión modificada de HAProxy. Usarlo en local te familiarizará con su comportamiento.

```bash
helm repo add haproxytech https://haproxytech.github.io/helm-charts
helm repo update
helm search repo haproxytech/kubernetes-ingress

helm install haproxy-ingress haproxytech/kubernetes-ingress \                                   
  --create-namespace --namespace ingress-controller
  
```
Para validar:
```bash
kubectl -n ingress-controller get pods
kubectl -n ingress-controller get svc
```

### Paso A. Para sacar la ip alcanzable de un nodo desplegado
```bash
kubectl get node colima -o wide
kubectl get node colima -o jsonpath='{range .status.addresses[*]}{.type}{" "}{.address}{"\n"}{end}'
```

### Paso B. Prueba acceso con esa IP + NodePort
```bash
curl -I http://<INTERNAL_IP>:32279
```

### Si NO funciona (lo más común en Colima): usa port-forward
```bash
kubectl -n ingress-controller port-forward svc/haproxy-ingress-kubernetes-ingress 8080:80 8443:443
```

Y accedes desde tu Mac:
* http://localhost:8080
* https://localhost:8443
  
Esto evita completamente el problema de “IP de la VM no enrutable”.


### Alternativas si quieres “como producción” (con IP externa)
Si quieres que EXTERNAL-IP deje de ser <none> en un entorno local, normalmente haces una de estas:
* MetalLB (simula LoadBalancer en bare metal)
* Traefik/Ingress propio de k3s + mapeos del runtime
* Colima con soporte de LoadBalancer (según versión/config; no siempre aplica)

Pero para avanzar ahora mismo, port-forward es la vía rápida y fiable.

## 🎯 5. Reglas de Oro para Compatibilidad con OpenShift
Si quieres que lo que programes hoy en K3s funcione en OpenShift mañana sin errores, sigue estas 3 reglas en tus archivos YAML:
### A. No uses usuarios ROOT (SCC Compliance)
OpenShift prohíbe por defecto que los contenedores corran como root.
Mal: Tu Dockerfile termina en USER root.
Bien: Configura el securityContext en tu YAML:

```yaml
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1001
```

## B. Usa Resource Quotas
OpenShift es estricto con los recursos. Define siempre límites en tus despliegues:

```yaml
resources:
  limits:
    cpu: "500m"
    memory: "512Mi"
  requests:
    cpu: "100m"
    memory: "256Mi"
```

## C. Almacenamiento Estándar
Usa siempre PersistentVolumeClaims con accessModes: [ReadWriteOnce]. No mapees carpetas locales de tu Mac directamente (hostPath), ya que OpenShift lo bloqueará por seguridad.

## 🖥 6. Gestión Visual con Rancher
Para tener un panel de control profesional:

```bash
helm repo add rancher-stable releases.rancher.com
kubectl create namespace cattle-system

helm install rancher rancher-stable/rancher \
  --namespace cattle-system \
  --set hostname=rancher.localhost \
  --set bootstrapPassword=admin \
  --set replicas=1
```
Para entrar al panel:
Ejecuta: kubectl port-forward -n cattle-system deployments/rancher 8443:443
Abre: https://localhost:8443

## 📝 Comandos de Mantenimiento

|Acción	                                      |Comando      |
|---------------------------------------------|-------------|
|Pausar todo (ahorrar batería)	              |colima stop  |
|Reanudar	                                  |colima start |
|Ver estado de red	                          |cilium status|
|Destruir y limpiar todo	                  |colima delete|


