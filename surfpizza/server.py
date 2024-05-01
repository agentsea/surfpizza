import os
from typing import List, Final
import logging

from taskara import Task, V1Task, V1Tasks
from surfkit.hub import Hub
from surfkit.models import V1SolveTask
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from tenacity import retry, stop_after_attempt, wait_fixed
import uvicorn

from .agent import Agent, router

logger: Final = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the agent type before the server comes live
    Agent.init()
    yield


app = FastAPI(lifespan=lifespan)  # type: ignore

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": "Agent in the shell"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/tasks")
async def solve_task(background_tasks: BackgroundTasks, task_model: V1SolveTask):
    print(f"solving task: {task_model.model_dump()}")
    try:
        # TODO: we need to find a way to do this earlier but get status back
        router.check_model()
    except Exception as e:
        logger.error(
            f"Cannot connect to LLM providers: {e} -- did you provide a valid key?"
        )
        return {
            "status": "failed",
            "message": f"failed to conect to LLM providers: {e} -- did you provide a valid key?",
        }

    background_tasks.add_task(_solve_task, task_model)
    logger.info("created background task...")


def _solve_task(task_model: V1SolveTask):
    task = Task.from_v1(task_model.task, owner_id="local")
    if task.remote:
        logger.info("connecting to remote task...")
        HUB_SERVER = os.environ.get("SURF_HUB_SERVER", "https://surf.agentlabs.xyz")
        HUB_API_KEY = os.environ.get("HUB_API_KEY")
        if not HUB_API_KEY:
            raise Exception("$HUB_API_KEY not set")

        hub = Hub(HUB_SERVER)
        user_info = hub.get_user_info(HUB_API_KEY)
        logger.debug("got user info: ", user_info.__dict__)

        task = get_remote_task(
            id=task.id,
            owner_id=user_info.email,  # type: ignore
            server=task.remote,
        )
        logger.debug("got remote task: ", task.__dict__)

    logger.info("Saving remote tasks status to running...")
    task.status = "in progress"
    task.save()

    if task_model.task.device:
        logger.info(f"connecting to device {task_model.task.device.name}...")
        device = None
        for Device in Agent.supported_devices():
            if Device.name() == task_model.task.device.name:
                logger.debug("found device: ", task_model.task.device.model_dump())
                logger.debug("model config: ", task_model.task.device.config)
                config = Device.connect_config_type()(**task_model.task.device.config)
                device = Device.connect(config=config)

        if not device:
            raise ValueError(
                f"Device {task_model.task.device.name} provided in solve task, but not supported by agent"
            )

        logger.debug("connected to device: ", device.__dict__)
    else:
        raise ValueError("No device provided")

    logger.info("starting agent...")
    if task_model.agent:
        config = Agent.config_type()(**task_model.agent.config.model_dump())
        agent = Agent.from_config(config=config)
    else:
        agent = Agent.default()

    try:
        fin_task = agent.solve_task(task=task, device=device, max_steps=task.max_steps)
    except Exception as e:
        logger.info("error running agent: ", e)
        task.status = "failed"
        task.error = str(e)
        task.save()
        task.post_message("assistant", f"Failed to run task '{task.description}': {e}")
        raise e
    if fin_task:
        fin_task.save()


@app.get("/v1/tasks", response_model=V1Tasks)
async def get_tasks():
    tasks = Task.find()
    return V1Tasks(tasks=[task.to_v1() for task in tasks])


@app.get("/v1/tasks/{id}", response_model=V1Task)
async def get_task(id: str):
    tasks = Task.find(id=id)
    if not tasks:
        raise Exception(f"Task {id} not found")
    return tasks[0].to_v1()


@retry(stop=stop_after_attempt(10), wait=wait_fixed(10))
def get_remote_task(id: str, owner_id: str, server: str) -> Task:
    HUB_API_KEY = os.environ.get("HUB_API_KEY")
    if not HUB_API_KEY:
        raise Exception("$HUB_API_KEY not set")

    logger.debug("connecting to remote task: ", id, HUB_API_KEY)
    try:
        tasks = Task.find(
            id=id,
            remote=server,
            owner_id=owner_id,
        )
        if not tasks:
            raise Exception(f"Task {id} not found")
        logger.debug("got remote task: ", tasks[0].__dict__)
        return tasks[0]
    except Exception as e:
        logger.error("error getting remote task: ", e)
        raise e


if __name__ == "__main__":
    port = os.getenv("SURF_PORT", "9090")
    uvicorn.run(app, host="0.0.0.0", port=int(port), reload=True)
