import json
import os
import uvicorn
from datetime import datetime
from fastapi import FastAPI, HTTPException, status, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import List, Optional

# Novas importações para email
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig

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
    email: Optional[str] = None
    tipoProblema: str
    descricao: str

class Ticket(BaseModel):
    """Modelo completo de um ticket (como ele é salvo no JSON)"""
    id: str
    dataAbertura: str
    nome: str
    setor: str
    email: Optional[str] = None
    tipoProblema: str
    descricao: str
    status: str
    responsaveis: List[str]
    urgencia: str
    dataInicial: str
    dataFinal: str

# --- Configuração do App ---
app = FastAPI()

# Configuração do CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Funções Auxiliares (Banco de Dados JSON) ---

def load_config():
    """Carrega as configurações (setores, etc.) do arquivo config.json"""
    try:
        # Usa o caminho absoluto
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        # Se não achar o arquivo, cria uma config padrão
        default_config = {
            "sectors": ["... (config padrão omitida para brevidade) ..."],
            "it_team": ["Zanardi", "Castilho", "Mitcheuser", "Amorim"],
            "it_team_emails": [], # Novo
            "status_options": ["Em aberto", "Em andamento", "Aguardando peças", "Concluído"],
            "urgency_levels": ["Baixa", "Média", "Alta", "Crítica"],
            "credentials": { "username": "admin", "password": "hospital123" },
            "email_config": { "MAIL_USERNAME": "", "MAIL_PASSWORD": "", "MAIL_FROM": "", "MAIL_PORT": 587, "MAIL_SERVER": "", "MAIL_STARTTLS": True, "MAIL_SSL_TLS": False } # Novo
        }
        # Usa o caminho absoluto
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4)
        return default_config

def load_tickets_db():
    """Carrega todos os tickets do arquivo JSON"""
    # Usa o caminho absoluto
    if not os.path.exists(DB_FILE):
        return []
    try:
        # Usa o caminho absoluto
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [Ticket(**ticket) for ticket in data]
    except json.JSONDecodeError:
        return []
    except Exception:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            tickets_validos = []
            for ticket_data in data:
                ticket_data.pop("observacoesTI", None)
                try:
                    tickets_validos.append(Ticket(**ticket_data))
                except Exception:
                    continue
        save_tickets_db(tickets_validos)
        return tickets_validos


def save_tickets_db(tickets: List[Ticket]):
    """Salva a lista completa de tickets no arquivo JSON"""
    # Usa o caminho absoluto
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump([ticket.model_dump() for ticket in tickets], f, indent=4)

# --- Configuração de Email ---

# Carrega a configuração globalmente
config = load_config()

# Cria a configuração de conexão de email a partir do config.json
conf = ConnectionConfig(**config.get("email_config", {}))
fm = FastMail(conf)

async def send_notification_email(subject: str, recipients: List[str], body: str):
    """Função auxiliar para enviar emails"""
    
    # Filtra emails vazios ou None
    valid_recipients = [email for email in recipients if email and "@" in email]
    if not valid_recipients:
        print("Nenhum destinatário válido para o email.")
        return

    message = MessageSchema(
        subject=subject,
        recipients=valid_recipients,
        body=body,
        subtype="html" # Importante: Definido como HTML
    )
    
    try:
        await fm.send_message(message)
        print(f"Email enviado para: {valid_recipients}")
    except Exception as e:
        print(f"Erro ao enviar email: {e}")

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
async def create_ticket(ticket_in: TicketIn, background_tasks: BackgroundTasks):
    """
    Rota para um novo ticket ser criado (pelo formulário público)
    Agora inclui 'background_tasks' para enviar emails em segundo plano.
    """
    tickets = load_tickets_db()
    
    new_ticket = Ticket(
        id=f"TICKET-{int(datetime.now().timestamp() * 1000)}",
        dataAbertura=datetime.now().isoformat(),
        nome=ticket_in.nome,
        setor=ticket_in.setor,
        email=ticket_in.email,
        tipoProblema=ticket_in.tipoProblema,
        descricao=ticket_in.descricao,
        status="Em aberto",
        responsaveis=[],
        urgencia="Média",
        dataInicial="",
        dataFinal=""
    )
    
    tickets.append(new_ticket)
    save_tickets_db(tickets)
    
    # --- LÓGICA DE EMAIL (ATUALIZADA COM HTML) ---
    
    # 1. Enviar email de confirmação para o colaborador
    if new_ticket.email:
        subject_colaborador = f"Ticket #{new_ticket.id} Recebido - Hospital Santa Clara"
        
        # --- NOVO TEMPLATE HTML ---
        body_colaborador = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="width: 90%; max-width: 600px; margin: 20px auto; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
                <div style="background-color: #0066CC; color: #ffffff; padding: 20px; text-align: center;">
                    <h2>Hospital Santa Clara</h2>
                </div>
                <div style="padding: 30px;">
                    <p>Olá, <strong>{new_ticket.nome}</strong>!</p>
                    <p>Recebemos seu chamado com sucesso. Nossa equipe de TI já foi notificada e entrará em contato em breve.</p>
                    <p style="margin-top: 25px;"><strong>ID do Ticket:</strong></p>
                    <p style="font-size: 24px; font-weight: bold; color: #0052A3; text-align: center; margin-bottom: 25px;">{new_ticket.id}</p>
                    <p><strong>Problema Reportado:</strong><br/>{new_ticket.tipoProblema}</p>
                </div>
                <div style="background-color: #f9f9f9; text-align: center; padding: 20px; border-top: 1px solid #eee;">
                    <img src="https://i.imgur.com/DIPWvZA.png" alt="Logo Hospital Santa Clara" style="max-width: 200px;">
                </div>
            </div>
        </div>
        """
        # --- FIM DO TEMPLATE ---
        
        background_tasks.add_task(
            send_notification_email, 
            subject_colaborador, 
            [new_ticket.email], 
            body_colaborador
        )

    # 2. Enviar email de notificação para a equipe de TI
    it_emails = config.get("it_team_emails", [])
    if it_emails:
        subject_ti = f"Novo Ticket: #{new_ticket.id} ({new_ticket.setor})"
        
        # --- NOVO TEMPLATE HTML ---
        body_ti = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="width: 90%; max-width: 600px; margin: 20px auto; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
                <div style="background-color: #DC3545; color: #ffffff; padding: 20px; text-align: center;">
                    <h2>Novo Ticket Aberto</h2>
                </div>
                <div style="padding: 30px;">
                    <p>Um novo ticket foi aberto e requer atenção:</p>
                    <p style="margin-top: 25px;"><strong>ID do Ticket:</strong></p>
                    <p style="font-size: 24px; font-weight: bold; color: #0052A3; text-align: center; margin-bottom: 25px;">{new_ticket.id}</p>
                    <p><strong>Colaborador:</strong> {new_ticket.nome}</p>
                    <p><strong>Setor:</strong> {new_ticket.setor}</p>
                    <p><strong>Problema:</strong> {new_ticket.tipoProblema}</p>
                    <p><strong>Descrição:</strong><br/>{new_ticket.descricao}</p>
                    <p style="text-align: center; margin-top: 30px;">Acesse o painel para gerenciar.</p>
                </div>
                <div style="background-color: #f9f9f9; text-align: center; padding: 20px; border-top: 1px solid #eee;">
                    <img src="https://i.imgur.com/DIPWvZA.png" alt="Logo Hospital Santa Clara" style="max-width: 200px;">
                </div>
            </div>
        </div>
        """
        # --- FIM DO TEMPLATE ---
        
        background_tasks.add_task(
            send_notification_email, 
            subject_ti, 
            it_emails, 
            body_ti
        )
    
    return new_ticket

