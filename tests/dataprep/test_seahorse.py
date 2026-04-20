import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class FakeHTTPException(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class FakeLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class FakeOpeaComponent:
    def __init__(self, name, type, description, config=None):
        self.name = name
        self.type = type
        self.description = description
        self.config = config or {}


class FakeOpeaComponentRegistry:
    _registry = {}

    @classmethod
    def register(cls, name):
        def decorator(component_class):
            cls._registry[name] = component_class
            return component_class

        return decorator


class FakeEmbeddingClient:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class FakeVectorStore:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self._client = SimpleNamespace(get_indexed_row_count=lambda: {"total_row_count": 1})

    def add_texts(self, *args, **kwargs):
        return None

    def delete(self, *args, **kwargs):
        return None


class FakeTextSplitter:
    def __init__(self, *args, **kwargs):
        pass

    def split_text(self, content):
        return [content]


def _package(name):
    module = types.ModuleType(name)
    module.__path__ = []
    return module


def import_dataprep_module(env):
    package_name = "testpkg_dataprep"
    module_name = f"{package_name}.seahorse"
    config_package_name = f"{package_name}.config"
    config_name = f"{config_package_name}.seahorse"

    for name in list(sys.modules):
        if name.startswith(package_name):
            sys.modules.pop(name, None)

    fake_fastapi = types.ModuleType("fastapi")
    fake_fastapi.HTTPException = FakeHTTPException
    fake_fastapi.Body = lambda default=None, embed=False: default
    fake_fastapi.File = lambda default=None: default
    fake_fastapi.Form = lambda default=None: default
    fake_fastapi.UploadFile = object

    fake_requests = types.ModuleType("requests")
    fake_requests.get = MagicMock()

    fake_langchain = _package("langchain")
    fake_langchain_text_splitter = types.ModuleType("langchain.text_splitter")
    fake_langchain_text_splitter.RecursiveCharacterTextSplitter = FakeTextSplitter

    fake_langchain_community = _package("langchain_community")
    fake_langchain_community_embeddings = types.ModuleType("langchain_community.embeddings")
    fake_langchain_community_embeddings.HuggingFaceInferenceAPIEmbeddings = FakeEmbeddingClient

    fake_langchain_huggingface = types.ModuleType("langchain_huggingface")
    fake_langchain_huggingface.HuggingFaceEmbeddings = FakeEmbeddingClient

    fake_langchain_text_splitters = types.ModuleType("langchain_text_splitters")
    fake_langchain_text_splitters.HTMLHeaderTextSplitter = FakeTextSplitter

    fake_seahorse_module = types.ModuleType("seahorse_vector_store")
    fake_seahorse_module.SeahorseVectorStore = FakeVectorStore

    fake_comps = types.ModuleType("comps")
    fake_comps.CustomLogger = lambda name: FakeLogger()
    fake_comps.DocPath = SimpleNamespace
    fake_comps.OpeaComponent = FakeOpeaComponent
    fake_comps.OpeaComponentRegistry = FakeOpeaComponentRegistry
    fake_comps.ServiceType = SimpleNamespace(DATAPREP=SimpleNamespace(name="DATAPREP"))

    fake_api_protocol = types.ModuleType("comps.cores.proto.api_protocol")
    fake_api_protocol.DataprepRequest = object

    fake_utils = types.ModuleType("comps.dataprep.src.utils")
    fake_utils.create_upload_folder = lambda path: None
    fake_utils.document_loader = lambda path: ""
    fake_utils.encode_filename = lambda name: name.replace("/", "_")
    fake_utils.get_separators = lambda: ["\n\n", "\n", " "]
    fake_utils.get_tables_result = lambda path, strategy: []
    fake_utils.parse_html_new = lambda links, chunk_size=None, chunk_overlap=None: ""
    fake_utils.remove_folder_with_ignore = lambda path: None
    fake_utils.save_content_to_local_disk = lambda path, file: None

    config_package = _package(config_package_name)
    config_module = types.ModuleType(config_name)
    config_module.EMBED_MODEL = env.get("EMBED_MODEL", "BAAI/bge-base-en-v1.5")
    config_module.HF_TOKEN = env.get("HF_TOKEN", "")
    config_module.SEAHORSE_API_KEY = env.get("SEAHORSE_API_KEY", "")
    config_module.SEAHORSE_BASE_URL = env.get("SEAHORSE_BASE_URL", "")
    config_module.SEAHORSE_EMBEDDING_MODE = env.get("SEAHORSE_EMBEDDING_MODE", "builtin")
    config_module.TEI_EMBEDDING_ENDPOINT = env.get("TEI_EMBEDDING_ENDPOINT", "")

    dataprep_package = _package(package_name)
    dataprep_package.config = config_package

    module_path = Path(__file__).resolve().parents[2] / "comps" / "dataprep" / "src" / "integrations" / "seahorse.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = package_name

    with patch.dict(
        sys.modules,
        {
            "fastapi": fake_fastapi,
            "requests": fake_requests,
            "langchain": fake_langchain,
            "langchain.text_splitter": fake_langchain_text_splitter,
            "langchain_community": fake_langchain_community,
            "langchain_community.embeddings": fake_langchain_community_embeddings,
            "langchain_huggingface": fake_langchain_huggingface,
            "langchain_text_splitters": fake_langchain_text_splitters,
            "seahorse_vector_store": fake_seahorse_module,
            "comps": fake_comps,
            "comps.cores": _package("comps.cores"),
            "comps.cores.proto": _package("comps.cores.proto"),
            "comps.cores.proto.api_protocol": fake_api_protocol,
            "comps.dataprep": _package("comps.dataprep"),
            "comps.dataprep.src": _package("comps.dataprep.src"),
            "comps.dataprep.src.utils": fake_utils,
            package_name: dataprep_package,
            config_package_name: config_package,
            config_name: config_module,
            module_name: module,
        },
        clear=False,
    ):
        spec.loader.exec_module(module)
    return module


class TestSeahorseDataprep(unittest.TestCase):
    def test_init_requires_base_url_and_api_key(self):
        module = import_dataprep_module(
            {
                "SEAHORSE_BASE_URL": "",
                "SEAHORSE_API_KEY": "",
                "SEAHORSE_EMBEDDING_MODE": "builtin",
            }
        )

        vectorstore = MagicMock()
        vectorstore._client.get_indexed_row_count.return_value = {"total_row_count": 1}

        with patch.object(module, "SeahorseVectorStore", return_value=vectorstore):
            with self.assertRaises(RuntimeError):
                module.OpeaSeahorseDataprep("OPEA_DATAPREP_SEAHORSE", "test")

    def test_init_raises_when_health_check_fails(self):
        module = import_dataprep_module(
            {
                "SEAHORSE_BASE_URL": "https://example.com",
                "SEAHORSE_API_KEY": "secret",
                "SEAHORSE_EMBEDDING_MODE": "builtin",
            }
        )

        vectorstore = MagicMock()
        vectorstore._client.get_indexed_row_count.side_effect = RuntimeError("unreachable")

        with patch.object(module, "SeahorseVectorStore", return_value=vectorstore):
            with self.assertRaises(RuntimeError):
                module.OpeaSeahorseDataprep("OPEA_DATAPREP_SEAHORSE", "test")

    def test_tei_info_without_model_id_raises_http_exception(self):
        module = import_dataprep_module(
            {
                "SEAHORSE_BASE_URL": "https://example.com",
                "SEAHORSE_API_KEY": "secret",
                "SEAHORSE_EMBEDDING_MODE": "external",
                "TEI_EMBEDDING_ENDPOINT": "https://tei.example.com",
                "HF_TOKEN": "hf-token",
            }
        )

        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {}

        with patch.object(module, "requests") as mock_requests:
            mock_requests.get.return_value = response
            with self.assertRaises(module.HTTPException):
                module.OpeaSeahorseDataprep("OPEA_DATAPREP_SEAHORSE", "test")


if __name__ == "__main__":
    unittest.main()
