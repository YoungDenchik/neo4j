from dotenv import load_dotenv
from core.neo4j_driver import init_driver, close_driver

load_dotenv()

from repositories.ingest_repo import GraphRepository
from agent.agent import LangGraphIngestionAgent

init_driver()  # what the fuck


repo = GraphRepository()
repo.ensure_constraints()

agent = LangGraphIngestionAgent(repo=repo)

facts = agent.run(
    raw_input={
        "items": [
            {
                "RNOKPP": "2935512345",
                "last_name": "АДЕЛЬРЕЇВ",
                "first_name": "ЕДМУНД",
                "middle_name": "АДОЛЬФОВИЧ",
                "date_birth": "1980-05-15",
            }
        ],
        "id": "З-2025-1833-062-u5p",
    },
    max_fix_attempts=2,
)
print(facts)
close_driver()
print("DONE ✅")
