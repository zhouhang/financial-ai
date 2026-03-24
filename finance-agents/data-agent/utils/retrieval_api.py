"""Retrieval API clients for embedding and rerank.

当前先接入智谱 AI 的 Embedding / Rerank 接口，后续如果替换供应商，
只需要保持这里的函数签名不变即可。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import httpx

from config import (
    ZHIPU_API_KEY,
    ZHIPU_BASE_URL,
    ZHIPU_EMBEDDING_MODEL,
    ZHIPU_RERANK_MODEL,
    ZHIPU_EMBEDDING_DIMENSIONS,
    ZHIPU_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


class ZhipuRetrievalClient:
    """智谱检索客户端。

    提供两个稳定方法：
    - embed_texts: 文本转向量
    - rerank_documents: 对候选文档进行重排
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        embedding_model: str,
        rerank_model: str,
        embedding_dimensions: int,
        timeout_seconds: float,
    ) -> None:
        if not api_key:
            raise ValueError("ZHIPU_API_KEY 未配置，请在 data-agent/.env 中设置")

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.embedding_model = embedding_model
        self.rerank_model = rerank_model
        self.embedding_dimensions = embedding_dimensions
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        logger.info("调用智谱检索接口: %s", url)

        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(url, headers=self._headers(), json=payload)

        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError(f"智谱接口返回格式异常: {type(data)!r}")
        return data

    def embed_texts(
        self,
        texts: list[str],
        *,
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """批量将文本转换为向量。

        Args:
            texts: 输入文本列表。
            dimensions: 可选，覆盖默认向量维度。
        """
        cleaned_texts = [text.strip() for text in texts if text and text.strip()]
        if not cleaned_texts:
            return []

        payload = {
            "model": self.embedding_model,
            "input": cleaned_texts,
            "dimensions": dimensions or self.embedding_dimensions,
        }
        data = self._post("/embeddings", payload)
        items = data.get("data") or []

        embeddings: list[list[float]] = []
        for item in items:
            embedding = item.get("embedding")
            if not isinstance(embedding, list):
                raise ValueError("智谱 embedding 返回缺少 embedding 字段")
            embeddings.append(embedding)

        if len(embeddings) != len(cleaned_texts):
            raise ValueError(
                f"智谱 embedding 返回数量异常: expected={len(cleaned_texts)}, got={len(embeddings)}"
            )
        return embeddings

    def embed_text(
        self,
        text: str,
        *,
        dimensions: int | None = None,
    ) -> list[float]:
        """单条文本转向量。"""
        embeddings = self.embed_texts([text], dimensions=dimensions)
        return embeddings[0] if embeddings else []

    def rerank_documents(
        self,
        *,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[dict[str, Any]]:
        """对候选文档进行重排。

        Returns:
            返回智谱 API 原生结果的轻量标准化结构，至少包含：
            - index
            - document
            - relevance_score
        """
        cleaned_query = (query or "").strip()
        cleaned_documents = [doc.strip() for doc in documents if doc and doc.strip()]
        if not cleaned_query:
            raise ValueError("rerank query 不能为空")
        if not cleaned_documents:
            return []

        payload = {
            "model": self.rerank_model,
            "query": cleaned_query,
            "documents": cleaned_documents,
        }
        if top_n is not None:
            payload["top_n"] = top_n

        data = self._post("/rerank", payload)
        results = data.get("results") or []

        normalized_results: list[dict[str, Any]] = []
        for item in results:
            index = item.get("index")
            if not isinstance(index, int):
                raise ValueError("智谱 rerank 返回缺少合法 index 字段")
            normalized_results.append(
                {
                    "index": index,
                    "document": item.get("document", ""),
                    "relevance_score": item.get("relevance_score"),
                }
            )
        return normalized_results


@lru_cache(maxsize=1)
def get_retrieval_client() -> ZhipuRetrievalClient:
    """获取检索 API 客户端单例。"""
    return ZhipuRetrievalClient(
        api_key=ZHIPU_API_KEY,
        base_url=ZHIPU_BASE_URL,
        embedding_model=ZHIPU_EMBEDDING_MODEL,
        rerank_model=ZHIPU_RERANK_MODEL,
        embedding_dimensions=ZHIPU_EMBEDDING_DIMENSIONS,
        timeout_seconds=ZHIPU_TIMEOUT_SECONDS,
    )


def embed_texts(
    texts: list[str],
    *,
    dimensions: int | None = None,
) -> list[list[float]]:
    """供后续 history_retrieval 等模块直接调用的批量 embedding 方法。"""
    return get_retrieval_client().embed_texts(texts, dimensions=dimensions)


def embed_text(
    text: str,
    *,
    dimensions: int | None = None,
) -> list[float]:
    """供后续 history_retrieval 等模块直接调用的单条 embedding 方法。"""
    return get_retrieval_client().embed_text(text, dimensions=dimensions)


def rerank_documents(
    *,
    query: str,
    documents: list[str],
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    """供后续 history_retrieval 等模块直接调用的 rerank 方法。"""
    return get_retrieval_client().rerank_documents(
        query=query,
        documents=documents,
        top_n=top_n,
    )
