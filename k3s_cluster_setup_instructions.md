# Set up a K3s cluster for the EdgeMIND framework

These instructions have been used to successfully set up a K3s cluster for the EdgeMIND system on three Dell machines (one controller node and two worker nodes) and two Lenovo machines (Lenovo ThinkBook and Lenovo Legion, both worker nodes), each with the following specs:

- **OS**: Ubuntu 24.04.4 LTS (64-bit) or Ubuntu 24.04.2 LTS (64-bit)
- **Memory**: 16+ GB
- **Disk capacity**: 512+ GB

## Set up the EdgeMIND system

### Create/obtain and initialize required files and directories

The following services require initialization of some files and/or directories:
- `edgeMIND-vector-db-server`: requires permanent and temporary metadata JSON-files. **Instructions**: [vector db `README.md`](edgeMIND-vector-db-server/README.md).
- `pdf-processing-server`: requires a `.env` file. **Instructions**: [pdf processing server `README.md`](pdf-processing-server/README.md).

### Obtain required API keys

The `pdf-processing-server` service requres an API key for the LlamaParse model. The api key is stored in a `.env` file like this: `LLAMAPARSE_API_KEY=<your-api-key>`. **Instructions**: [pdf processing server `README.md`](pdf-processing-server/README.md).

### Additional required setup

The `LLMquery-server-text` service requires a local LLM model and the model setup in the code. **Instructions**: [llm query server `README.md`](LLMquery-server-text/README.md).


## Set up the nodes and install K3s

### Give all machines a unique host name

All the machines in the cluster must have unique host names. Check the host name of all machines with this command:
```bash
hostnamectl
```

If you want to or need to change the host name of any (or all) of the machines, run this command in all those machines:
```bash
hostnamectl set-hostname <NEW-HOSTNAME>
```

**You may need to use `sudo` in front of the commands.**

### Install K3s on master node

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

### Install K3s on the worker nodes

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

### Create a local Docker registry

Add the IP address (of the machine where you want the registry to live) + hostname mapping to `/etc/hosts` file on every node:
```bash
sudo nano /etc/hosts
```

The format should be: `x.x.x.x registry.local`. 
Replace `x.x.x.x` with the actual IP address of the machine where you will have your registry.

### Configure Docker's daemon.json file

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

### Run the registry container and push the images there

If you haven't already built the images, do it now.

After that, pull and run the registry container:
```bash
docker run -d -p 4000:5000 --name registry registry:2
```

Here we map port 4000 to port 5000, because the registry uses by default port 5000, but we already use port 5000 in the EdgeMIND framework, so we need to use some other port (here 4000).

Tag the images and push them to the local registry:
```bash
docker tag <IMAGE-NAME> registry.local:4000/<IMAGE-NAME>:latest

docker push registry.local:4000/<IMAGE-NAME>:latest
```

example:
```bash
docker tag audio-processing-service registry.local:4000/audio-processing-service:latest

docker push registry.local:4000/audio-processing-service:latest
```

### Create and edit registries.yaml files

On **each node**, create this directory if it doesn't exist yet:
```bash
sudo mkdir -p /etc/rancher/k3s
```

Then, edit (or create) this file: `/etc/rancher/k3s/registries.yaml`. To edit the file, open **any** text editor, for example:
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

### Label nodes for selective deployment (optional)

If you want to deploy specific containers on specific nodes you can add labels to the nodes like this:
```bash
sudo kubectl label node <NODE-NAME> <LABEL-KEY>=<LABEL-VALUE>
```

You get the names of the nodes by running:
```bash
sudo kubectl get nodes -o wide
```

Replace `<LABEl_KEY>` and `<LABEL-VALUE>` with any key-value pair.

### Download and save llm models on each node that runs the llm-text-gen-service

Download and save your preferred llm models locally on each node that you are planning to run the `llm-text-gen-service` on.

Download and save the model(s) to this directory: `/var/lib/llm-models/models/`, e.g. `/var/lib/llm-models/models/phi3`

### Deploy the EdgeMIND system

Deploy the EdgeMIND system by applying the K3s manifests for each service. The manifest files can be found in `K3s_manifests`. Before applying the manifests, you can specify the nodes to deploy the services on by adding the node names to the nodeAffinity section in each manifest file, for example, like this:
```yaml
apiVersion: apps/v1
kind: Deployment
...
spec:
  ...
  template:
      ...
      spec:
        ...
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: kubernetes.io/hostname
                # Add the values for the label with the key specified above
                operator: In
                values:
                - node1   # Example value
                - mynode  # Example value
```


Whenever you update the code and/or the manifest file(s), run these commands to apply the changes:

```bash
cd /path/to/edgeMIND/project/K3s_manifests

# Apply manifest
k3s kubectl apply -f <manifest-file.yaml>   # e.g. llm-text-gen-service.yaml
# Restart K3s deployment
k3s kubectl rollout restart deployment <name-of-deployment>   # e.g. llm-text-gen-service
```
