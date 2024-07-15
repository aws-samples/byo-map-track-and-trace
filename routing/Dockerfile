# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

FROM public.ecr.aws/lambda/python:3.12

ARG HTTPS_PROXY
ARG POETRY_VERSION=1.8.3
ENV PIP_ROOT_USER_ACTION=ignore

# set the pip cache location
ENV PIP_CACHE_DIR=/tmp/pip-cache

# set the poetry cache
ENV POETRY_CACHE_DIR=/tmp/poetry-cache

RUN \
# Create a new location for the pip cache
    mkdir /tmp/pip-cache && \
# Upgrade pip (required by cryptography v3.4 and above, which is a dependency of poetry)
    pip install --upgrade pip && \
# Create a new location for the poetry cache
    mkdir $POETRY_CACHE_DIR && \
# Install poetry and dependencies (including wheel, which will add support for binaries)
    pip install poetry==$POETRY_VERSION poetry-plugin-export wheel

COPY pyproject.toml ${LAMBDA_TASK_ROOT}
COPY poetry.lock ${LAMBDA_TASK_ROOT}

# Install the specified packages
# inspired by https://github.com/aws/aws-cdk/blob/main/packages/%40aws-cdk/aws-lambda-python-alpha/lib/packaging.ts
RUN \
	poetry export --with-credentials --without dev --format requirements.txt --output requirements.txt && \
	pip install -r requirements.txt && \
# Ensure no temporary files remain in the caches
    rm -rf $PIP_CACHE_DIR/* $POETRY_CACHE_DIR/*

# Copy function code
COPY . ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler (could also be done as a parameter override outside of the Dockerfile)
CMD [ "routing.lambda_handler.handle" ]
