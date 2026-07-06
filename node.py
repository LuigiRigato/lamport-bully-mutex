import argparse
import asyncio
import httpx
import uvicorn
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager

NODES = {
    1: "http://localhost:5001",
    2: "http://localhost:5002",
    3: "http://localhost:5003"
}

class State:
    def __init__(self, node_id):
        self.node_id = node_id
        self.port = 5000 + node_id
        self.relogio_local = 0
        self.estado_mutex = "RELEASED"
        self.timestamp_requisicao = 0
        self.deferidos = []
        self.respostas_recebidas = set()
        self.lider = max(NODES.keys())

    def atualizar_relogio(self, timestamp_recebido):
        self.relogio_local = max(self.relogio_local, int(timestamp_recebido)) + 1

    def get_headers(self):
        return {
            "sender_id": str(self.node_id), 
            "timestamp": str(self.relogio_local)
        }

node_state: State = State(0) # dummy initialization, set in main

@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"Iniciando nó. Disparando eleição inicial...")
    asyncio.create_task(iniciar_eleicao())
    print(f"Iniciando tarefa de monitoramento do líder...")
    task = asyncio.create_task(monitorar_lider())
    yield
    print(f"Encerrando tarefa de monitoramento...")
    task.cancel()

app = FastAPI(lifespan=lifespan)

class LamportMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        timestamp = request.headers.get("timestamp")
        if timestamp:
            node_state.atualizar_relogio(timestamp)
        else:
            node_state.relogio_local += 1
        return await call_next(request)

app.add_middleware(LamportMiddleware)

async def send_request(target_id, endpoint, method="POST", data=None):
    url = f"{NODES[target_id]}{endpoint}"
    async with httpx.AsyncClient() as client:
        try:
            headers = node_state.get_headers()
            if method == "POST":
                response = await client.post(url, json=data or {}, headers=headers, timeout=2.0)
            else:
                response = await client.get(url, headers=headers, timeout=2.0)
            
            if response.status_code == 200:
                return True
            return False
        except Exception:
            return False

@app.post("/eleicao")
async def eleicao(request: Request):
    sender_id = int(request.headers.get("sender_id"))
    print(f"⚠️ Recebi mensagem de ELEIÇÃO do Nó {sender_id}")
    if sender_id < node_state.node_id:
        asyncio.create_task(iniciar_eleicao())
    return {"status": "ok"}

@app.post("/coordenador")
async def coordenador(request: Request):
    node_state.lider = int(request.headers.get("sender_id"))
    print(f"👑 Novo líder definido: Nó {node_state.lider}")
    return {"status": "ok"}

@app.get("/ping")
async def ping(request: Request):
    sender_id = request.headers.get("sender_id", "Desconhecido")
    print(f"💓 Ping recebido do Nó {sender_id}")
    return {"status": "alive"}

@app.post("/requisitar_recurso")
async def requisitar_recurso(request: Request):
    sender_id = int(request.headers.get("sender_id"))
    timestamp = int(request.headers.get("timestamp"))
    if (
        node_state.estado_mutex == "HELD" 
        or (
            node_state.estado_mutex == "WANTED" 
            and (
                node_state.timestamp_requisicao < timestamp 
                or (
                    node_state.timestamp_requisicao == timestamp 
                    and node_state.node_id < sender_id
                )
            )
        )
    ):
        node_state.deferidos.append(sender_id)
        print(f"🔒 Pedido do Nó {sender_id} colocado na fila de espera (defer).")
        return {"status": "deferred"}
    await send_request(sender_id, "/responder_ok")
    return {"status": "ok"}

@app.post("/responder_ok")
async def responder_ok(request: Request):
    sender_id = int(request.headers.get("sender_id"))
    node_state.respostas_recebidas.add(sender_id)
    print(f"✅ Recebi OK do Nó {sender_id} (Total: {len(node_state.respostas_recebidas)}/{len(NODES) - 1})")
    return {"status": "ok"}

@app.post("/iniciar_mutex")
async def iniciar_mutex():
    node_state.estado_mutex = "WANTED"
    node_state.timestamp_requisicao = node_state.relogio_local
    node_state.respostas_recebidas = set()
    
    print(f"⏳ Solicitando acesso à Região Crítica (Tempo Lógico: {node_state.timestamp_requisicao})...")
    
    for n_id in NODES:
        if n_id != node_state.node_id:
            sucesso = await send_request(n_id, "/requisitar_recurso")
            if not sucesso:
                print(f"⚠️ Nó {n_id} está offline. Assumindo OK implícito.")
                node_state.respostas_recebidas.add(n_id)
    
    while len(node_state.respostas_recebidas) < len(NODES) - 1:
        await asyncio.sleep(0.5)
    
    node_state.estado_mutex = "HELD"
    print(f"🔥 Nó {node_state.node_id}: HELD - Acessando recurso crítico")
    
    with open("recurso.txt", "a", encoding="utf-8") as f:
        f.write(f"Nó {node_state.node_id} acessou às {node_state.relogio_local} (Tempo Lógico)\n")
        
    await asyncio.sleep(20)
    node_state.estado_mutex = "RELEASED"
    print(f"🚪 Nó {node_state.node_id}: RELEASED - Saindo do recurso crítico.")

    for d_id in node_state.deferidos:
        print(f"✉️  Enviando OK atrasado para o Nó {d_id} que estava na fila.")
        await send_request(d_id, "/responder_ok")
    
    node_state.deferidos = []
    return {"status": "released"}

async def iniciar_eleicao():
    maiores = [n for n in NODES if n > node_state.node_id]
    if not maiores:
        node_state.lider = node_state.node_id
        for n in NODES:
            if n != node_state.node_id:
                await send_request(n, "/coordenador")
    else:
        alguem_respondeu = False
        for n in maiores:
            respondeu = await send_request(n, "/eleicao")
            if respondeu:
                alguem_respondeu = True
                
        if not alguem_respondeu:
            node_state.lider = node_state.node_id
            print(f"Nenhum nó maior ativo. Assumindo a liderança (Nó {node_state.node_id})!")
            for n in NODES:
                if n != node_state.node_id:
                    await send_request(n, "/coordenador")

async def monitorar_lider():
    while True:
        await asyncio.sleep(5)
        if node_state.node_id != node_state.lider:
            try:
                async with httpx.AsyncClient() as client:
                    headers = node_state.get_headers()
                    response = await client.get(
                        f"{NODES[node_state.lider]}/ping", 
                        headers=headers,
                        timeout=2.0
                    )
                    response.raise_for_status()
            except:
                print(f"Líder {node_state.lider} caiu! Iniciando eleição...")
                await iniciar_eleicao()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True)
    args = parser.parse_args()
    
    node_state = State(args.id)
    
    uvicorn.run(app, host="0.0.0.0", port=node_state.port, reload=False)