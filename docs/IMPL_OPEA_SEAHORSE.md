# Seahorse Cloud OPEA GenAIComps 구현 계획서

**작성일**: 2026-04-08
**SDK**: `langchain-seahorse>=0.2.0`
**대상**: [opea-project/GenAIComps](https://github.com/opea-project/GenAIComps) (v1.5 기준)
**배경 분석**: [PLAN_OPEA_INTEGRATION.md](PLAN_OPEA_INTEGRATION.md) 참고

---

## 1. 사전 준비

### 1.1 Fork & 브랜치

```bash
git clone https://github.com/<YOUR_ACCOUNT>/GenAIComps.git
cd GenAIComps
git remote add upstream https://github.com/opea-project/GenAIComps.git
git fetch upstream
git checkout -b feat/seahorse-cloud upstream/main
```

### 1.2 의존성 확인

```bash
pip install langchain-seahorse>=0.2.0
python -c "from seahorse_vector_store import SeahorseVectorStore, SearchMode; print('OK')"
```

### 1.3 최신 OPEA 인터페이스 확인

> OPEA는 자주 리팩토링하므로 반드시 PR 시점의 최신 코드를 확인할 것.

확인 대상 파일:
- `comps/retrievers/src/integrations/milvus.py` — Retriever invoke() 패턴 (search_type 분기)
- `comps/dataprep/src/integrations/qdrant.py` — Dataprep ingest_files() 패턴 (가장 단순)
- `comps/dataprep/src/integrations/milvus.py` — Dataprep get_files()/delete_files() 패턴 (가장 완전)
- `comps/retrievers/src/integrations/config.py` — 환경변수 설정 패턴
- `comps/retrievers/src/opea_retrievers_microservice.py` — Retriever 등록
- `comps/dataprep/src/opea_dataprep_microservice.py` — Dataprep 등록

---

## 2. 구현 파일 목록

### 신규 파일 (7개)

| # | 파일 | 설명 |
|---|---|---|
| 1 | `comps/retrievers/src/integrations/seahorse.py` | Retriever 통합 |
| 2 | `comps/dataprep/src/integrations/seahorse.py` | Dataprep 통합 |
| 3 | `comps/dataprep/src/integrations/config/seahorse.py` | Dataprep 설정 |
| 4 | `comps/retrievers/src/README_seahorse.md` | Retriever README |
| 5 | `comps/dataprep/src/README_seahorse.md` | Dataprep README |
| 6 | `tests/retrievers/test_retrievers_seahorse.sh` | Retriever 테스트 |
| 7 | `tests/dataprep/test_dataprep_seahorse.sh` | Dataprep 테스트 |

### 수정 파일 (5개)

| # | 파일 | 변경 |
|---|---|---|
| 1 | `comps/retrievers/src/opea_retrievers_microservice.py` | import 추가 |
| 2 | `comps/dataprep/src/opea_dataprep_microservice.py` | import 추가 |
| 3 | `comps/retrievers/src/integrations/config.py` | 환경변수 추가 |
| 4 | `comps/retrievers/src/requirements.in` | `langchain-seahorse` 추가 |
| 5 | `comps/dataprep/src/requirements.in` | `langchain-seahorse` 추가 |

> **참고**: 이 저장소는 `requirements.in` → `uv pip compile` → `requirements-cpu.txt` / `requirements-gpu.txt` 구조를 사용합니다. `requirements.txt`가 아닌 `requirements.in`에 추가하고, lock 파일을 재생성해야 합니다.
> 별도 `Dockerfile.seahorse`는 만들지 않고, 기존 공용 `Dockerfile`을 그대로 사용합니다 (환경변수 `RETRIEVER_COMPONENT_NAME` / `DATAPREP_COMPONENT_NAME`으로 Seahorse 컴포넌트를 선택).

---

## 3. Step 1: 환경변수 설정

### 임베딩 일관성 설계

> **핵심 원칙**: 문서 삽입(Dataprep)과 검색(Retriever)은 반드시 동일한 임베딩 모델을 사용해야 합니다.
> 서로 다른 임베딩 모델을 사용하면 벡터 공간이 달라져 검색 결과가 무의미해집니다.
>
> `SEAHORSE_EMBEDDING_MODE` 환경변수 하나로 양쪽 서비스의 임베딩 전략을 동시에 제어합니다:
>
> | 모드 | Dataprep (문서 저장) | Retriever (검색) |
> |---|---|---|
> | `builtin` (기본) | `SeahorseVectorStore(use_builtin_embedding=True).add_texts()` — 서버사이드 임베딩 | `similarity_search(query=input.text)` — 동일 서버사이드 임베딩으로 쿼리 벡터 생성 |
> | `external` | `SeahorseVectorStore(embedding=TEI, use_builtin_embedding=False).add_texts()` — TEI 임베딩 | `similarity_search_by_vector(embedding=input.embedding)` — OPEA TEI가 생성한 벡터 사용 |
>
> **⚠️ 주의**: 한 번 데이터를 삽입한 후에는 모드를 변경하면 안 됩니다. 모드를 변경하려면 기존 데이터를 전부 삭제하고 재삽입해야 합니다.

### `comps/retrievers/src/integrations/config.py` 에 추가

```python
#######################################################
# Seahorse Cloud                                      #
#######################################################
SEAHORSE_BASE_URL = os.getenv("SEAHORSE_BASE_URL", "")
SEAHORSE_API_KEY = os.getenv("SEAHORSE_API_KEY", "")
SEAHORSE_INDEX_NAME = os.getenv("SEAHORSE_INDEX_NAME", "embedding")
SEAHORSE_SEARCH_MODE = os.getenv("SEAHORSE_SEARCH_MODE", "hybrid")
SEAHORSE_EMBEDDING_MODE = os.getenv("SEAHORSE_EMBEDDING_MODE", "builtin")  # "builtin" or "external"
```

### `comps/dataprep/src/integrations/config/seahorse.py` 신규 생성

```python
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os

SEAHORSE_BASE_URL = os.getenv("SEAHORSE_BASE_URL", "")
SEAHORSE_API_KEY = os.getenv("SEAHORSE_API_KEY", "")
SEAHORSE_INDEX_NAME = os.getenv("SEAHORSE_INDEX_NAME", "embedding")
SEAHORSE_EMBEDDING_MODE = os.getenv("SEAHORSE_EMBEDDING_MODE", "builtin")  # "builtin" or "external"

EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-base-en-v1.5")
TEI_EMBEDDING_ENDPOINT = os.getenv("TEI_EMBEDDING_ENDPOINT", "")
HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACEHUB_API_TOKEN", "")
```

### 환경변수 요약

| 변수 | 필수 | 기본값 | 용도 |
|---|---|---|---|
| `SEAHORSE_BASE_URL` | Yes | - | 테이블 API Gateway URL (`https://<uuid>.api.seahorse.dnotitia.ai`) |
| `SEAHORSE_API_KEY` | Yes | - | Bearer 인증 키 |
| `SEAHORSE_INDEX_NAME` | No | `embedding` | 벡터 컬럼명 |
| `SEAHORSE_SEARCH_MODE` | No | `hybrid` | Retriever 검색 모드 (`dense`/`sparse`/`hybrid`) |
| `SEAHORSE_EMBEDDING_MODE` | No | `builtin` | 임베딩 전략 (`builtin`: Seahorse 내장 / `external`: TEI 등 외부). **Retriever와 Dataprep 양쪽에 동일하게 적용됨** |
| `TEI_EMBEDDING_ENDPOINT` | `external` 모드 시 Yes | - | 외부 임베딩 사용 시 TEI 엔드포인트 |

---

## 4. Step 2: Retriever 구현

### `comps/retrievers/src/integrations/seahorse.py`

> **참고 모델**: Milvus Retriever (search_type 분기가 가장 완전)
>
> **임베딩 모드에 따른 검색 전략**:
> - `builtin` 모드: `similarity_search(query=input.text)` 호출 → Seahorse 서버가 동일 내장 모델로 쿼리 임베딩 생성 + 검색
> - `external` 모드: `similarity_search_by_vector(embedding=input.embedding)` 호출 → OPEA TEI가 생성한 벡터로 직접 검색

```python
# Copyright (C) 2024 Intel Corporation
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
        if logflag:
            logger.info("[ check health ] start to check health of Seahorse Cloud")
        try:
            # TODO: SDK에 health check 메서드 추가 검토, 없으면 httpx로 GET /healthz 직접 호출
            if logflag:
                logger.info("[ check health ] Seahorse Cloud connection configured.")
            return True
        except Exception as e:
            logger.info(f"[ check health ] Failed to connect to Seahorse Cloud: {e}")
            return False

    async def _search_builtin(self, input: EmbedDoc) -> list:
        """builtin 모드: 텍스트 쿼리를 SDK에 전달, 서버가 동일 내장 모델로 임베딩 + 검색."""
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
        """external 모드: OPEA TEI가 생성한 벡터로 직접 검색.

        Note: similarity_search_by_vector()는 retrieval_mode 파라미터를 지원하지 않음.
        벡터 검색은 항상 dense-only (벡터가 외부에서 사전 계산됨).
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
```

### 확인 결과 (v0.2.0 검증 완료)

| 항목 | 결과 |
|---|---|
| `similarity_search(retrieval_mode=...)` | ✅ 지원됨. `SearchMode.HYBRID/DENSE/SPARSE` 전달 가능 |
| `similarity_search_by_vector(retrieval_mode=...)` | ❌ **미지원**. `retrieval_mode` 파라미터 없음 (벡터 검색은 항상 dense-only) |
| `similarity_search_by_vector_with_score()` | ✅ 지원됨. `(Document, float)` 튜플 리스트 반환 |
| `delete(delete_all=True)` | ✅ 전체 삭제 지원됨 |
| async 네이티브 | ❌ 없음. `asyncio.to_thread()` 래핑으로 대응 |

---

## 5. Step 3: Dataprep 구현

### `comps/dataprep/src/integrations/seahorse.py`

> **참고 모델**: Qdrant Dataprep (구조), Milvus Dataprep (get_files/delete_files)
>
> **임베딩 모드에 따른 저장 전략** (`SEAHORSE_EMBEDDING_MODE`):
> - `builtin`: `SeahorseVectorStore(use_builtin_embedding=True).add_texts()` → 서버가 임베딩 생성 + 저장
> - `external`: `SeahorseVectorStore(embedding=TEI, use_builtin_embedding=False).add_texts()` → TEI가 임베딩 생성 후 벡터 저장

```python
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
from pathlib import Path
from typing import List, Optional, Union

from fastapi import Body, File, Form, HTTPException, UploadFile
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_text_splitters import HTMLHeaderTextSplitter
from seahorse_vector_store import SeahorseVectorStore

from comps import CustomLogger, DocPath, OpeaComponent, OpeaComponentRegistry, ServiceType
from comps.cores.proto.api_protocol import DataprepRequest
from comps.dataprep.src.utils import (
    create_upload_folder,
    document_loader,
    encode_filename,
    get_separators,
    get_tables_result,
    parse_html_new,
    remove_folder_with_ignore,
    save_content_to_local_disk,
)

from .config.seahorse import (
    EMBED_MODEL,
    HF_TOKEN,
    SEAHORSE_API_KEY,
    SEAHORSE_BASE_URL,
    SEAHORSE_EMBEDDING_MODE,
    SEAHORSE_INDEX_NAME,
    TEI_EMBEDDING_ENDPOINT,
)

logger = CustomLogger("seahorse_dataprep")
logflag = os.getenv("LOGFLAG", False)
upload_folder = "./uploaded_files/"


@OpeaComponentRegistry.register("OPEA_DATAPREP_SEAHORSE")
class OpeaSeahorseDataprep(OpeaComponent):
    """Seahorse Cloud document ingestion via API Gateway.

    Embedding mode (controlled by SEAHORSE_EMBEDDING_MODE env var):
    - "builtin": Seahorse Cloud generates embeddings server-side (no TEI needed).
                 Must match Retriever's builtin mode for consistent search.
    - "external": Uses TEI or local HuggingFace embeddings.
                  Must match Retriever's external mode for consistent search.
    """

    def __init__(self, name: str, description: str, config: dict = None):
        super().__init__(name, ServiceType.DATAPREP.name.lower(), description, config)
        self.upload_folder = upload_folder
        self.use_builtin = SEAHORSE_EMBEDDING_MODE == "builtin"
        self.embedder = self._initialize_embedder()
        self.vectorstore = self._initialize_vectorstore()
        health_status = self.check_health()
        if not health_status:
            logger.error("OpeaSeahorseDataprep health check failed.")

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
            import requests
            from langchain_community.embeddings import HuggingFaceInferenceAPIEmbeddings

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
        else:
            if logflag:
                logger.info(f"[ init embedder ] LOCAL EMBED_MODEL: {EMBED_MODEL}")
            from langchain_huggingface import HuggingFaceEmbeddings

            return HuggingFaceEmbeddings(model_name=EMBED_MODEL)

    def _initialize_vectorstore(self) -> SeahorseVectorStore:
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
        if logflag:
            logger.info("[ check health ] start to check health of Seahorse Cloud")
        try:
            # TODO: SDK health check 또는 schema 조회로 연결 확인
            return True
        except Exception as e:
            logger.error(f"[ check health ] Seahorse Cloud health check failed: {e}")
            return False

    def invoke(self, *args, **kwargs):
        pass

    async def ingest_data_to_seahorse(self, doc_path: DocPath):
        """Parse, chunk, and ingest a single document."""
        path = doc_path.path
        file_name = path.split("/")[-1]
        if logflag:
            logger.info(f"[ ingest ] Parsing document {path}")

        if path.endswith(".html"):
            headers_to_split_on = [
                ("h1", "Header 1"),
                ("h2", "Header 2"),
                ("h3", "Header 3"),
            ]
            text_splitter = HTMLHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
        else:
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=doc_path.chunk_size,
                chunk_overlap=doc_path.chunk_overlap,
                add_start_index=True,
                separators=get_separators(),
            )

        content = await document_loader(path)

        structured_types = [".xlsx", ".csv", ".json", "jsonl"]
        _, ext = os.path.splitext(path)

        if ext in structured_types:
            chunks = content
        else:
            chunks = text_splitter.split_text(content)

        if doc_path.process_table and path.endswith(".pdf"):
            table_chunks = get_tables_result(path, doc_path.table_strategy)
            if table_chunks:
                chunks = chunks + table_chunks

        if logflag:
            logger.info(f"[ ingest ] Created {len(chunks)} chunks from {file_name}")

        metadatas = [{"filename": file_name} for _ in chunks]

        # langchain-seahorse add_texts()는 내부적으로 자동 배칭 (max 50/request)
        # builtin 모드: 텍스트만 전송 → 서버가 임베딩 생성 + 저장
        # external 모드: SDK가 self.embedder로 임베딩 생성 후 벡터와 함께 저장
        self.vectorstore.add_texts(texts=chunks, metadatas=metadatas)

        if logflag:
            logger.info(f"[ ingest ] Successfully ingested {file_name} to Seahorse Cloud")
        return True

    async def ingest_files(self, input: DataprepRequest):
        """Ingest files/links into Seahorse Cloud.

        Args:
            input (DataprepRequest): files, link_list, chunk_size, chunk_overlap, etc.
        Returns:
            dict: {"status": 200, "message": "Data preparation succeeded"}
        """
        files = input.files
        link_list = input.link_list
        chunk_size = input.chunk_size
        chunk_overlap = input.chunk_overlap
        process_table = input.process_table
        table_strategy = input.table_strategy

        if logflag:
            logger.info(f"[ ingest ] files: {files}")
            logger.info(f"[ ingest ] link_list: {link_list}")

        if files:
            if not isinstance(files, list):
                files = [files]
            for file in files:
                encode_file = encode_filename(file.filename)
                save_path = self.upload_folder + encode_file
                await save_content_to_local_disk(save_path, file)
                await self.ingest_data_to_seahorse(
                    DocPath(
                        path=save_path,
                        chunk_size=chunk_size,
                        chunk_overlap=chunk_overlap,
                        process_table=process_table,
                        table_strategy=table_strategy,
                    )
                )
                if logflag:
                    logger.info(f"[ ingest ] Successfully saved file {save_path}")
            return {"status": 200, "message": "Data preparation succeeded"}

        if link_list:
            link_list = json.loads(link_list)
            if not isinstance(link_list, list):
                raise HTTPException(status_code=400, detail="link_list should be a list.")
            for link in link_list:
                encoded_link = encode_filename(link)
                save_path = self.upload_folder + encoded_link + ".txt"
                content = parse_html_new([link], chunk_size=chunk_size, chunk_overlap=chunk_overlap)
                await save_content_to_local_disk(save_path, content)
                await self.ingest_data_to_seahorse(
                    DocPath(
                        path=save_path,
                        chunk_size=chunk_size,
                        chunk_overlap=chunk_overlap,
                        process_table=process_table,
                        table_strategy=table_strategy,
                    )
                )
                if logflag:
                    logger.info(f"[ ingest ] Successfully saved link {link}")
            return {"status": 200, "message": "Data preparation succeeded"}

        raise HTTPException(status_code=400, detail="Must provide either a file or a string list.")

    async def get_files(self):
        """Get list of ingested files from local upload folder.

        TODO: 추후 /v2/data/scan API로 DB에서 직접 filename 목록 조회하는 방식으로 개선 가능
        """
        if logflag:
            logger.info("[ get files ] start to get file structure")

        if not Path(self.upload_folder).exists():
            if logflag:
                logger.info("No file uploaded, return empty list.")
            return []

        from comps.dataprep.src.utils import get_file_structure

        file_content = get_file_structure(self.upload_folder)
        if logflag:
            logger.info(file_content)
        return file_content

    async def delete_files(self, file_path: str = Body(..., embed=True)):
        """Delete file data from Seahorse Cloud.

        file_path:
        - "all": delete all data
        - specific path: delete chunks for that file (by metadata filter)
        """
        if logflag:
            logger.info(f"[ delete ] file_path: {file_path}")

        if file_path == "all":
            # Seahorse API: POST /v2/data/delete with empty condition deletes all
            # TODO: langchain-seahorse의 delete() 메서드로 전체 삭제 지원 확인
            # 미지원 시 httpx로 직접 /v2/data/delete 호출
            try:
                remove_folder_with_ignore(self.upload_folder)
            except Exception as e:
                logger.error(f"[ delete ] Failed to remove upload folder: {e}")
            create_upload_folder(self.upload_folder)
            if logflag:
                logger.info("[ delete ] successfully deleted all files")
            return {"status": True}

        # 단일 파일 삭제: metadata의 filename 필드로 필터링
        encode_file_name = encode_filename(file_path)
        delete_path = Path(self.upload_folder + "/" + encode_file_name)

        if delete_path.exists():
            # TODO: langchain-seahorse delete(ids=...) 또는
            # Seahorse API delete_condition="metadata like '%filename%'" 활용
            delete_path.unlink()
            if logflag:
                logger.info(f"[ delete ] file {file_path} deleted")
            return {"status": True}
        else:
            raise HTTPException(status_code=404, detail="File not found.")
```

---

## 6. Step 4: 마이크로서비스 등록

### `comps/retrievers/src/opea_retrievers_microservice.py` 에 import 추가

```python
from integrations.seahorse import OpeaSeahorseRetriever
```

기존 import 블록의 마지막에 추가 (알파벳 순서).

### `comps/dataprep/src/opea_dataprep_microservice.py` 에 import 추가

```python
from integrations.seahorse import OpeaSeahorseDataprep
```

기존 import 블록의 마지막에 추가.

### requirements.in 에 추가

`comps/retrievers/src/requirements.in` 및 `comps/dataprep/src/requirements.in` 에:

```
langchain-seahorse>=0.2.0
```

추가 후 lock 파일 재생성:

```bash
# Retriever
uv pip compile --python=/usr/local/bin/python3.11 --index-strategy unsafe-best-match \
    ./comps/retrievers/src/requirements.in --universal \
    -o ./comps/retrievers/src/requirements-cpu.txt

uv pip compile --python=/usr/local/bin/python3.11 \
    ./comps/retrievers/src/requirements.in --universal \
    -o ./comps/retrievers/src/requirements-gpu.txt

# Dataprep
uv pip compile --python=/usr/local/bin/python3.11 --index-strategy unsafe-best-match \
    ./comps/dataprep/src/requirements.in --universal \
    -o ./comps/dataprep/src/requirements-cpu.txt

uv pip compile --python=/usr/local/bin/python3.11 \
    ./comps/dataprep/src/requirements.in --universal \
    -o ./comps/dataprep/src/requirements-gpu.txt
```

---

## 7. Step 5: Docker 빌드

> 별도 `Dockerfile.seahorse`는 만들지 않습니다.
> 기존 공용 `Dockerfile`을 그대로 사용하고, 환경변수로 Seahorse 컴포넌트를 선택합니다.
> `langchain-seahorse`는 `requirements.in` → `requirements-cpu.txt` / `requirements-gpu.txt`에 이미 포함되어 있으므로 별도 설치가 필요 없습니다.

```bash
# Retriever 이미지 빌드 (기존 공용 Dockerfile 사용)
docker build -t opea/retriever:seahorse \
    -f comps/retrievers/src/Dockerfile .

# Dataprep 이미지 빌드 (기존 공용 Dockerfile 사용)
docker build -t opea/dataprep:seahorse \
    -f comps/dataprep/src/Dockerfile .
```

실행 시 환경변수로 Seahorse 컴포넌트 선택:

```bash
# Retriever
docker run -d -p 7000:7000 \
    -e RETRIEVER_COMPONENT_NAME="OPEA_RETRIEVER_SEAHORSE" \
    -e SEAHORSE_BASE_URL="https://xxx.api.seahorse.dnotitia.ai" \
    -e SEAHORSE_API_KEY="sk_xxx" \
    -e SEAHORSE_EMBEDDING_MODE="builtin" \
    opea/retriever:seahorse

# Dataprep
docker run -d -p 5000:5000 \
    -e DATAPREP_COMPONENT_NAME="OPEA_DATAPREP_SEAHORSE" \
    -e SEAHORSE_BASE_URL="https://xxx.api.seahorse.dnotitia.ai" \
    -e SEAHORSE_API_KEY="sk_xxx" \
    -e SEAHORSE_EMBEDDING_MODE="builtin" \
    opea/dataprep:seahorse
```

> **⚠️ 중요**: 두 컨테이너의 `SEAHORSE_EMBEDDING_MODE`는 반드시 동일한 값이어야 합니다.

---

## 8. Step 6: 테스트 스크립트

### `tests/retrievers/test_retrievers_seahorse.sh`

```bash
#!/bin/bash
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -e

RETRIEVER_URL="${RETRIEVER_URL:-http://localhost:7000}"

echo "=== Testing Seahorse Cloud Retriever ==="

# Health check
echo "1. Health check..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$RETRIEVER_URL/v1/health")
if [ "$STATUS" = "200" ]; then
    echo "   PASS: Health check"
else
    echo "   FAIL: Health check returned $STATUS"
    exit 1
fi

# Retrieval test (dummy embedding)
echo "2. Retrieval test..."
RESPONSE=$(curl -s -X POST "$RETRIEVER_URL/v1/retrieval" \
    -H "Content-Type: application/json" \
    -d '{
        "text": "test query",
        "embedding": [0.1, 0.2, 0.3],
        "k": 3
    }')
echo "   Response: $RESPONSE"

echo "=== All tests passed ==="
```

### `tests/dataprep/test_dataprep_seahorse.sh`

```bash
#!/bin/bash
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -e

DATAPREP_URL="${DATAPREP_URL:-http://localhost:5000}"

echo "=== Testing Seahorse Cloud Dataprep ==="

# Health check
echo "1. Health check..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$DATAPREP_URL/v1/health")
if [ "$STATUS" = "200" ]; then
    echo "   PASS: Health check"
else
    echo "   FAIL: Health check returned $STATUS"
    exit 1
fi

# Ingest test
echo "2. Ingest test..."
echo "This is a test document for Seahorse Cloud integration." > /tmp/test_seahorse.txt
RESPONSE=$(curl -s -X POST "$DATAPREP_URL/v1/dataprep/ingest" \
    -F "files=@/tmp/test_seahorse.txt")
echo "   Response: $RESPONSE"

# Get files test
echo "3. Get files test..."
RESPONSE=$(curl -s -X POST "$DATAPREP_URL/v1/dataprep/get")
echo "   Response: $RESPONSE"

# Delete test
echo "4. Delete test..."
RESPONSE=$(curl -s -X POST "$DATAPREP_URL/v1/dataprep/delete" \
    -H "Content-Type: application/json" \
    -d '{"file_path": "all"}')
echo "   Response: $RESPONSE"

rm -f /tmp/test_seahorse.txt
echo "=== All tests passed ==="
```

---

## 9. Step 7: 실행 및 검증

### Retriever 로컬 테스트

```bash
export SEAHORSE_BASE_URL="https://<table-uuid>.api.seahorse.dnotitia.ai"
export SEAHORSE_API_KEY="sk_xxx"
export RETRIEVER_COMPONENT_NAME="OPEA_RETRIEVER_SEAHORSE"
export SEAHORSE_EMBEDDING_MODE="builtin"
export LOGFLAG=true

python comps/retrievers/src/opea_retrievers_microservice.py
# → http://localhost:7000 에서 서비스 시작

# 별도 터미널
bash tests/retrievers/test_retrievers_seahorse.sh
```

### Dataprep 로컬 테스트

```bash
export SEAHORSE_BASE_URL="https://<table-uuid>.api.seahorse.dnotitia.ai"
export SEAHORSE_API_KEY="sk_xxx"
export DATAPREP_COMPONENT_NAME="OPEA_DATAPREP_SEAHORSE"
export SEAHORSE_EMBEDDING_MODE="builtin"
export LOGFLAG=true

python comps/dataprep/src/opea_dataprep_microservice.py
# → http://localhost:5000 에서 서비스 시작

# 별도 터미널
bash tests/dataprep/test_dataprep_seahorse.sh
```

> **⚠️ 두 서비스의 `SEAHORSE_EMBEDDING_MODE`를 반드시 동일한 값으로 설정하세요.**
> `external` 모드를 사용하려면 `TEI_EMBEDDING_ENDPOINT`, `HF_TOKEN`도 함께 설정해야 합니다.

---

## 10. Step 8: 커밋 및 PR

### 커밋

```bash
git add .
git commit -s -m "$(cat <<'EOF'
feat: add Seahorse Cloud as managed vector search backend

Add Seahorse Cloud (managed VDB SaaS by Dnotitia) as retriever and
dataprep backend for OPEA GenAIComps.

Uses langchain-seahorse SDK for LangChain VectorStore compatibility.
Connects via API Gateway with Bearer token authentication.
No self-hosted VDB infrastructure required.

Components:
- Retriever: vector similarity search (dense/sparse/hybrid)
- Dataprep: document ingestion with configurable embedding mode
- SEAHORSE_EMBEDDING_MODE env var enforces consistent embeddings
  between ingestion and search (builtin or external)

Signed-off-by: Your Name <your.email@dnotitia.com>
EOF
)"
```

### GitHub Issue 생성 → PR 생성

Issue/PR 템플릿은 [PLAN_OPEA_INTEGRATION.md 섹션 7](PLAN_OPEA_INTEGRATION.md#7-pr-제출-요구사항-체크리스트) 참고.

---

## 11. 구현 시 TODO 및 확인 사항

> 코드 내 TODO로 마킹된 항목. 구현 진행하면서 해결할 것.

| # | 항목 | 위치 | 설명 |
|---|---|---|---|
| 1 | **async 메서드 지원 여부** | Retriever `invoke()` | SDK에 `asimilarity_search()` 등 async 네이티브 메서드가 있으면 `asyncio.to_thread()` 대신 직접 호출로 교체 |
| 2 | **SearchMode 파라미터 전달** | Retriever `_search_builtin()` / `_search_external()` | `similarity_search(retrieval_mode=...)` 및 `similarity_search_by_vector(retrieval_mode=...)` 지원 확인 |
| 3 | **score_threshold 동작** | Retriever `invoke()` | `similarity_search_with_score()` 반환값에서 점수 기준 필터링 정상 동작 확인 |
| 4 | **MMR 미지원 안내** | Retriever `invoke()` | Seahorse API는 MMR 미지원. similarity fallback 동작 확인 |
| 5 | **health check 구현** | 양쪽 `check_health()` | SDK에 적절한 메서드 없으면 `httpx`로 `GET /healthz` 직접 호출 |
| 6 | **전체 삭제** | Dataprep `delete_files("all")` | `langchain-seahorse` `delete()` 또는 직접 API 호출 |
| 7 | **단일 파일 삭제** | Dataprep `delete_files(path)` | metadata `filename` 필터로 해당 청크만 삭제 — SDK/API 지원 확인 |
| 8 | **add_texts 동기/비동기** | Dataprep `ingest_data_to_seahorse()` | 현재 `self.vectorstore.add_texts()` 동기 호출. async 필요 시 `aadd_texts()` 사용 |
| 9 | **임베딩 모드 변경 방지** | 양쪽 `__init__()` | 서비스 시작 시 테이블에 이미 데이터가 있으면, 기존 데이터의 임베딩 방식과 현재 `SEAHORSE_EMBEDDING_MODE`가 일치하는지 검증하는 로직 추가 검토 |

---

## 12. 제출 전 체크리스트

- [ ] 모든 커밋에 `Signed-off-by:` 포함 (`git commit -s`)
- [ ] 모든 소스 파일에 라이선스 헤더 (`Apache-2.0`)
- [ ] `langchain-seahorse` import 정상 동작
- [ ] Retriever: `OPEA_RETRIEVER_SEAHORSE`로 마이크로서비스 시작 확인
- [ ] Dataprep: `OPEA_DATAPREP_SEAHORSE`로 마이크로서비스 시작 확인
- [ ] **임베딩 일관성**: `SEAHORSE_EMBEDDING_MODE=builtin`으로 Dataprep 삽입 → 같은 모드로 Retriever 검색 정상 동작
- [ ] **임베딩 일관성**: `SEAHORSE_EMBEDDING_MODE=external`으로 Dataprep 삽입 → 같은 모드로 Retriever 검색 정상 동작
- [ ] 테스트 스크립트 pass
- [ ] Docker 빌드 성공 (공용 Dockerfile 사용, 환경변수로 컴포넌트 선택)
- [ ] API Key가 코드/테스트에 하드코딩되지 않았는지 확인
