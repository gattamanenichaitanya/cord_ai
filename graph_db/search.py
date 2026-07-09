import sys
import os
import argparse
from pathlib import Path
import chromadb
from chromadb.utils import embedding_functions

os.environ["HF_TRUST_REMOTE_CODE"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"



PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHROMA_DIR = PROJECT_ROOT / "graph_db" / "chroma"

def get_embedding_function():
    try:
        return embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    except Exception:
        return embedding_functions.ONNXMiniLM_L6_V2()

def search_graph(query: str, n_results: int = 5, filter_type: str = None, filter_object: str = None) -> list[dict]:
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    ef = get_embedding_function()
    collection = client.get_collection("hubspot_graph", embedding_function=ef)

    if filter_type == "ui_operation":
        filter_type = "operation"

    conditions = []
    if filter_type:
        conditions.append({"type": filter_type})
    if filter_object:
        conditions.append({"object": filter_object})

    where_clause = None
    if len(conditions) == 1:
        where_clause = conditions[0]
    elif len(conditions) > 1:
        where_clause = {"$and": conditions}

    query_args = {
        "query_texts": [query],
        "n_results": n_results
    }
    if where_clause:
        query_args["where"] = where_clause

    results_raw = collection.query(**query_args)

    output = []
    if results_raw and results_raw.get("documents") and results_raw["documents"][0]:
        docs = results_raw["documents"][0]
        metas = results_raw["metadatas"][0]
        dists = results_raw["distances"][0]

        for doc, meta, dist in zip(docs, metas, dists):
            output.append({
                "text": doc,
                "metadata": meta,
                "distance": dist,
                "file_path": meta.get("file_path", "")
            })

    return output

def main():
    parser = argparse.ArgumentParser(description="Search the HubSpot Graph DB")
    parser.add_argument("query", type=str, help="Search query text")
    parser.add_argument("--type", type=str, default=None, help="Filter by graph_entry_type (e.g. standard_property, gotcha, operation)")
    parser.add_argument("--object", type=str, default=None, help="Filter by target object (e.g. contacts)")
    parser.add_argument("-n", "--results", type=int, default=5, help="Number of results to return")

    args = parser.parse_args()

    results = search_graph(args.query, n_results=args.results, filter_type=args.type, filter_object=args.object)

    print(f"\nSearch Query: '{args.query}'")
    if args.type:
        print(f"Filter Type: {args.type}")
    if args.object:
        print(f"Filter Object: {args.object}")
    print(f"Found {len(results)} results:\n")

    for idx, res in enumerate(results, 1):
        meta = res["metadata"]
        text_preview = res["text"].replace("\n", " ")[:150]
        print(f"{idx}. [Distance: {res['distance']:.4f}] Type: {meta.get('type')}, ID: {meta.get('entry_id')}")
        print(f"   File: {res['file_path']}")
        print(f"   Text: {text_preview}...\n")

if __name__ == "__main__":
    main()
