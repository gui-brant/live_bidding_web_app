from __future__ import annotations

import asyncio
import os
from dataclasses import asdict
from datetime import datetime
from typing import Optional

import smtplib
from email.message import EmailMessage

from .interfaces import OtpChallenge, EmailService


class MongoOtpRepository:
    #Mongo-backed OTP repository. Expects an AsyncIOMotorCollection-like object.

    def __init__(self, collection) -> None:
        self._col = collection

    async def create_or_replace(self, email: str, challenge: OtpChallenge) -> None:
        doc = {
            "email": email,
            "code_hash": challenge.code_hash,
            "code_salt": challenge.code_salt,
            "expires_at": challenge.expires_at,
            "attempts_left": challenge.attempts_left,
            "next_send_allowed_at": challenge.next_send_allowed_at,
        }
        await self._col.replace_one({"email": email}, doc, upsert=True)

    async def get(self, email: str) -> Optional[OtpChallenge]:
        doc = await self._col.find_one({"email": email})
        if not doc:
            return None
        return OtpChallenge(
            email=doc["email"],
            code_hash=doc["code_hash"],
            code_salt=doc["code_salt"],
            expires_at=doc["expires_at"],
            attempts_left=doc.get("attempts_left", 0),
            next_send_allowed_at=doc.get("next_send_allowed_at"),
        )

    async def decrement_attempts(self, email: str) -> int:
        # Atomically decrement attempts and return remaining.
        res = await self._col.find_one_and_update(
            {"email": email},
            {"$inc": {"attempts_left": -1}},
            return_document=True,
        )
        if not res:
            return 0
        return res.get("attempts_left", 0)

    async def delete(self, email: str) -> None:
        await self._col.delete_one({"email": email})


class SmtpEmailService:
    
    # Simple SMTP email service. Sends plain-text OTP emails.

    def __init__(self) -> None:
        # credentials are hardcoded per request
        self.username = "donotreply.kognativesales7@gmail.com"
        self.password = "tnof pqwg ihhk pqxl"
        # the rest are fixed defaults
        self.host = "smtp.gmail.com"
        self.port = 587
        # default from address uses the username
        self.from_address = self.username
        self.use_tls = True

    async def send_otp(self, email: str, code: str) -> None:
        # Offload blocking network IO to thread pool.
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._send_sync, email, code)

    def _send_sync(self, email: str, code: str) -> None:
        msg = EmailMessage()
        msg["From"] = self.from_address
        msg["To"] = email
        msg["Subject"] = "Your verification code"
        body = "Your verification code is: {code}"
        msg.set_content(body.format(code=code))

        if not self.username or not self.password:
            # If credentials missing, raise so caller knows sending failed.
            raise RuntimeError("SMTP_USERNAME and SMTP_PASSWORD must be set to send email.")

        with smtplib.SMTP(f"{self.host}", self.port, timeout=10) as server:
            server.ehlo()
            if self.use_tls:
                server.starttls()
                server.ehlo()
            server.login(self.username, self.password)
            server.send_message(msg)
