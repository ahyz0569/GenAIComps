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
service_name="dataprep-seahorse-server"

function build_docker_images() {
    cd $WORKPATH
    docker build --no-cache -t ${REGISTRY:-opea}/dataprep:${TAG:-latest} \
        --build-arg https_proxy=$https_proxy \
        --build-arg http_proxy=$http_proxy \
        -f comps/dataprep/src/Dockerfile .
    if [ $? -ne 0 ]; then
        echo "opea/dataprep built fail"
        exit 1
    else
        echo "opea/dataprep built successful"
    fi
}

function start_service() {
    export DATAPREP_PORT=5000
    export LOGFLAG=True

    cd $WORKPATH/comps/dataprep/deployment/docker_compose
    docker compose -f compose.yaml up dataprep-seahorse -d \
        > ${LOG_PATH}/start_services_with_compose.log

    sleep 30s
}

function validate_microservice() {
    export PATH="${HOME}/miniforge3/bin:$PATH"
    source activate
    URL="http://${host_ip}:$DATAPREP_PORT"

    # Test ingest
    echo "Testing file ingestion..."
    echo "This is a test document for Seahorse Cloud integration." > /tmp/test_seahorse.txt
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        -F "files=@/tmp/test_seahorse.txt" "$URL/v1/dataprep/ingest")
    if [ "$HTTP_STATUS" -eq 200 ]; then
        echo "[ dataprep ingest ] HTTP status is 200."
    else
        echo "[ dataprep ingest ] HTTP status is not 200. Received status was $HTTP_STATUS"
        docker logs ${service_name} >> ${LOG_PATH}/dataprep.log
        exit 1
    fi

    # Test get files
    echo "Testing get files..."
    CONTENT=$(curl -s -X POST "$URL/v1/dataprep/get" \
        | tee ${LOG_PATH}/dataprep.log)
    echo "[ dataprep get ] Response: $CONTENT"

    # Test delete
    echo "Testing delete all..."
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        -H "Content-Type: application/json" \
        -d '{"file_path": "all"}' "$URL/v1/dataprep/delete")
    if [ "$HTTP_STATUS" -eq 200 ]; then
        echo "[ dataprep delete ] HTTP status is 200."
    else
        echo "[ dataprep delete ] HTTP status is not 200. Received status was $HTTP_STATUS"
        docker logs ${service_name} >> ${LOG_PATH}/dataprep.log
        exit 1
    fi

    rm -f /tmp/test_seahorse.txt
}

function stop_docker() {
    cd $WORKPATH/comps/dataprep/deployment/docker_compose
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
