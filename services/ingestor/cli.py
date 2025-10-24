#!/usr/bin/env python3
"""
Ingestor CLI - 命令行工具用於批次匯入文件
"""

import argparse
import json
import sys
from pathlib import Path

import requests


def main():
    parser = argparse.ArgumentParser(description="FreeRoute RAG Ingestor CLI")
    parser.add_argument("path", help="要匯入的目錄路徑")
    parser.add_argument("--ingestor-url", default="http://localhost:9900", help="Ingestor 服務 URL")
    parser.add_argument("--collection", default="chunks", help="Qdrant collection 名稱")
    parser.add_argument("--file-patterns", nargs="+", default=["*.md", "*.txt", "*.html"], help="檔案模式")
    parser.add_argument("--chunk-size", type=int, default=1000, help="切分大小")
    parser.add_argument("--chunk-overlap", type=int, default=200, help="切分重疊")
    parser.add_argument("--no-graph", action="store_true", help="不抽取知識圖譜")
    parser.add_argument("--force", action="store_true", help="強制重新處理")
    parser.add_argument("--api-key", type=str, default=None, help="Gateway API Key (推薦，會自動推斷 tenant)")
    parser.add_argument("--tenant-id", type=str, default=None, help="Tenant ID (可選，若未指定則自動從 API key 推斷)")

    args = parser.parse_args()

    # 驗證路徑
    if not Path(args.path).exists():
        print(f"錯誤：路徑不存在 {args.path}")
        sys.exit(1)

    # 準備請求
    data = {
        "path": args.path,
        "collection": args.collection,
        "file_patterns": args.file_patterns,
        "chunk_size": args.chunk_size,
        "chunk_overlap": args.chunk_overlap,
        "extract_graph": not args.no_graph,
        "force_reprocess": args.force,
    }
    # 傳遞 tenant_id 給 ingestor service
    if args.tenant_id:
        data["tenant_id"] = args.tenant_id

    print(f"開始匯入目錄：{args.path}")
    print(f"檔案模式：{args.file_patterns}")
    print(f"切分大小：{args.chunk_size} (重疊 {args.chunk_overlap})")
    print(f"圖譜抽取：{'開啟' if not args.no_graph else '關閉'}")
    print()

    try:
        # 準備 header
        headers = {}
        if args.api_key:
            headers["X-API-Key"] = args.api_key
        # 呼叫 API
        response = requests.post(
            f"{args.ingestor_url}/ingest/directory",
            json=data,
            headers=headers,
            timeout=300,  # 5分鐘超時
        )
        response.raise_for_status()

        result = response.json()

        # 顯示結果
        print("匯入完成！")
        print(f"狀態：{result['message']}")
        print()
        print("統計資訊：")
        for key, value in result["stats"].items():
            print(f"  {key}: {value}")

        if result["processed_files"]:
            print(f"\n已處理文件 ({len(result['processed_files'])})：")
            for file in result["processed_files"][:10]:  # 只顯示前10個
                print(f"  ✓ {file}")
            if len(result["processed_files"]) > 10:
                print(f"  ... 及其他 {len(result['processed_files']) - 10} 個檔案")

        if result["errors"]:
            print(f"\n錯誤 ({len(result['errors'])})：")
            for error in result["errors"][:5]:  # 只顯示前5個錯誤
                print(f"  ✗ {error['file']} ({error['stage']}): {error['error']}")
            if len(result["errors"]) > 5:
                print(f"  ... 及其他 {len(result['errors']) - 5} 個錯誤")
    except requests.RequestException as e:
        print(f"API 呼叫失敗：{e}")
        sys.exit(1)
    except Exception as e:
        print(f"未知錯誤：{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
