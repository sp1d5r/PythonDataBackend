from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="My API")


class HelloResponse(BaseModel):
    message: str


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}", response_model=HelloResponse)
async def say_hello(name: str):
    return HelloResponse(message=f"Hello {name}")