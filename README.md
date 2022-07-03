# kubectl pull-image
TL;DR: It's like `docker pull <image>` but from a Kubernetes cluster instead of from a docker registry.

## Usage
1. Run `kubectl pull-image [-n NAMESPACE] [-c CONTAINER] <POD_NAME>` (the `-c` flag is only required in case the pod runs more than a single container).
2. Witness how auto-magically the image used by that pod's container appears in your local docker by running `docker images <IMAGE>`.
3. Profit!

## Behind the scenes
The gory details:
1. You execute the `kubectl pull-image` command to pull an image of some pod's container into your local docker environment.
2. The client makes an API call to kube-apiserver to find out on which k8s node that container is running.
3. The client makes an API call to kube-apiserver to run a k8s Job named `<POD_NAME>-image-cloner` in the same namespace as the pod provided in step #1. The Job spins up a pod on the same node discovered in step #2 using [latest docker official image](https://hub.docker.com/_/docker) while mounting the node's docker socket to the pod.
4. The pod executes `docker save <IMAGE> | base64` (where `<IMAGE>` is the image specified in that container's spec) to print out the entire image as base64 encoded string to STDOUT ([base64 encoding makes the image roughly 33-37% larger](https://en.wikipedia.org/wiki/Base64#:~:text=This%20encoding%20causes%20an%20overhead%20of%2033%E2%80%9337%25%20(33%25%20by%20the%20encoding%20itself%3B%20up%20to%204%25%20more%20by%20the%20inserted%20line%20breaks))).
5. The client makes periodical check to kube-apiserver (every 2 seconds) to detected when the Job has completed.
6. Once the job has completed, the client makes an API call to kube-apiserver to fetch the log of the pod spawned by that job.
7. The client decodes the base64 encoded image (the pod's log) and feeds it as STDIN to `docker load`.
8. The client deletes the k8s Job (and the completed pod) by patching the Job's `.spec.ttlSecondsAfterFinished` to `1` second.
9. You now have the image on your local machine (`docker images <IMAGE>`).

## But... Why?
Couple of use cases:
1. The Docker registy from which the images you wish pull is not routable directly from your machine or it is running behing a firewall that whitelists specific source IPs (like the kubernetes node's or their NAT address).
2. You do have access to the Docker registry but it's private and either you don't have the credentials for it or you are too lazy (or don't want) to add them to your local docker's `config.json`.
3. You want a "quick n' dirty" way to fetch the image locally in order to scan it or to experiment with it.

## Installation
1. Download the binary: `curl -L https://github.com/yarozen/kubectl-pull_image/releases/download/v0.1.0/kubectl-pull_image -O -s`.
2. Make it executable: `chmod +x kubectl-pull_image`.
3. Add the binary file location to your `PATH` environment variable: `export PATH=$PATH:$PWD`.
3. Run it: `kubectl pull-image -h`.

## Prerequisites
1. Docker installed on your local machine from which you execute the `kubectl pull-image` command.
2. Connectivity to your current Kubernetes cluster context (`KUBECONFIG`).
3. Kubernetes roles to create, list & get Jobs & Pods.
4. Permission to mount docker socket to pods. If the k8s cluster runs an admission controller (e.g. OPA gatekeeper) make sure it permits that or create a rule to exclude it. 

## Build
1. Clone this repo: `git clone https://github.com/yarozen/kubectl-pull_image.git`.
2. Create a one-file bundled executable: `Create a one-file bundled executable` (the executable will be found at `dist/kubectl-pull_image`).

## Author
Written by Yaniv Rozenboim.


