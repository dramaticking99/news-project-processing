from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

class Article(BaseModel):
    url: str
    title: str
    content: str

app = FastAPI(title="News Processing API")

@app.post("/process-article")
def process_article(article: Article):
    print(f"Received article to process: {article.title}")
    # --- VECTOR DB and AI LOGIC GOES HERE ---
    return {"status": "Article received", "title": article.title}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)