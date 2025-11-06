import json
import os
import uvicorn
from datetime import datetime
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import List, Optional

# --- Constantes ---
DB_FILE = "tickets.json"

# --- Modelos de Dados (Pydantic) ---

class LoginPayload(BaseModel):
    username: str
    password: str

class TicketIn(BaseModel):
    """Modelo para criar um novo ticket (dados que vêm do formulário)"""
    nome: str
    setor: str
    email: Optional[str] = None # Trocado de EmailStr para str
    tipoProblema: str
    descricao: str

class Ticket(BaseModel):
    """Modelo completo de um ticket (como ele é salvo no JSON)"""
    id: str
    dataAbertura: str
    nome: str
    setor: str
    email: Optional[str] = None # Trocado de EmailStr para str
    tipoProblema: str
    descricao: str
    status: str
    responsaveis: List[str]
    urgencia: str
    dataInicial: str
    dataFinal: str
    # O campo observacoesTI foi removido daqui

# --- Configuração do App ---
app = FastAPI()

# Configuração do CORS (Cross-Origin Resource Sharing)
# Permite que o front-end (index.html) acesse o back-end (FastAPI)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite todas as origens (para testes)
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos os métodos (GET, POST, PUT, etc.)
    allow_headers=["*"],  # Permite todos os cabeçalhos
)

# --- Funções Auxiliares (Banco de Dados JSON) ---

def load_config():
    """Carrega as configurações (setores, etc.) do arquivo config.json"""
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        # Se não achar o arquivo, cria uma config padrão
        default_config = {
            "sectors": [
                "Administrativo", "Faturamento Convênios", "Faturamento SUS", 
                "Pré-Faturamento", "Recepção Especialidades", "Recepção Imagens", 
                "Recepção P.A", "P.A", "Hemodiálise", "Farmácia", "SHIBATA", 
                "PALANDRI", "ALMOXARIFADO", "CONTABILIDADE", "TESOURARIA", 
                "FAE", "RH", "AUDITORIA", "UTI", "CENTRO CIRÚRGICO", "MANUTENÇÃO"
            ],
            "it_team": ["Zanardi", "Castilho", "Mitcheuser", "Amorim"],
            "status_options": ["Em aberto", "Em andamento", "Aguardando peças", "Concluído"],
            "urgency_levels": ["Baixa", "Média", "Alta", "Crítica"],
            "credentials": {
                "username": "admin",
                "password": "hospital123"
            }
        }
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4)
        return default_config

def load_tickets_db():
    """Carrega todos os tickets do arquivo JSON"""
    if not os.path.exists(DB_FILE):
        return [] # Retorna lista vazia se o arquivo não existe
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Converte os dicts para instâncias do modelo Ticket
            return [Ticket(**ticket) for ticket in data]
    except json.JSONDecodeError:
        return [] # Retorna lista vazia se o JSON estiver mal formatado
    except Exception: # Pega outros erros de validação do Pydantic se o JSON estiver defasado
        # Se um ticket antigo tiver 'observacoesTI', o Pydantic vai falhar
        # Vamos carregar os dados brutos e filtrar
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            tickets_validos = []
            for ticket_data in data:
                ticket_data.pop("observacoesTI", None) # Remove o campo problemático
                try:
                    tickets_validos.append(Ticket(**ticket_data))
                except Exception:
                    continue # Ignora o ticket se ainda for inválido
        save_tickets_db(tickets_validos) # Salva a lista limpa
        return tickets_validos


def save_tickets_db(tickets: List[Ticket]):
    """Salva a lista completa de tickets no arquivo JSON"""
    with open(DB_FILE, "w", encoding="utf-8") as f:
        # Converte as instâncias do modelo Ticket de volta para dicts
        json.dump([ticket.model_dump() for ticket in tickets], f, indent=4)

# Carrega a configuração globalmente
config = load_config()

# --- Rotas da API ---

@app.get("/api/config")
async def get_config():
    """Rota para o front-end buscar as listas de setores, equipe, etc."""
    return config

@app.post("/api/login")
async def login(payload: LoginPayload):
    """Rota para validar o login da equipe de TI"""
    creds = config.get("credentials", {})
    if payload.username == creds.get("username") and payload.password == creds.get("password"):
        return {"message": "Login bem-sucedido"}
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos"
        )

@app.get("/api/tickets", response_model=List[Ticket])
async def get_all_tickets():
    """Rota para listar todos os tickets abertos"""
    return load_tickets_db()

@app.post("/api/tickets", response_model=Ticket, status_code=status.HTTP_201_CREATED)
async def create_ticket(ticket_in: TicketIn):
    """Rota para um novo ticket ser criado (pelo formulário público)"""
    tickets = load_tickets_db()
    
    # Cria o novo ticket completo
    new_ticket = Ticket(
        id=f"TICKET-{int(datetime.now().timestamp() * 1000)}", # ID único
        dataAbertura=datetime.now().isoformat(),
        nome=ticket_in.nome,
        setor=ticket_in.setor,
        email=ticket_in.email,
        tipoProblema=ticket_in.tipoProblema,
        descricao=ticket_in.descricao,
        status="Em aberto", # Status padrão
        responsaveis=[],
        urgencia="Média", # Urgência padrão
        dataInicial="",
        dataFinal=""
        # O campo observacoesTI foi removido daqui
    )
    
    tickets.append(new_ticket)
    save_tickets_db(tickets)
    return new_ticket

@app.put("/api/tickets/{ticket_id}", response_model=Ticket)
async def update_ticket_route(ticket_id: str, ticket_update: Ticket):
    """
    Rota para atualizar um ticket existente.
    Recebe o ticket *inteiro* e atualizado do front-end.
    """
    tickets = load_tickets_db()
    
    # Encontra o índice do ticket a ser atualizado
    index_to_update = -1
    for i, ticket in enumerate(tickets):
        if ticket.id == ticket_id:
            index_to_update = i
            break
            
    if index_to_update == -1:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    # CORREÇÃO: Substitui o ticket antigo pelo novo ticket (ticket_update)
    # que veio do front-end, garantindo que o ID seja o mesmo.
    ticket_update.id = ticket_id 
    tickets[index_to_update] = ticket_update
    
    # Salva a lista inteira de tickets no banco de dados
    save_tickets_db(tickets)
    
    # Retorna o ticket que foi salvo
    return tickets[index_to_update]


# --- Servir o Front-end (index.html) ---

@app.get("/")
async def get_index():
    """Serve o arquivo index.html principal"""
    return FileResponse("index.html")

# --- Execução do Servidor ---

if __name__ == "__main__":
    print("Iniciando servidor FastAPI em http://127.0.0.1:5000")
    # host="0.0.0.0" permite que outras máquinas na rede acessem o servidor
    uvicorn.run(app, host="0.0.0.0", port=5000)