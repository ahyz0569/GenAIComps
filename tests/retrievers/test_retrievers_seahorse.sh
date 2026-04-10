#!/bin/bash
# Copyright (C) 2026 Dnotitia
# SPDX-License-Identifier: Apache-2.0

set -x

IMAGE_REPO=${IMAGE_REPO:-"opea"}
export REGISTRY=${IMAGE_REPO}
export TAG="comps"
echo "REGISTRY=IMAGE_REPO=${IMAGE_REPO}"
echo "TAG=${TAG}"

WORKPATH=$(dirname "$PWD")
LOG_PATH="$WORKPATH/tests"
export host_ip=$(hostname -I | awk '{print $1}')
service_name="retriever-seahorse"

function build_docker_images() {
    cd $WORKPATH
    docker build --no-cache -t ${REGISTRY:-opea}/retriever:${TAG:-latest} \
        --build-arg https_proxy=$https_proxy \
        --build-arg http_proxy=$http_proxy \
        -f comps/retrievers/src/Dockerfile .
    if [ $? -ne 0 ]; then
        echo "opea/retriever built fail"
        exit 1
    else
        echo "opea/retriever built successful"
    fi
}

function start_service() {
    export RETRIEVER_PORT=7000
    export LOGFLAG=True

    cd $WORKPATH/comps/retrievers/deployment/docker_compose
    docker compose -f compose.yaml up ${service_name} -d \
        > ${LOG_PATH}/start_services_with_compose.log

    sleep 30s
}

function validate_microservice() {
    export PATH="${HOME}/miniforge3/bin:$PATH"
    source activate
    URL="http://${host_ip}:$RETRIEVER_PORT/v1/retrieval"

    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        -d '{"text":"test query","embedding":[0.1],"k":3}' \
        -H 'Content-Type: application/json' "$URL")
    if [ "$HTTP_STATUS" -eq 200 ]; then
        echo "[ retriever ] HTTP status is 200. Checking content..."
        local CONTENT=$(curl -s -X POST \
            -d '{"text":"test query","embedding":[0.1],"k":3}' \
            -H 'Content-Type: application/json' "$URL" \
            | tee ${LOG_PATH}/retriever.log)

        if echo "$CONTENT" | grep -q "retrieved_docs"; then
            echo "[ retriever ] Content is as expected."
        else
            echo "[ retriever ] Content does not match the expected result: $CONTENT"
            docker logs ${service_name} >> ${LOG_PATH}/retriever.log
            exit 1
        fi
    else
        echo "[ retriever ] HTTP status is not 200. Received status was $HTTP_STATUS"
        docker logs ${service_name} >> ${LOG_PATH}/retriever.log
        exit 1
    fi
}

function stop_docker() {
    cd $WORKPATH/comps/retrievers/deployment/docker_compose
    docker compose -f compose.yaml down --remove-orphans
}

function main() {
    stop_docker
    build_docker_images

    start_service
    validate_microservice

    stop_docker
    echo y | docker system prune
}

main
