import os
import sys
import json
from pathlib import Path
import chromadb
from chromadb.utils import embedding_functions

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GRAPH_DIR = PROJECT_ROOT / "graph" / "hubspot"
CHROMA_DIR = PROJECT_ROOT / "graph_db" / "chroma"

def get_embedding_function():
    try:
        print("Initializing embedding model (all-MiniLM-L6-v2)...")
        return embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    except Exception as e:
        print(f"Fallback to ONNXMiniLM_L6_V2 due to embedding initialization notice/error: {e}")
        return embedding_functions.ONNXMiniLM_L6_V2()

def extract_text_and_metadata(file_path: Path, data: dict):
    entry_type = data.get("graph_entry_type")
    rel_path = file_path.relative_to(PROJECT_ROOT).as_posix()

    if entry_type == "object":
        entry_id = data.get("internal_name", "")
        synonyms = ", ".join(data.get("synonyms_for_semantic_matching", []))
        text_parts = [
            f"Display Label: {data.get('display_label', '')}",
            f"Internal Name: {entry_id}",
            f"Semantic Meaning: {data.get('semantic_meaning', '')}",
            f"Synonyms: {synonyms}"
        ]
        text_repr = "\n".join(text_parts)
        metadata = {
            "type": entry_type,
            "file_path": rel_path,
            "entry_id": entry_id,
            "object": entry_id
        }
        return text_repr, metadata

    elif entry_type == "standard_property":
        entry_id = data.get("internal_name", "")
        synonyms = ", ".join(data.get("synonyms_for_semantic_matching", []))
        uses = " ".join(data.get("common_uses", []))
        alts_raw = data.get("alternatives_to_consider", [])
        alt_names = []
        for alt in alts_raw:
            if isinstance(alt, dict):
                alt_names.append(alt.get("property", ""))
            elif isinstance(alt, str):
                alt_names.append(alt)
        alts_str = ", ".join(filter(None, alt_names))

        text_parts = [
            f"Display Label: {data.get('display_label', '')}",
            f"Internal Name: {entry_id}",
            f"Semantic Meaning: {data.get('semantic_meaning', '')}",
            f"Synonyms: {synonyms}",
            f"Common Uses: {uses}",
            f"Alternatives to Consider: {alts_str}"
        ]
        text_repr = "\n".join(text_parts)
        metadata = {
            "type": entry_type,
            "file_path": rel_path,
            "entry_id": entry_id,
            "object": data.get("object", "")
        }
        return text_repr, metadata

    elif entry_type == "capability":
        entry_id = data.get("capability_name", "")
        criteria_parts = []
        criteria = data.get("decision_criteria", {})
        if isinstance(criteria, dict):
            for k, v in criteria.items():
                if isinstance(v, dict):
                    sub_str = " ".join(f"{sk}: {sv}" for sk, sv in v.items())
                    criteria_parts.append(f"{k}: {sub_str}")
                else:
                    criteria_parts.append(f"{k}: {v}")
        criteria_str = "\n".join(criteria_parts)

        synonyms = ", ".join(data.get("synonyms_for_semantic_matching", []))

        text_parts = [
            f"Capability Name: {entry_id}",
            f"What This Enables: {data.get('what_this_enables', '')}",
            f"Decision Criteria:\n{criteria_str}"
        ]
        if synonyms:
            text_parts.append(f"Synonyms: {synonyms}")

        text_repr = "\n".join(text_parts)
        metadata = {
            "type": entry_type,
            "file_path": rel_path,
            "entry_id": entry_id,
            "object": ""
        }
        return text_repr, metadata

    elif entry_type == "operation":
        entry_id = data.get("operation_id", "")
        intents = []
        for method in data.get("execution_methods", []):
            for step in method.get("steps", []):
                if isinstance(step, dict) and "intent" in step:
                    intents.append(step["intent"])
                if isinstance(step, dict) and "loop_sub_steps" in step:
                    for sub in step["loop_sub_steps"]:
                        if isinstance(sub, dict) and "intent" in sub:
                            intents.append(sub["intent"])
        intents_str = "\n".join(intents)

        text_parts = [
            f"Operation ID: {entry_id}",
            f"Description: {data.get('description', '')}",
            f"Step Intents:\n{intents_str}"
        ]
        text_repr = "\n".join(text_parts)
        metadata = {
            "type": entry_type,
            "file_path": rel_path,
            "entry_id": entry_id,
            "object": ""
        }
        return text_repr, metadata

    elif entry_type == "gotcha":
        entry_id = data.get("gotcha_id", "")
        surfaces = "\n".join(data.get("when_to_surface_this", []))
        manifests = "\n".join(data.get("how_it_manifests", []))

        text_parts = [
            f"Gotcha ID: {entry_id}",
            f"The Problem: {data.get('the_problem', '')}",
            f"When to Surface This:\n{surfaces}",
            f"How it Manifests:\n{manifests}"
        ]
        text_repr = "\n".join(text_parts)
        metadata = {
            "type": entry_type,
            "file_path": rel_path,
            "entry_id": entry_id,
            "object": ""
        }
        return text_repr, metadata

    else:
        return None, None

def build_index():
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    collection_name = "hubspot_graph"
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    ef = get_embedding_function()
    collection = client.create_collection(collection_name, embedding_function=ef)

    json_files = list(GRAPH_DIR.rglob("*.json"))
    print(f"Found {len(json_files)} JSON files in graph/hubspot/")

    documents = []
    metadatas = []
    ids = []
    type_counts = {}

    for file_path in json_files:
        rel_path = file_path.relative_to(PROJECT_ROOT).as_posix()
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Skipping {rel_path}: Malformed JSON ({e})")
            continue

        entry_type = data.get("graph_entry_type")
        text_repr, metadata = extract_text_and_metadata(file_path, data)

        if text_repr is None or metadata is None:
            print(f"Skipping {rel_path}: No indexer for type {entry_type} — skipping")
            continue

        entry_id = metadata["entry_id"]
        print(f"Indexing {rel_path} [type={entry_type}, id={entry_id}]")

        documents.append(text_repr)
        metadatas.append(metadata)
        ids.append(rel_path)

        type_counts[entry_type] = type_counts.get(entry_type, 0) + 1

    if documents:
        collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )

    counts_str = ", ".join(f"{k}: {v}" for k, v in type_counts.items())
    print(f"Final summary: Indexed {len(documents)} entries across types: {{{counts_str}}}")

if __name__ == "__main__":
    build_index()
