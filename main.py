import pickle
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import imaplib
import email
from email.header import decode_header
from datetime import datetime

with open("model.pkl", "rb") as f:
    model = pickle.load(f)

print("Model loaded!")

app = FastAPI()
app.add_middleware(CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class IMAPRequest(BaseModel):
    email_address: str
    app_password: str
    max_emails: int = 20

def fetch_and_classify(email_address: str, app_password: str, max_emails: int = 20):
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_address, app_password)
        mail.select("inbox")

        _, messages = mail.search(None, "ALL")
        email_ids = messages[0].split()
        latest = email_ids[-max_emails:]
        latest.reverse()

        classified = []
        for eid in latest:
            _, msg_data = mail.fetch(eid, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

            subject_raw = msg.get("Subject", "No Subject")
            subject_parts = decode_header(subject_raw)
            subject = ""
            for part, enc in subject_parts:
                if isinstance(part, bytes):
                    subject += part.decode(enc or "utf-8", errors="ignore")
                else:
                    subject += str(part)

            sender = msg.get("From", "Unknown")
            snippet = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True)
                        if body:
                            snippet = body.decode("utf-8", errors="ignore")[:150]
                            break
            else:
                body = msg.get_payload(decode=True)
                if body:
                    snippet = body.decode("utf-8", errors="ignore")[:150]

            text_to_classify = f"{subject} {snippet}"
            label = model.predict([text_to_classify])[0].strip()

            if label.lower() == "important":
                label = "Important"
            elif label.lower() == "high":
                label = "High"
            elif label.lower() == "low":
                label = "Low"

            proba = model.predict_proba([text_to_classify])[0]
            confidence = round(max(proba) * 100, 1)

            classified.append({
                "id": str(eid),
                "subject": subject,
                "sender": sender,
                "snippet": snippet[:100],
                "label": label,
                "confidence": f"{confidence}%",
                "timestamp": datetime.now().isoformat(),
            })

        mail.logout()
        return classified

    except Exception as e:
        print(f"Error: {e}")
        return []

@app.post("/fetch-with-credentials")
def fetch_with_credentials(request: IMAPRequest):
    emails = fetch_and_classify(
        request.email_address,
        request.app_password,
        request.max_emails
    )
    if not emails:
        return {"error": "Invalid credentials or could not fetch emails"}
    return {"emails": emails}

@app.get("/")
def root():
    return {"status": "AutoBot email classifier running!"}
