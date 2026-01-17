# from dotenv import load_dotenv
# from core.neo4j_driver import init_driver, close_driver

# load_dotenv()

# from repositories.ingest_repo import GraphRepository
# from agent.agent import LangGraphIngestionAgent
# from pipeline.ingestion_pipeline import IngestionPipeline

# init_driver()  # what the fuck


# repo = GraphRepository()
# repo.ensure_constraints()

# agent = LangGraphIngestionAgent(repo=repo)
# # ingestionPipeline = IngestionPipeline(r"D:\nabu\pipeline\normalized")
# # ingestionPipeline.run()  

# facts = agent.run(
#     raw_input={"items": [{"IDrequest": "З-2025-1833-062-jlS", "basis_request": "6161-ТІТ", "ExecutorInfo": {"ExecutorEDRPOUcode": "11111111", "ExecutorRNOKPP": "111115555511", "ExecutorFullName": "Тестеров Таурус"}, "person": {"RNOKPP": "2935512345", "last_name": "АДЕЛЬРЕЇВ", "first_name": "ЕДМУНД", "middle_name": "АДОЛЬФОВИЧ", "date_birth": "1980-05-15"}, "residence": {}, "period": {"period_begin_month": 1, "period_begin_year": 2001, "period_end_month": 12, "period_end_year": 2001}}], "id": "З-2025-1833-062-jlS"},
#     max_fix_attempts=5,
# )
# # print(facts)
# close_driver()
# print("DONE ✅")


from __future__ import annotations

import json
from pathlib import Path
from dotenv import load_dotenv

from core.neo4j_driver import init_driver, close_driver
from repositories.ingest_repo import GraphRepository
from agent.agent import LangGraphIngestionAgent


# ============================================================
# Bootstrap
# ============================================================

def bootstrap_agent() -> LangGraphIngestionAgent:
    """
    Initializes env, Neo4j driver, repository, constraints and agent.
    """
    load_dotenv()

    init_driver()  # initializes global neo4j driver singleton

    repo = GraphRepository()
    repo.ensure_constraints()

    return LangGraphIngestionAgent(repo=repo)


# ============================================================
# Helpers
# ============================================================

def iter_ndjson(path: Path):
    """
    Iterate over NDJSON file (one JSON per line).
    """
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                print(f"[WARN] Broken JSON at line {line_no}: {e}")


# ============================================================
# Main
# ============================================================

def main():
    agent = bootstrap_agent()

    try:
        # # ====================================================
        # # 🔹 VARIANT 1 — single record (manual test)
        # # ====================================================
        # facts = agent.run(
        #     raw_input={
        #         "items": [
        #             {
        #                 "IDrequest": "З-2025-1833-062-jlS",
        #                 "basis_request": "6161-ТІТ",
        #                 "ExecutorInfo": {
        #                     "ExecutorEDRPOUcode": "11111111",
        #                     "ExecutorRNOKPP": "111115555511",
        #                     "ExecutorFullName": "Тестеров Таурус",
        #                 },
        #                 "person": {
        #                     "RNOKPP": "2935512345",
        #                     "last_name": "АДЕЛЬРЕЇВ",
        #                     "first_name": "ЕДМУНД",
        #                     "middle_name": "АДОЛЬФОВИЧ",
        #                     "date_birth": "1980-05-15",
        #                 },
        #                 "residence": {},
        #                 "period": {
        #                     "period_begin_month": 1,
        #                     "period_begin_year": 2001,
        #                     "period_end_month": 12,
        #                     "period_end_year": 2001,
        #                 },
        #             }
        #         ],
        #         "id": "З-2025-1833-062-jlS",
        #     },
        #     max_fix_attempts=5,
        # )

        # print(facts)  # optional debug

        # ====================================================
        # 🔹 VARIANT 2 — full all_data.txt ingestion
        # ====================================================
        all_data_path = Path("all_data.txt")
        
        success = 0
        failed = 0
        
        for record in iter_ndjson(all_data_path):
            try:
                agent.run(raw_input=record, max_fix_attempts=5)
                success += 1
            except Exception as e:
                failed += 1
                print(f"[ERROR] id={record.get('id')} -> {e}")
        
        print(f"[DONE] success={success}, failed={failed}")

    finally:
        close_driver()
        print("DONE ✅")


if __name__ == "__main__":
    main()
