# Set up a K3s cluster for the EdgeMIND framework

## Set up the nodes and install K3s

### Uninstall old k3s-agent

Unistall a k3s-agent with this command:
```bash
/usr/local/bin/k3s-agent-uninstall.sh
```

### 0. Give all machines a unique host name

All the machines in the cluster must have unique host names. Check the host name of all machines with this command:
```bash
hostnamectl
```

If you want to or need to change the host name of any (or all) of the machines, run this command in all those machines:
```bash
hostnamectl set-hostname <NEW-HOSTNAME>
```

**You may need to use `sudo` in front of the commands.**

### 1. Install K3s on master node

Run this command on the master node machine:

```bash
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--flannel-backend=host-gw" K3S_TOKEN="<CUSTOM-TOKEN>" sh -
```

Check that it was successfully installed with:
```bash
kubectl get nodes

kubectl get pods -A
```

You should see `STATUS=Ready` for the master node, and `Running` for the system pods.

Lastly, run this on the master node and copy the entire output string:
```bash
cat /var/lib/rancher/k3s/server/node-token
```

The output is a token that is needed in joining the worker nodes to the cluster.

### 2. Install K3s on the worker nodes

On each worker node, run:
```bash
curl -sfL https://get.k3s.io | K3S_URL="https://<SERVER-IP>:6443" K3S_TOKEN="<CUSTOM-TOKEN>" sh -
```
Replace `SERVER-IP` with the IP address of the master node machine, and `CUSTOM-TOKEN` with the token that you printed in the console in step 1.
If you are adding a new node to an existing cluster, you can find the cluster token and master node IP from this file:
```bash
cat /etc/rancher/k3s/config.yaml
```

On master node, verify successfull installation with
```bash
kubectl get nodes
```

You should now see `STATUS=Ready` for all nodes.

## Build images and set up the Docker registry

### 3. Create a local Docker registry (each node)

Add the IP address (of the machine where you want the registry to live) + hostname mapping to `/etc/hosts` file on every node:
```bash
nano /etc/hosts
```

The format should be: 
```bash
x.x.x.x registry.local  # Replace x.x.x.x with actual IP address
``` 
Replace `x.x.x.x` with the actual IP address of the machine where you will have your registry.

### 4. Configure Docker's daemon.json file (on each node)

Add this to the `/etc/docker/daemon.json` file to use HTTP instead of HTTPS:
```json
{
  "insecure-registries": ["registry.local:4000"]
}
```

To modify the file, you must run:
```bash
nano /etc/docker/daemon.json
```
... or use some other text editor.

Then, restart Docker daemon with:
```bash
systemctl restart docker
```

### 5. Run the registry container and push the images there

If you haven't already built the images, do it now.

After that, pull and run the registry container:
```bash
docker run -d -p 4000:5000 --name registry registry:2
```

Here we map port 4000 to port 5000, because the registry uses by default port 5000, but we already use port 5000 in the EdgeMIND framework, so we need to use some other port (here 4000).

Tag the images and push them to the local registry:
```bash
docker tag <IMAGE-NAME> registry.local:4000/<IMAGE-NAME>

docker push registry.local:4000/<IMAGE-NAME>
```

example:
```bash
docker tag audio-processing-service registry.local:4000/audio-processing-service

docker push registry.local:4000/audio-processing-service
```

### 6. Create and edit registries.yaml files

On **each node**, create this directory if it doesn't exist yet:
```bash
mkdir -p /etc/rancher/k3s
```

Then, edit (or create) this file: `/etc/rancher/k3s/registries.yaml`. To edit the file, open a text editor, for example:
```bash
nano /etc/rancher/k3s/registries.yaml
```

In each `registries.yaml` file, add:
```yaml
mirrors:
  "registry.local:4000":
    endpoint:
      - "http://registry.local:4000"
```

**Remember to do these steps on all nodes in the cluster!**

After that restart the k3s service on **all master nodes and worker nodes**:
On master node(s), run:
```bash
systemctl restart k3s
```

On worker nodes, run:
```bash
systemctl restart k3s-agent
```

## Creating and configuring the deployments

### 7. (Optional) label nodes for selective deployment

If you want to deploy specific containers on specific nodes you can add labels to the nodes like this:
```bash
kubectl label node <NODE-NAME> <LABEL-KEY>=<LABEL-VALUE>
```

You get the names of the nodes by running:
```bash
kubectl get nodes -o wide
```

Replace `<LABEl_KEY>` and `<LABEL-VALUE>` with any key-value pair.

### 8. Create k3s manifest files

Create a folder (for example `k3s` or `manifest`) anywhere on the master node machine to store the manifest files (needed for deployment of the services).

For each service you intend to deploy, create a manifest file (yaml format), for example, with the help of this template:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: service-x   # replace with a custom name for the service
spec:
  replicas: 1
  selector:
    matchLabels:
      app: service-x    # here (and below) use the same name as above for metadata.name
  template:
    metadata:
      labels:
        app: service-x
    spec:
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchLabels:
                app: service-x
            topologyKey: "kubernetes.io/hostname"
      nodeSelector:
        <KEY>: <VALUE>  # Here put any label + its value you have given to any node(s)
      containers:
      - name: service-x
        image: registry.local:4000/<container-image>    # replace with the name of your service's container image
        ports:
        - containerPort: 1000   # replace with the container's internal port
---
apiVersion: v1
kind: Service
metadata:
  name: service-x
spec:
  selector:
    app: service-x
  ports:
  - port: 1000          # replace with the container's external port
    targetPort: 1000    # replace with the container's internal port

```