@app.put("/api/tickets/{ticket_id}", response_model=Ticket)
async def update_ticket_route(ticket_id: str, ticket_update: Ticket, background_tasks: BackgroundTasks):
    """
    Rota para atualizar um ticket existente.
    Agora inclui 'background_tasks' para enviar emails de atualização.
    """
    tickets = load_tickets_db()
    
    index_to_update = -1
    old_status = ""
    for i, ticket in enumerate(tickets):
        if ticket.id == ticket_id:
            index_to_update = i
            old_status = ticket.status # Guarda o status antigo
            break
            
    if index_to_update == -1:
        raise HTTPException(status_code=404, detail="Ticket não encontrado")
    
    new_status = ticket_update.status
    
    ticket_update.id = ticket_id 
    tickets[index_to_update] = ticket_update
    
    save_tickets_db(tickets)
    
    # --- LÓGICA DE EMAIL (ATUALIZADA COM HTML) ---
    
    # 3. Enviar email de atualização de status para o colaborador
    if new_status != old_status and ticket_update.email:
        subject_update = f"Atualização Ticket #{ticket_id}: Status mudou para {new_status}"
        
        # --- NOVO TEMPLATE HTML ---
        body_update = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="width: 90%; max-width: 600px; margin: 20px auto; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
                <div style="background-color: #FFC107; color: #333; padding: 20px; text-align: center;">
                    <h2>Atualização do seu Ticket</h2>
                </div>
                <div style="padding: 30px;">
                    <p>Olá, <strong>{ticket_update.nome}</strong>!</p>
                    <p>O status do seu ticket #{ticket_id} foi atualizado.</p>
                    
                    <p><strong>Status Anterior:</strong> {old_status}</p>
                    <p><strong>Novo Status:</strong> {new_status}</p>
                    
                    <p style="margin-top: 25px;"><strong>Problema Reportado:</strong><br/>{ticket_update.tipoProblema}</p>
                </div>
                <div style="background-color: #f9f9f9; text-align: center; padding: 20px; border-top: 1px solid #eee;">
                    <img src="https://i.imgur.com/DIPWvZA.png" alt="Logo Hospital Santa Clara" style="max-width: 200px;">
                </div>
            </div>
        </div>
        """
        # --- FIM DO TEMPLATE ---

        background_tasks.add_task(
            send_notification_email, 
            subject_update, 
            [ticket_update.email], 
            body_update
        )

    return tickets[index_to_update]


# --- Servir o Front-end (index.html) ---

@app.get("/")
async def get_index():
    """Serve o arquivo index.html principal"""
    # Usa o caminho absoluto
    return FileResponse(INDEX_FILE)

# --- Execução do Servidor ---

if __name__ == "__main__":
    print("Iniciando servidor FastAPI em http://127.0.0.1:5000")
    # host="0.0.0.0" permite que outras máquinas na rede acessem o servidor
    uvicorn.run(app, host="0.0.0.0", port=5000)