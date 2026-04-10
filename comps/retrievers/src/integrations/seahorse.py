# Copyright (C) 2026 Dnotitia
# SPDX-License-Identifier: Apache-2.0

import asyncio
import os

from seahorse_vector_store import SeahorseVectorStore, SearchMode

from comps import CustomLogger, EmbedDoc, OpeaComponent, OpeaComponentRegistry, ServiceType

from .config import (
    SEAHORSE_API_KEY,
    SEAHORSE_BASE_URL,
    SEAHORSE_EMBEDDING_MODE,
    SEAHORSE_INDEX_NAME,
    SEAHORSE_SEARCH_MODE,
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
    - "external": Uses OPEA TEI embeddings. Calls similarity_search_by_vector(embedding=vec)
                  with the pre-computed embedding from OPEA's embedding service.
    """

    def __init__(self, name: str, description: str, config: dict = None):
        super().__init__(name, ServiceType.RETRIEVER.name.lower(), description, config)
        self.use_builtin = SEAHORSE_EMBEDDING_MODE == "builtin"
        self.search_mode = SEARCH_MODE_MAP.get(SEAHORSE_SEARCH_MODE, SearchMode.HYBRID)
        self.vectorstore = self._initialize_vectorstore()
        health_status = self.check_health()
        if not health_status:
            logger.error("OpeaSeahorseRetriever health check failed.")

    def _initialize_vectorstore(self) -> SeahorseVectorStore:
        if logflag:
            logger.info(f"[ init ] SEAHORSE_BASE_URL: {SEAHORSE_BASE_URL}")
            logger.info(f"[ init ] SEAHORSE_EMBEDDING_MODE: {SEAHORSE_EMBEDDING_MODE}")
        return SeahorseVectorStore(
            api_key=SEAHORSE_API_KEY,
            base_url=SEAHORSE_BASE_URL,
            dense_column=SEAHORSE_INDEX_NAME,
            use_builtin_embedding=self.use_builtin,
        )

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

    async def _search_builtin(self, input: EmbedDoc) -> list:
        """builtin mode: text query → server embeds with same built-in model → search."""
        if input.search_type == "similarity_score_threshold":
            docs_and_scores = await asyncio.to_thread(
                self.vectorstore.similarity_search_with_score,
                query=input.text,
                k=input.k,
                retrieval_mode=self.search_mode,
            )
            return [doc for doc, score in docs_and_scores if score >= input.score_threshold]

        return await asyncio.to_thread(
            self.vectorstore.similarity_search,
            query=input.text,
            k=input.k,
            retrieval_mode=self.search_mode,
        )

    async def _search_external(self, input: EmbedDoc) -> list:
        """external mode: use pre-computed OPEA TEI embedding vector for search.

        Note: similarity_search_by_vector() does not accept retrieval_mode parameter.
        Vector search is always dense-only (the vector is pre-computed externally).
        """
        if input.search_type == "similarity_score_threshold":
            docs_and_scores = await asyncio.to_thread(
                self.vectorstore.similarity_search_by_vector_with_score,
                embedding=input.embedding,
                k=input.k,
            )
            return [doc for doc, score in docs_and_scores if score >= input.score_threshold]

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
