import json
from datetime import date
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base


class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    open_time = Column(String, default="11:00")   # "HH:MM" (JST)
    token = Column(String, unique=True, index=True, nullable=True)  # 店舗専用URL用の秘密キー
    passcode = Column(String, nullable=True)                        # 店舗ログイン用パスワード（番号）
    alerted_on = Column(Date, nullable=True)        # last date an "unopened" alert was sent

    open_reports = relationship("OpenReport", back_populates="store")
    close_reports = relationship("CloseReport", back_populates="store")


class OpenReport(Base):
    __tablename__ = "open_reports"

    id = Column(Integer, primary_key=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    report_date = Column(Date, nullable=False)
    opened_at = Column(DateTime, nullable=False)
    reporter = Column(String, nullable=True)
    memo = Column(Text, nullable=True)
    photos_json = Column(Text, default="[]")

    store = relationship("Store", back_populates="open_reports")

    @property
    def photos(self):
        try:
            return json.loads(self.photos_json or "[]")
        except Exception:
            return []


class CloseReport(Base):
    __tablename__ = "close_reports"

    id = Column(Integer, primary_key=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    report_date = Column(Date, nullable=False)
    closed_at = Column(DateTime, nullable=False)
    reporter = Column(String, nullable=True)
    handover = Column(Text, nullable=True)          # 翌日への引き継ぎ事項
    photos_json = Column(Text, default="[]")

    store = relationship("Store", back_populates="close_reports")

    @property
    def photos(self):
        try:
            return json.loads(self.photos_json or "[]")
        except Exception:
            return []
