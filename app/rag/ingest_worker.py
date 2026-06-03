from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import List

from app.core.router import ServiceRouter, get_router


def chunk_markdown(markdown: str, min_chars: int = 50) -> List[str]:
    return [chunk.strip() for chunk in markdown.split("\n\n") if len(chunk.strip()) >= min_chars]


def stable_point_id(candidate_id: str, chunk_index: int) -> int:
    digest = hashlib.sha256(f"{candidate_id}:{chunk_index}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)


def process_and_vectorize_resume(
    file_path: str,
    candidate_id: str,
    router: ServiceRouter | None = None,
    document_parser_service: str | None = None,
    embedding_service: str | None = None,
    vector_store_service: str | None = None,
    write_database: bool = False,
    database_service: str | None = None,
) -> str:
    router = router or get_router()
    print(f"[4090 Worker] 正在解析多模态源文档: {file_path}")
    clean_text = router.document_parser(document_parser_service).parse(file_path)
    chunks = chunk_markdown(clean_text)
    if not chunks:
        raise ValueError("Document parsed successfully, but no chunk reached the minimum length.")

    print(f"[4090 Worker] 文档解析完毕，切分为 {len(chunks)} 个结构化知识分块。开始本地 Embedding...")
    embeddings = router.embedding(embedding_service).embed_texts(chunks)
    router.vector_store(vector_store_service).upsert_chunks(
        candidate_id=candidate_id,
        chunks=chunks,
        embeddings=embeddings,
        point_id_fn=stable_point_id,
    )
    if write_database:
        router.database(database_service).candidate_repository().upsert_candidate_profile(
            {
                "candidate_id": candidate_id,
                "source_platform": "internal",
                "technical_layer_tags": [],
                "parsed_capabilities": {},
                "raw_text_vector_id": candidate_id,
            }
        )
    print(f"成功将候选人 {candidate_id} 的多模态知识网络注入本地 Qdrant 数据库。")
    return clean_text


def create_mock_resume(path: str) -> None:
    Path(path).write_text(
        "# 张三\n\n"
        "具身智能算法实习生。擅长使用 Cursor 和 LangGraph 快速复现 Diffusion Policy。"
        "并在本地 Isaac Sim 中成功搭建了家庭厨房洗碗任务的仿真环境，动作Token对齐延迟控制在12ms。\n\n"
        "项目证据：实现遥操作数据清洗脚本，完成多摄像头视频、关节角和力矩数据的时间戳对齐。",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Local 4090 resume/document ingest worker.")
    parser.add_argument("--file", default="test_readme.md", help="PDF/DOCX/image/Markdown resume path")
    parser.add_argument("--candidate-id", default="cand_ai_native_002")
    parser.add_argument("--config", default=None, help="Service config TOML path. Defaults to config/services.toml")
    parser.add_argument("--document-parser", default=None, help="Override document_parser service name")
    parser.add_argument("--embedding", default=None, help="Override embedding service name")
    parser.add_argument("--vector-store", default=None, help="Override vector_store service name")
    parser.add_argument("--write-db", action="store_true", help="Write candidate metadata to configured database")
    parser.add_argument("--database", default=None, help="Override database service name")
    args = parser.parse_args()

    if not Path(args.file).exists() and args.file == "test_readme.md":
        create_mock_resume(args.file)

    router = get_router(args.config)
    extracted_md = process_and_vectorize_resume(
        file_path=args.file,
        candidate_id=args.candidate_id,
        router=router,
        document_parser_service=args.document_parser,
        embedding_service=args.embedding,
        vector_store_service=args.vector_store,
        write_database=args.write_db,
        database_service=args.database,
    )
    print("\n--- 本地多模态抽取 Markdown 预览 ---")
    print(extracted_md[:500])


if __name__ == "__main__":
    main()
