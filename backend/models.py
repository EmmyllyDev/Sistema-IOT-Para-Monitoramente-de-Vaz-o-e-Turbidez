from sqlalchemy import Column, Integer, Float, DateTime, String, Boolean
from .database import Base
from datetime import datetime

class Monitoramento(Base):
    __tablename__ = "leituras_sigua"

    id = Column(Integer, primary_key=True, index=True)
    # ISO 8601 é o padrão para data/hora em JSON
    horario = Column(DateTime, default=datetime.utcnow) 
    turbidez_ntu = Column(Float)
    vazao_ls = Column(Float)
    nivel_cm = Column(Float)
    status_conformidade = Column(Boolean)