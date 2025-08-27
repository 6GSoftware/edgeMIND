# Set up a K3s cluster for the EdgeMIND framework

## Set up the nodes and install K3s

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
sudo kubectl get nodes

sudo kubectl get pods -A
```

You should see `STATUS=Ready` for the master node, and `Running` for the system pods.

Lastly, run this on the master node and copy the entire output string:
```bash
sudo cat /var/lib/rancher/k3s/server/node-token
```

The output is a token that is needed in joining the worker nodes to the cluster.

### 2. Install K3s on the worker nodes

On each worker node, run:
```bash
curl -sfL https://get.k3s.io | K3S_URL="https://<SERVER-IP>:6443" K3S_TOKEN="<CUSTOM-TOKEN>" sh -
```
Replace `SERVER-IP` with the IP address of the master node machine, and `CUSTOM-TOKEN` with the token that you printed in the console in step 1.

On master node, verify successfull installation with
```bash
sudo kubectl get nodes
```

You should now see `STATUS=Ready` for all nodes.

## Build images and set up the Docker registry

### 3. Create a local Docker registry

Add the IP address (of the machine where you want the registry to live) + hostname mapping to `/etc/hosts` file on every node:
```bash
sudo nano /etc/hosts
```

The format should be: `x.x.x.x registry.local`. 
Replace `x.x.x.x` with the actual IP address of the machine where you will have your registry.

### 4. Configure Docker's daemon.json file

Add this to the `/etc/docker/daemon.json` file to use HTTP instead of HTTPS:
```json
{
  "insecure-registries": ["registry.local:4000"]
}
```

Then, restart Docker daemon with:
```bash
sudo systemctl restart docker
```

### 5. Run the registry container and push the images there

If you haven't already built the images, do it now.

After that, pull and run the registry container:
```bash
sudo docker run -d -p 4000:5000 --name registry registry:2
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
sudo mkdir -p /etc/rancher/k3s
```

Then, edit (or create) this file: `/etc/rancher/k3s/registries.yaml`. To edit the file, open a text editor, for example:
```bash
sudo nano /etc/rancher/k3s/registries.yaml
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
sudo systemctl restart k3s
```

On worker nodes, run:
```bash
sudo systemctl restart k3s-agent
```

## Creating and configuring the deployments

### 7. (Optional) label nodes for selective deployment

If you want to deploy specific containers on specific nodes you can add labels to the nodes like this:
```bash
sudo kubectl label node <NODE-NAME> <LABEL-KEY>=<LABEL-VALUE>
```

You get the names of the nodes by running:
```bash
sudo kubectl get nodes -o wide
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

## Useful commands (for debugging)
Apply a manifest file to K3s:
```bash
sudo kubectl apply -f <NAME_OF_MANIFEST_FILE>.yaml
```

Get all repositories in the local Docker registry:
```bash
curl -X GET http://localhost:4000/v2/_catalog
```

Get container logs and output:
```bash
sudo kubectl logs <POD-NAME>
```

Restart a deployment in K3s:
```bash
sudo kubectl rollout restart deployment <NAME_OF_SERVICE>
```

Get inside a pod's shell:
```bash
sudo kubectl exec -it <POD_NAME> -- /bin/sh
```


## FIXING THE K3S GPU ISSUE

Install Helm if you don’t already have it:
```bash
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

After installing k3s and nvidia-container-toolkit, install the Nvidia device plugin operator:
```bash

helm repo add nvdp https://nvidia.github.io/k8s-device-plugin
helm repo update

helm upgrade -i nvdp nvdp/nvidia-device-plugin \
  --version=0.14.5 \
  --namespace nvidia-device-plugin \
  --create-namespace \
  --set gfd.enabled=true \
  --set runtimeClassName=nvidia
```

Label your node for GPU workloads:
```bash
sudo kubectl label node <NODE_NAME> processor=gpu --overwrite
```

<!-- You need to authenticate to nvcr.io and get an API key:
1. Go to this website: https://catalog.ngc.nvidia.com/?filters=&orderBy=weightPopularDESC&query=&page=&pageSize=
2. Log in → Click on your profile → Setup → API Key.
3. Generate a new API key. **Copy it (and save it somewhere)!**

After generating the API key log in to the registry:
```bash
docker login nvcr.io -u '$oauthtoken' -p <YOUR_NGC_API_KEY>
```
Replace `<YOUR_NGC_API_KEY>` with your API key!

Create a Kubernetes secret for pulling images:
```bash
kubectl create secret docker-registry nvidia-secret \
  --docker-server=nvcr.io \
  --docker-username='$oauthtoken' \
  --docker-password='<YOUR_NGC_API_KEY>' \
  --namespace nvidia-device-plugin
```
Replace `<YOUR_NGC_API_KEY>` with your API key!

Install/upgrade the nvidia-device-plugin and tell Helm to use the secret:
```bash
helm upgrade nvdp nvdp/nvidia-device-plugin \
  --install \
  --version=0.14.5 \
  --namespace nvidia-device-plugin \
  --create-namespace \
  --set gfd.enabled=true \
  --set runtimeClassName=nvidia \
  --set imagePullSecrets[0].name=nvidia-secret
```
The last line tells helm to use the secret that you just created. -->

Create runtimeclass manifest file (example name: `nvidia-runtimeclass.yaml`) and apply it with `kubectl apply -f <name-of-manifest-file>.yaml`:
```yaml
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: nvidia
handler: nvidia
```

Add this under `spec.template.spec` to the manifest files of the pods which you want to access the GPU:
```yaml
runtimeClassName: nvidia
```
Example:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: llm-image-gen-service
spec:
  replicas: 1
  selector:
    matchLabels:
      app: llm-image-gen-service
  template:
    metadata:
      labels:
        app: llm-image-gen-service
    spec:
      runtimeClassName: nvidia  # The runtime class name is here!
      affinity:
        ...
```
Apply with `kubectl apply -f <name-of-manifest-file>.yaml`.