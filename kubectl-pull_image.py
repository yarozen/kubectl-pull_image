#!/usr/bin/env python3

import argparse
from kubernetes import client, config
import sys
from time import sleep
from base64 import b64decode
import docker
import logging


def arguments_parsing():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "pod", help="Pod that runs a container that its image you wish to pull"
    )
    parser.add_argument("-n", "--namespace", help="Namespace of pod")
    parser.add_argument(
        "-c",
        "--container",
        help="Container that its image you wish to pull (required in case the pod runs more than one container)",
    )
    return parser.parse_args()


def get_pod_data(args):
    v1 = client.CoreV1Api()
    pod_name = args.pod
    if args.namespace:
        namespace = args.namespace
    else:
        namespace = config.list_kube_config_contexts()[1]["context"].get(
            "namespace", "default"
        )
    cluster = config.list_kube_config_contexts()[1]["context"]["cluster"]
    try:
        pod = v1.read_namespaced_pod(pod_name, namespace)
    except Exception as e:
        sys.exit(e)
    if args.container:
        for container_obj in pod.spec.containers:
            if args.container == container_obj.name:
                container = container_obj.name
                image = container_obj.image
                break
        else:
            sys.exit(f"container {args.container} is not valid for pod {pod_name}")
    else:
        if len(pod.spec.containers) == 1:
            container = pod.spec.containers[0].name
            image = pod.spec.containers[0].image
        else:
            sys.exit(
                f"Multiple containers in pod {pod_name}: {[container_obj.name for container_obj in pod.spec.containers]}, specify the one you want to pull with '-c' flag"
            )
    node = pod.spec.node_name
    return (
        cluster,
        image,
        container,
        node,
        pod_name,
        namespace,
    )


def clone_image(cluster, image, container, node, pod, namespace):
    logging.info(
        f"Starting k8s Job to save {image} docker image as base64 encoded output to STDOUT (container={container}, pod={pod}, namespace={namespace}, node={node}, cluster={cluster})."
    )
    dockersock_volume_mount = client.V1VolumeMount(
        mount_path="/var/run/docker.sock", name="dockersock"
    )
    dockersock_volume = client.V1Volume(
        host_path=client.V1HostPathVolumeSource(path="/var/run/docker.sock"),
        name="dockersock",
    )
    container = client.V1Container(
        name=f"docker",
        image="docker:20.10.17",
        resources=client.V1ResourceRequirements(
            requests={"cpu": "100m", "memory": "200Mi"},
            limits={"cpu": "500m", "memory": "500Mi"},
        ),
        command=["/bin/sh", "-c"],
        args=[f"docker save {image} | base64"],
        volume_mounts=[dockersock_volume_mount],
    )
    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels={"app": "image-cloner"}),
        spec=client.V1PodSpec(
            containers=[container],
            node_name=node,
            restart_policy="Never",
            volumes=[dockersock_volume],
        ),
    )
    spec = client.V1JobSpec(
        template=template, ttl_seconds_after_finished=600, backoff_limit=0
    )
    job = client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(name=pod + "-image-cloner"),
        spec=spec,
    )
    batchv1 = client.BatchV1Api()
    job = batchv1.create_namespaced_job(body=job, namespace=namespace)
    while True:
        sleep(2)
        job_status = batchv1.read_namespaced_job_status(
            name=job.metadata.name, namespace=job.metadata.namespace
        )
        if job_status.status.succeeded:
            break
    logging.info(
        f"Job Completed successfully. Finding the pod name that was generated from the k8s job to extract its log."
    )
    v1 = client.CoreV1Api()
    pod_from_job = (
        v1.list_namespaced_pod(
            namespace=job.metadata.namespace,
            label_selector=f"job-name={job.metadata.name}",
        )
        .items[0]
        .metadata.name
    )
    logging.info(
        f"Extracting pod {pod_from_job} log, base64 decoding it and feeding it as input to 'docker load'."
    )
    docker_client = docker.from_env()
    docker_client.images.load(
        b64decode(
            v1.read_namespaced_pod_log(
                name=pod_from_job, namespace=job.metadata.namespace
            )
        )
    )
    logging.info(f"Image pulled successfully.")
    job.spec.ttl_seconds_after_finished = 1
    job.metadata.resource_version = None
    batchv1.patch_namespaced_job(
        name=job.metadata.name, namespace=job.metadata.namespace, body=job
    )
    logging.info(f"Deleted k8s Job (and corresponding completed pod).")
    logging.info(
        f"You can find the image locally by executing 'docker images {image}'."
    )


def main():
    args = arguments_parsing()
    global logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    config.load_kube_config()
    cluster, image, container, node, pod, namespace = get_pod_data(args)
    clone_image(cluster, image, container, node, pod, namespace)


if __name__ == "__main__":
    main()
