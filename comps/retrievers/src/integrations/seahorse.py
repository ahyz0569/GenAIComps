# Copyright (C) 2026 Dnotitia
# SPDX-License-Identifier: Apache-2.0

import asyncio
import os

import requests
from fastapi import HTTPException
from langchain_community.embeddings import HuggingFaceInferenceAPIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from seahorse_vector_store import SeahorseVectorStore, SearchMode

from comps import CustomLogger, EmbedDoc, OpeaComponent, OpeaComponentRegistry, ServiceType

from .config import (
    EMBED_MODEL,
    HF_TOKEN,
    SEAHORSE_API_KEY,
    SEAHORSE_BASE_URL,
    SEAHORSE_EMBEDDING_MODE,
    SEAHORSE_INDEX_NAME,
    SEAHORSE_SEARCH_MODE,
    TEI_EMBEDDING_ENDPOINT,
)

logger = CustomLogger("seahorse_retrievers")
logflag = os.getenv("LOGFLAG", False)

SEARCH_MODE_MAP = {
    "dense": SearchMode.DENSE,
    "sparse": SearchMode.SPARSE,
    "hybrid": SearchMode.HYBRID,
}


@OpeaComponentRegistry.register("OPEA_RETRIEVER_SEAHORSE")
class OpeaSeahorseRetriever(OpeaComponent):
    """Seahorse Cloud managed vector search retriever.

    Connects to Seahorse Cloud API Gateway via langchain-seahorse SDK.
    SaaS — no self-hosted infrastructure required.

    Embedding mode (controlled by SEAHORSE_EMBEDDING_MODE env var):
    - "builtin": Uses Seahorse server-side embeddings for both indexing and search.
                 Calls similarity_search(query=text) so the server embeds the query.
    - "external": Initializes the SDK with a TEI or local HuggingFace embedder, but query-time
                  retrieval uses similarity_search_by_vector(embedding=vec) with the pre-computed
                  embedding passed in from the caller. External mode is always dense-only.
    """

    def __init__(self, name: str, description: str, config: dict = None):
        super().__init__(name, ServiceType.RETRIEVER.name.lower(), description, config)
        self.use_builtin = SEAHORSE_EMBEDDING_MODE == "builtin"
        self.embedder = self._initialize_embedder()
        self.search_mode = self._initialize_search_mode()
        self.vectorstore = self._initialize_vectorstore()
        health_status = self.check_health()
        if not health_status:
            logger.error("OpeaSeahorseRetriever health check failed.")

    def _initialize_embedder(self):
        if self.use_builtin:
            if logflag:
                logger.info("[ init embedder ] Using Seahorse built-in embeddings (SEAHORSE_EMBEDDING_MODE=builtin)")
            return None

        if TEI_EMBEDDING_ENDPOINT:
            if logflag:
                logger.info(f"[ init embedder ] TEI_EMBEDDING_ENDPOINT: {TEI_EMBEDDING_ENDPOINT}")
            if not HF_TOKEN:
                raise HTTPException(
                    status_code=400,
                    detail="You MUST offer the `HF_TOKEN` when using `TEI_EMBEDDING_ENDPOINT`.",
                )

            response = requests.get(TEI_EMBEDDING_ENDPOINT + "/info")
            if response.status_code != 200:
                raise HTTPException(
                    status_code=400,
                    detail=f"TEI embedding endpoint {TEI_EMBEDDING_ENDPOINT} is not available.",
                )
            model_id = response.json()["model_id"]
            return HuggingFaceInferenceAPIEmbeddings(
                api_key=HF_TOKEN, model_name=model_id, api_url=TEI_EMBEDDING_ENDPOINT
            )

        if logflag:
            logger.info(f"[ init embedder ] LOCAL EMBED_MODEL: {EMBED_MODEL}")

        return HuggingFaceEmbeddings(model_name=EMBED_MODEL)

    def _initialize_search_mode(self) -> SearchMode:
        requested_mode = SEARCH_MODE_MAP.get(SEAHORSE_SEARCH_MODE, SearchMode.HYBRID)
        if not self.use_builtin and requested_mode != SearchMode.DENSE:
            logger.warning(
                "[ init ] external embedding mode only supports dense search. "
                f"Overriding SEAHORSE_SEARCH_MODE={SEAHORSE_SEARCH_MODE} to dense."
            )
            return SearchMode.DENSE
        return requested_mode

    def _initialize_vectorstore(self) -> SeahorseVectorStore:
        if logflag:
            logger.info(f"[ init ] SEAHORSE_BASE_URL: {SEAHORSE_BASE_URL}")
            logger.info(f"[ init ] SEAHORSE_EMBEDDING_MODE: {SEAHORSE_EMBEDDING_MODE}")
        kwargs = {
            "api_key": SEAHORSE_API_KEY,
            "base_url": SEAHORSE_BASE_URL,
            "dense_column": SEAHORSE_INDEX_NAME,
        }
        if self.use_builtin:
            kwargs["use_builtin_embedding"] = True
        else:
            kwargs["embedding"] = self.embedder
            kwargs["use_builtin_embedding"] = False
        return SeahorseVectorStore(**kwargs)

    def check_health(self) -> bool:
        """Check Seahorse Cloud connectivity via indexed-row-count API."""
        if logflag:
            logger.info("[ check health ] start to check health of Seahorse Cloud")
        try:
            result = self.vectorstore._client.get_indexed_row_count()
            if logflag:
                logger.info(
                    f"[ check health ] Seahorse Cloud connected. "
                    f"total_row_count={result.get('total_row_count', 'N/A')}"
                )
            return True
        except Exception as e:
            logger.error(f"[ check health ] Failed to connect to Seahorse Cloud: {e}")
            return False

    @staticmethod
    def _passes_score_threshold(score: float, threshold: float, *, is_distance: bool) -> bool:
        """Match score semantics returned by the Seahorse SDK.

        Dense vector searches return distance values, where lower is better.
        Sparse and hybrid searches return similarity scores, where higher is better.
        """
        if is_distance:
            return score <= threshold
        return score >= threshold

    async def _search_builtin(self, input: EmbedDoc) -> list:
        """builtin mode: text query → server embeds with same built-in model → search."""
        if input.search_type == "similarity_score_threshold":
            docs_and_scores = await asyncio.to_thread(
                self.vectorstore.similarity_search_with_score,
                query=input.text,
                k=input.k,
                retrieval_mode=self.search_mode,
            )
            uses_distance = self.search_mode == SearchMode.DENSE
            return [
                doc
                for doc, score in docs_and_scores
                if self._passes_score_threshold(score, input.score_threshold, is_distance=uses_distance)
            ]

        return await asyncio.to_thread(
            self.vectorstore.similarity_search,
            query=input.text,
            k=input.k,
            retrieval_mode=self.search_mode,
        )

    async def _search_external(self, input: EmbedDoc) -> list:
        """external mode: use pre-computed OPEA TEI embedding vector for search.

        Note: similarity_search_by_vector() does not accept retrieval_mode parameter.
        External embedding mode is always dense-only, regardless of SEAHORSE_SEARCH_MODE.
        """
        if input.search_type == "similarity_score_threshold":
            docs_and_scores = await asyncio.to_thread(
                self.vectorstore.similarity_search_by_vector_with_score,
                embedding=input.embedding,
                k=input.k,
            )
            return [
                doc
                for doc, score in docs_and_scores
                if self._passes_score_threshold(score, input.score_threshold, is_distance=True)
            ]

        return await asyncio.to_thread(
            self.vectorstore.similarity_search_by_vector,
            embedding=input.embedding,
            k=input.k,
        )

    async def invoke(self, input: EmbedDoc) -> list:
        """Search Seahorse Cloud for similar documents.

        Args:
            input (EmbedDoc): Query with embedding vector, search_type, k, etc.
        Returns:
            list: Retrieved documents.
        """
        if logflag:
            logger.info(input)

        if input.search_type == "mmr":
            logger.info("[ invoke ] MMR not supported by Seahorse, falling back to similarity search")

        if self.use_builtin:
            search_res = await self._search_builtin(input)
        else:
            search_res = await self._search_external(input)

        if logflag:
            logger.info(f"[ invoke ] retrieve result: {search_res}")

        return search_res
