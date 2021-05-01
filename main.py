print("Importing libraries...")
import os
import json
from collections import Counter
import spacy
from flask import Flask, request
from gevent.pywsgi import WSGIServer
from decouple import config
from pixabay import Video

print("Loading spaCy language model...")
nlp = spacy.load("en_core_web_lg")
print("Successfully loaded spaCy language model.")

def get_keywords(text):
    doc = nlp(text)
    entities = [e.text for e in list(doc.ents) if e.label_ in ["PERSON", "NORP", "FAC", "ORG", "GPE", "LOC", "PRODUCT", "EVENT"]]
    words = [w.text for w in list(doc) if w.is_alpha and not w.is_stop and not w.is_punct and w.tag_ in ["NN", "NNS", "NNP", "NNPS", "VB", "VBD", "VBG", "VBP", "VBZ", "AFX", "JJ"]]
    return entities + words
    
app = Flask(__name__)
PORT = int(os.environ.get("PORT", 8001))
PIXABAY_API_AUTH_KEY = os.environ.get(
    "PIXABAY_API_AUTH_KEY", config("PIXABAY_API_AUTH_KEY") or "Your API key from https://pixabay.com/api/docs/")

video = Video(PIXABAY_API_AUTH_KEY)

def get_video_data(text, main_keywords, duration, video_ids):
    keywords = get_keywords(text) or [text]
    doc_keywords = nlp(" ".join(keywords + main_keywords)) # used for similarity
    keywords = [k[0] for k in Counter(keywords).most_common(5)] + main_keywords # keywords to search in order
    min_duration = duration
    max_duration = 60 * 5
    video_url = ""
    video_id = 0
    for keyword in keywords:
        # per keyword
        max_similarity = 0
        max_hit = {}
        for hit in video.search(q=keyword, safesearch="true", per_page=200)["hits"]:
            if min_duration <= hit["duration"] <= max_duration and hit["picture_id"] not in video_ids:
                similarity = doc_keywords.similarity(nlp(hit["tags"].replace(",", "")))
                if similarity > max_similarity:
                    max_similarity = similarity
                    max_hit = hit
        if max_similarity > 0.5 and max_hit:
            video_url = max_hit["videos"]["large"]["url"] or max_hit["videos"]["medium"]["url"] or max_hit["videos"]["small"]["url"]
            if not video_url:
                continue
            video_id = max_hit["picture_id"]
            video_ids.add(video_id);
            break
    if not video_url: #find random abstract videos?
        for hit in video.search(q="abstract", safesearch="true", per_page=200)["hits"]:
            if min_duration <= hit["duration"] <= max_duration and hit["picture_id"] not in video_ids:
                video_url = hit["videos"]["large"]["url"] or max_hit["videos"]["medium"]["url"] or max_hit["videos"]["small"]["url"]
                if not video_url:
                  continue
                video_id = hit["picture_id"]
                video_ids.add(video_id);
                break;
    return { "auth": True, "message": "Successfully got video data", "videoUrl": video_url, "videoId": video_id }

@app.route("/api/v1/flask/keywords", methods=["POST"])
def post_keywords():
    body = request.get_json()
    if "text" not in body:
        return json.dumps({ "auth": False, "message": "Input text not found" })
    if type(body["text"]) != str:
        return json.dumps({ "auth": False, "message": "Invalid input text" })
    if not body["text"]:
        return json.dumps({ "auth": True, "message": "Successfully got keywords", "keywords": [] })
    keywords = get_keywords(body["text"]) or [body["text"]]
    keywords = [k[0] for k in Counter(keywords).most_common(5)]
    return json.dumps({ "auth": True, "message": "Successfully got keywords", "keywords": keywords })

@app.route("/api/v1/flask/video", methods=["POST"])
def post_video():
    body = request.get_json()
    if "text" not in body:
        return json.dumps({ "auth": False, "message": "Input text not found" })
    if type(body["text"]) != str or not body["text"]:
        return json.dumps({ "auth": False, "message": "Invalid input text" })
    if "keywords" not in body:
        return json.dumps({ "auth": False, "message": "Input keywords not found" })
    if type(body["keywords"]) != list:
        return json.dumps({ "auth": False, "message": "Invalid input keywords" })
    if "duration" not in body:
        return json.dumps({ "auth": False, "message": "Input duration not found" })
    if type(body["duration"]) not in (int, float) or not body["duration"]:
        return json.dumps({ "auth": False, "message": "Invalid input duration" })
    if "videoIds" not in body:
        return json.dumps({ "auth": False, "message": "Input videoIds not found" })
    if type(body["videoIds"]) != list:
        return json.dumps({ "auth": False, "message": "Invalid input videoIds" })
    res = get_video_data(body["text"], body["keywords"], body["duration"], set(body["videoIds"]))
    return json.dumps(res)

if __name__ == "__main__":
    print("Flask server listening on port:", PORT)
    http_server = WSGIServer(("", PORT), app)
    http_server.serve_forever()