# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os

SEAHORSE_BASE_URL = os.getenv("SEAHORSE_BASE_URL", "")
SEAHORSE_API_KEY = os.getenv("SEAHORSE_API_KEY", "")
SEAHORSE_INDEX_NAME = os.getenv("SEAHORSE_INDEX_NAME", "embedding")
SEAHORSE_EMBEDDING_MODE = os.getenv("SEAHORSE_EMBEDDING_MODE", "builtin")

EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-base-en-v1.5")
TEI_EMBEDDING_ENDPOINT = os.getenv("TEI_EMBEDDING_ENDPOINT", "")
HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACEHUB_API_TOKEN", "")
