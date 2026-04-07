from fastapi import FastAPI, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from . import models, database

app = FastAPI()

# Este é o "contrato" do seu JSON para a Issue #10
class LeituraSchema(BaseModel):
    turbidez: float
    vazao: float
    nivel: float

@app.post("/sensor/data")
def receber_dados(data: LeituraSchema, db: Session = Depends(database.get_db)):
    # Lógica de validação da Portaria 888/2021
    status = True if data.turbidez <= 5.0 else False
    
    nova_leitura = models.Monitoramento(
        turbidez_ntu=data.turbidez,
        vazao_ls=data.vazao,
        nivel_cm=data.nivel,
        status_conformidade=status
    )
    
    db.add(nova_leitura)
    db.commit()
    return {"message": "Dados recebidos com sucesso!", "status": status}