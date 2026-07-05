# LAMPORT-BULLY-MUTEX: Algoritmos em Sistemas Distribuídos

Este repositório contém a implementação de três algoritmos clássicos de coordenação e sincronização em Sistemas Distribuídos: **Relógio Lógico de Lamport**, **Eleição de Líder (Algoritmo do Valentão/Bully)** e **Exclusão Mútua (Ricart-Agrawala)**.

---

## 🏗️ Arquitetura e Decisões de Design

O projeto foi desenvolvido em **Python 3** utilizando comunicação através de requisições HTTP. Cada "nó" do sistema distribuído é, na verdade, um servidor web independente.

**Por que HTTP e FastAPI?**
Optou-se por utilizar o **FastAPI** em vez de frameworks web tradicionais síncronos. O FastAPI é construído nativamente sobre a norma ASGI e otimizado para o padrão `asyncio` do Python. Sendo os sistemas distribuídos fortemente limitados por I/O (rede), a natureza assíncrona permite que um nó lide com requisições concorrentes de forma extremamente eficiente. Por exemplo, um nó pode colocar uma resposta de exclusão mútua em espera (na fila de deferidos) sem bloquear o servidor, continuando a responder a requisições de *ping* e convocações de eleição em paralelo.

## ⚙️ Algoritmos Implementados

1. **Relógios Lógicos de Lamport:**
* Implementado através de um *Middleware* central que intercepta todas as requisições HTTP recebidas. O *timestamp* é enviado nos cabeçalhos (`headers`) de cada mensagem de saída.
* Regra matemática aplicada: `Relógio Local = max(Relógio Local, Timestamp Recebido) + 1`.


2. **Algoritmo do Valentão (Bully):**
* Os nós monitoram ativamente o líder atual através de requisições HTTP `GET /ping` a cada 5 segundos.
* Se houver falha de resposta (*timeout*), o nó detecta a queda do coordenador e inicia uma eleição enviando `POST /eleicao` para os nós com IDs maiores.
* Se não obtiver resposta dos IDs maiores (indicando que ele é o maior nó ativo), declara-se o novo coordenador e avisa os nós menores via `POST /coordenador`. O sistema é totalmente tolerante a falhas do líder.


3. **Algoritmo de Ricart-Agrawala (Exclusão Mútua):**
* Gerencia o acesso a um recurso crítico compartilhado (simulado pela escrita no arquivo `recurso.txt`).
* Utiliza os *timestamps* de Lamport para definir prioridades em caso de pedidos concorrentes (desempatando pelo menor ID em caso de timestamps iguais).
* **Melhoria (Tolerância a Falhas):** O algoritmo original foi ajustado para evitar *deadlocks*. Se um nó solicitar acesso ao recurso e um dos nós da rede estiver inacessível (offline), o nó solicitante assume um "OK implícito" em vez de ficar bloqueado infinitamente à espera de uma resposta impossível.



---

## 🚀 Como Executar o Projeto

### Pré-requisitos

Certifique-se de que tem o Python instalado em sua máquina e instale as dependências do projeto:

```bash
pip install -r requirements.txt
```

### Iniciar o Cluster

Você pode iniciar cada nó individualmente em terminais separados utilizando `python node.py --id 1`, `python node.py --id 2` e `python node.py --id 3`

Os nós estarão disponíveis em:

* Nó 1: `http://localhost:5001`
* Nó 2: `http://localhost:5002`
* Nó 3: `http://localhost:5003`

---

## 🧪 Como Testar

Após iniciar os nós, você pode utilizar o comando `curl` em outro terminal (ou ferramentas como o Postman/Insomnia) para simular eventos na rede.

### 1. Testar Eleição e Tolerância a Falhas (Bully)

Acompanhe os logs nos terminais e proceda da seguinte forma:

1. O sistema inicia e o Nó 3 (maior ID) assume naturalmente como líder.
2. Force a parada do Nó 3 (Pressione `Ctrl+C` no terminal correspondente ao Nó 3).
3. Aguarde cerca de 5 segundos. Os Nós 1 e 2 detectarão a falha. O Nó 2 invocará uma eleição, enviará mensagem ao Nó 3, não terá resposta e assumirá a liderança, notificando o Nó 1 imediatamente.

### 2. Testar Exclusão Mútua Simples (Ricart-Agrawala)

Simule o pedido de acesso à seção crítica por parte de um nó:

```bash
curl -X POST http://localhost:5001/iniciar_mutex

```

* **Resultado:** O Nó 1 entra em estado `HELD`, registra o evento no arquivo `recurso.txt` com o seu *timestamp* de Lamport atual e sai após a simulação de uso (20 segundos), enviando as mensagens de `OK` (release) necessárias.

### 3. Testar Concorrência Pura (Ricart-Agrawala)

Para validar a prioridade de Lamport e a correta formação da fila de `defer` (atraso de resposta), envie pedidos simultâneos para dois nós diferentes:

```bash
# Terminal A
curl -X POST http://localhost:5001/iniciar_mutex

# Terminal B
curl -X POST http://localhost:5002/iniciar_mutex

```

* **Resultado:** Pressione Enter em ambos os terminais quase ao mesmo tempo. Apenas o nó com maior prioridade (menor relógio lógico ou, em caso de empate, menor ID) obterá permissão imediata. O segundo nó será colocado na fila de espera e só entrará na seção crítica após o primeiro nó terminar e liberar o recurso. Verifique o arquivo `recurso.txt` para comprovar que a ordem de chegada foi perfeitamente respeitada.