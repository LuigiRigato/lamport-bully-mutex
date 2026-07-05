import argparse
import asyncio
import httpx
import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel
from config import NODES

app = FastAPI()

class State:
    def __init__(self, node_id):
        self.node_id = node_id
        self.port = 5000 + node_id
        self.relogio_local = 0
        self.estado_mutex = "RELEASED"  # RELEASED, WANTED, HELD
        self.deferidos = [] # Lista de nós esperando resposta
        self.respostas_recebidas = set()
        self.lider = max(NODES.keys()) # Inicialmente, o maior ID é o líder
        self.lock = asyncio.Lock()

    def evento_interno(self):
        self.relogio_local += 1
        return self.relogio_local

    def atualizar_relogio(self, timestamp_recebido):
        self.relogio_local = max(self.relogio_local, timestamp_recebido) + 1

    def get_headers(self):
        return {"sender_id": str(self.node_id), "timestamp": str(self.relogio_local)}

node_state = None

class Message(BaseModel):
    sender_id: int
    timestamp: int
    conteudo: str = ""

async def send_request(target_id, endpoint, method="POST", data=None):
    url = f"{NODES[target_id]}{endpoint}"
    async with httpx.AsyncClient() as client:
        try:
            headers = node_state.get_headers()
            if method == "POST":
                await client.post(url, json=data, headers=headers)
            else:
                await client.get(url, headers=headers)
        except Exception as e:
            print(f"Erro ao enviar para {target_id}: {e}")
            return False
    return True

# --- Endpoints ---
@app.post("/eleicao")
async def eleicao(request: Request):
    # Lógica simples: se receber, apenas aceita que eleição está ocorrendo
    # Em uma implementação robusta, deveria responder OK e iniciar sua própria eleição
    return {"status": "ok"}

@app.post("/coordenador")
async def coordenador(data: Message):
    node_state.lider = data.sender_id
    print(f"Novo líder: {node_state.lider}")
    return {"status": "ok"}

@app.get("/ping")
async def ping():
    return {"status": "alive"}

@app.post("/requisitar_recurso")
async def requisitar_recurso(data: Message):
    # Regra de Ricart-Agrawala
    if node_state.estado_mutex == "HELD" or (node_state.estado_mutex == "WANTED" and (node_state.relogio_local < data.timestamp or (node_state.relogio_local == data.timestamp and node_state.node_id < data.sender_id))):
        node_state.deferidos.append(data.sender_id)
        return {"status": "deferred"}
    
    # Enviar OK
    await send_request(data.sender_id, "/responder_ok")
    return {"status": "ok"}

@app.post("/responder_ok")
async def responder_ok(request: Request):
    sender_id = int(request.headers.get("sender_id"))
    node_state.respostas_recebidas.add(sender_id)
    return {"status": "ok"}

# --- Background Task: Bully Monitoring ---
async def monitorar_lider():
    while True:
        await asyncio.sleep(5)
        if node_state.node_id != node_state.lider:
            # Ping no líder
            url = f"{NODES[node_state.lider]}/ping"
            try:
                async with httpx.AsyncClient() as client:
                    await client.get(url, timeout=2.0)
            except:
                print(f"Líder {node_state.lider} caiu! Iniciando eleição.")
                # Lógica de eleição
                maiores = [n for n in NODES if n > node_state.node_id]
                if not maiores:
                    node_state.lider = node_state.node_id
                    for n in NODES:
                        if n != node_state.node_id:
                            await send_request(n, "/coordenador", data={"sender_id": node_state.node_id, "timestamp": node_state.relogio_local})
                else:
                    for n in maiores:
                        await send_request(n, "/eleicao")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(monitorar_lider())

# --- Main ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True)
    args = parser.parse_args()
    
    node_state = State(args.id)
    
    uvicorn.run(app, host="0.0.0.0", port=node_state.port)
