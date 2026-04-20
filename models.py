from sqlalchemy import Column, Integer, String, Boolean, DateTime
from database import Base
import security
from datetime import datetime
import json

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Configuration 
    bot_enabled = Column(Boolean, default=False)
    notification_time = Column(String, default="08:00") # "HH:MM" e.g. 08:30
    _watch_senders = Column("watch_senders", String, default="") # JSON list of strings

    # Encrypted fields
    _gmail_token_json_encrypted = Column("gmail_token_json_encrypted", String, default="")
    _twilio_sid_encrypted = Column("twilio_sid_encrypted", String, default="")
    _twilio_token_encrypted = Column("twilio_token_encrypted", String, default="")
    _twilio_from_encrypted = Column("twilio_from_encrypted", String, default="")
    _whatsapp_phone_encrypted = Column("whatsapp_phone_encrypted", String, default="")

    # Scraper and Keyword Settings (Encrypted choice)
    _watch_keywords_encrypted = Column("watch_keywords_encrypted", String, default="")
    _enable_devpost_encrypted = Column("enable_devpost_encrypted", String, default="") # Stored as "true"/"false"
    _enable_unstop_encrypted = Column("enable_unstop_encrypted", String, default="")   # Stored as "true"/"false"

    @property
    def watch_senders(self):
        if not self._watch_senders:
            return []
        try:
            return json.loads(self._watch_senders)
        except:
            return []

    @watch_senders.setter
    def watch_senders(self, senders_list):
        self._watch_senders = json.dumps(senders_list)

    @property
    def watch_keywords(self):
        val = security.decrypt_data(self._watch_keywords_encrypted)
        if not val:
            return []
        try:
            return json.loads(val)
        except:
            return []

    @watch_keywords.setter
    def watch_keywords(self, value_list):
        self._watch_keywords_encrypted = security.encrypt_data(json.dumps(value_list))

    @property
    def enable_devpost(self):
        val = security.decrypt_data(self._enable_devpost_encrypted)
        return val.lower() == "true"

    @enable_devpost.setter
    def enable_devpost(self, value: bool):
        self._enable_devpost_encrypted = security.encrypt_data("true" if value else "false")

    @property
    def enable_unstop(self):
        val = security.decrypt_data(self._enable_unstop_encrypted)
        return val.lower() == "true"

    @enable_unstop.setter
    def enable_unstop(self, value: bool):
        self._enable_unstop_encrypted = security.encrypt_data("true" if value else "false")

    @property
    def gmail_token_json(self):
        return security.decrypt_data(self._gmail_token_json_encrypted)

    @gmail_token_json.setter
    def gmail_token_json(self, value):
        self._gmail_token_json_encrypted = security.encrypt_data(value)

    @property
    def twilio_sid(self):
        return security.decrypt_data(self._twilio_sid_encrypted)

    @twilio_sid.setter
    def twilio_sid(self, value):
        self._twilio_sid_encrypted = security.encrypt_data(value)

    @property
    def twilio_token(self):
        return security.decrypt_data(self._twilio_token_encrypted)

    @twilio_token.setter
    def twilio_token(self, value):
        self._twilio_token_encrypted = security.encrypt_data(value)

    @property
    def twilio_from(self):
        return security.decrypt_data(self._twilio_from_encrypted)

    @twilio_from.setter
    def twilio_from(self, value):
        self._twilio_from_encrypted = security.encrypt_data(value)

    @property
    def whatsapp_phone(self):
        return security.decrypt_data(self._whatsapp_phone_encrypted)

    @whatsapp_phone.setter
    def whatsapp_phone(self, value):
        self._whatsapp_phone_encrypted = security.encrypt_data(value)
