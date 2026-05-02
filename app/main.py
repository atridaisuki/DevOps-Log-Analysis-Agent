from fastapi import FastAPI

from app.routers import agent, health

app = FastAPI(
    title="DevOps Log Analysis Agent",
    version="0.1.0",
    description="LangGraph ReAct agent for automated incident diagnosis",
)

app.include_router(health.router)
app.include_router(agent.router, prefix="/agent", tags=["agent"])
