from sqlalchemy import Column, Integer, String, Boolean
from core.database import Base

class GeminiModel(Base):
    __tablename__ = 'gemini_models'

    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String, unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)